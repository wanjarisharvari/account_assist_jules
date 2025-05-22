from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db.models import Sum, F, Q, Count, Avg, Max, Min
from django.utils import timezone
from django.db.models.functions import TruncMonth, TruncYear, TruncDay, TruncWeek
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
import logging
import json

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes

from .models import Conversation, Message, Transaction, PendingTransaction, Customer, Vendor
from .serializers import (
    ConversationSerializer, 
    MessageSerializer, 
    TransactionSerializer, 
    PendingTransactionSerializer,
    MessageInputSerializer,
    TransactionConfirmSerializer,
    CustomerSerializer,
    VendorSerializer,
    TransactionCreateSerializer
)
from django.http import JsonResponse
from .services.gemini_services import GeminiService
from .services.sheets_services import GoogleSheetsService  # Re-enabled Google Sheets

# Create your views here.

def create_sample_data(user):
    """Create sample transaction data for testing the analytics view"""
    from datetime import timedelta
    import random
    
    # Create a few sample customers
    customers = []
    for i in range(3):
        customer = Customer.objects.create(
            user=user,
            name=f"Customer {i+1}",
            email=f"customer{i+1}@example.com",
            phone=f"123-456-{7890+i}",
            total_receivable=Decimal(str(random.randint(5000, 15000))),
            total_received=Decimal(str(random.randint(2000, 4000)))
        )
        customers.append(customer)
    
    # Create a few sample vendors
    vendors = []
    for i in range(3):
        vendor = Vendor.objects.create(
            user=user,
            name=f"Vendor {i+1}",
            email=f"vendor{i+1}@example.com",
            phone=f"987-654-{3210+i}",
            total_payable=Decimal(str(random.randint(3000, 10000))),
            total_paid=Decimal(str(random.randint(1000, 2500)))
        )
        vendors.append(vendor)
    
    # Income categories
    income_categories = ['Salary', 'Freelance Work', 'Investments', 'Rental Income', 'Other Income']
    
    # Expense categories
    expense_categories = ['Groceries', 'Rent', 'Utilities', 'Transportation', 'Entertainment', 'Healthcare', 'Dining']
    
    # Generate transactions for the last 6 months
    now = timezone.now().date()
    start_date = now - timedelta(days=180)  # 6 months ago
    
    # Create 50 random transactions
    for i in range(50):
        transaction_date = start_date + timedelta(days=random.randint(0, 180))
        transaction_type = random.choice(['INCOME', 'EXPENSE'])
        
        if transaction_type == 'INCOME':
            category = random.choice(income_categories)
            amount = Decimal(str(random.randint(1000, 5000)))
            customer = random.choice(customers) if random.random() > 0.3 else None
            vendor = None
            description = f"{category} - {transaction_date.strftime('%b')}"
        else:  # EXPENSE
            category = random.choice(expense_categories)
            amount = Decimal(str(random.randint(500, 3000)))
            customer = None
            vendor = random.choice(vendors) if random.random() > 0.3 else None
            description = f"{category} - {transaction_date.strftime('%b')}"
        
        Transaction.objects.create(
            user=user,
            date=transaction_date,
            description=description,
            category=category,
            transaction_type=transaction_type,
            amount=amount,
            customer=customer,
            vendor=vendor,
            payment_method=random.choice(['Cash', 'Credit Card', 'Bank Transfer', 'UPI'])
        )


class AnalyticsDataView(APIView):
    """API endpoint for fetching analytics data for different time periods"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        # Create sample data if no transactions exist
        if not Transaction.objects.filter(user=request.user).exists():
            create_sample_data(request.user)
        
        # Get time period from query parameters
        period = request.query_params.get('period', 'month')
        
        # Calculate date range based on period
        now = timezone.now().date()
        
        if period == 'month':
            # Current month
            start_date = now.replace(day=1)
            end_date = now
            prev_start = (start_date - timedelta(days=1)).replace(day=1)
            prev_end = start_date - timedelta(days=1)
            date_format = '%b %d'
            trunc_func = TruncDay
        elif period == 'last_month':
            # Last month
            start_date = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
            end_date = now.replace(day=1) - timedelta(days=1)
            prev_start = (start_date - timedelta(days=31)).replace(day=1)
            prev_end = start_date - timedelta(days=1)
            date_format = '%b %d'
            trunc_func = TruncDay
        elif period == 'last_3_months':
            # Last 3 months
            start_date = (now.replace(day=1) - timedelta(days=90))
            end_date = now
            prev_start = (start_date - timedelta(days=90))
            prev_end = start_date - timedelta(days=1)
            date_format = '%b %Y'
            trunc_func = TruncMonth
        elif period == 'last_6_months':
            # Last 6 months
            start_date = (now.replace(day=1) - timedelta(days=180))
            end_date = now
            prev_start = (start_date - timedelta(days=180))
            prev_end = start_date - timedelta(days=1)
            date_format = '%b %Y'
            trunc_func = TruncMonth
        elif period == 'year':
            # Current year
            start_date = now.replace(month=1, day=1)
            end_date = now
            prev_start = start_date.replace(year=start_date.year-1)
            prev_end = end_date.replace(year=end_date.year-1)
            date_format = '%b %Y'
            trunc_func = TruncMonth
        else:
            # Default to current month
            start_date = now.replace(day=1)
            end_date = now
            prev_start = (start_date - timedelta(days=1)).replace(day=1)
            prev_end = start_date - timedelta(days=1)
            date_format = '%b %d'
            trunc_func = TruncDay
        
        # Get transactions for the selected period
        transactions = Transaction.objects.filter(
            user=request.user,
            date__gte=start_date,
            date__lte=end_date
        )
        
        # Get previous period transactions for comparison
        prev_transactions = Transaction.objects.filter(
            user=request.user,
            date__gte=prev_start,
            date__lte=prev_end
        )
        
        # Calculate summary statistics
        total_income = transactions.filter(transaction_type='INCOME').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        total_expenses = transactions.filter(transaction_type='EXPENSE').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        
        prev_income = prev_transactions.filter(transaction_type='INCOME').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        prev_expenses = prev_transactions.filter(transaction_type='EXPENSE').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        
        # Ensure consistent decimal types
        if not isinstance(total_income, Decimal):
            total_income = Decimal(str(total_income))
        if not isinstance(total_expenses, Decimal):
            total_expenses = Decimal(str(total_expenses))
        if not isinstance(prev_income, Decimal):
            prev_income = Decimal(str(prev_income))
        if not isinstance(prev_expenses, Decimal):
            prev_expenses = Decimal(str(prev_expenses))
            
        net_balance = total_income - total_expenses
        prev_net_balance = prev_income - prev_expenses
        
        savings_rate = (net_balance / total_income * Decimal('100')) if total_income > 0 else Decimal('0')
        prev_savings_rate = (prev_net_balance / prev_income * Decimal('100')) if prev_income > 0 else Decimal('0')
        
        # Calculate income change percentage
        income_change = ((total_income - prev_income) / prev_income * Decimal('100')) if prev_income > 0 else Decimal('0')
        expense_change = ((prev_expenses - total_expenses) / prev_expenses * Decimal('100')) if prev_expenses > 0 else Decimal('0')
        
        # Get time series data for charts
        time_series = transactions.annotate(
            period=trunc_func('date')
        ).values('period', 'transaction_type').annotate(
            total=Sum('amount')
        ).order_by('period')
        
        # Prepare time series data for the chart
        periods = sorted(set([item['period'] for item in time_series]))
        
        labels = [period.strftime(date_format) for period in periods]
        income_data = [0] * len(periods)
        expense_data = [0] * len(periods)
        
        for item in time_series:
            period_index = periods.index(item['period'])
            if item['transaction_type'] == 'INCOME':
                income_data[period_index] = float(item['total'])
            else:
                expense_data[period_index] = float(item['total'])
        
        # Get expense categories
        expense_categories = transactions.filter(
            transaction_type='EXPENSE'
        ).values('category').annotate(total=Sum('amount')).order_by('-total')
        
        # Prepare category data for the chart
        categories = []
        category_totals = []
        
        for cat in expense_categories:
            if cat['category'] and cat['total'] > 0:
                categories.append(cat['category'])
                category_totals.append(float(cat['total']))
        
        # Define category colors
        category_colors = [
            '#4e73df', '#1cc88a', '#36b9cc', '#f6c23e', '#e74a3b', '#858796',
            '#5a5c69', '#3a3b45', '#1cc88a', '#36b9cc', '#f6c23e', '#e74a3b'
        ]
        
        # Get recent transactions
        recent_transactions = transactions.order_by('-date')[:5]
        
        # Serialize recent transactions
        recent_transactions_data = [{
            'date': transaction.date.strftime('%Y-%m-%d'),
            'description': transaction.description,
            'category': transaction.category,
            'amount': float(transaction.amount),
            'type': transaction.transaction_type.lower()
        } for transaction in recent_transactions]
        
        # Prepare response data
        response_data = {
            'summary': {
                'total_income': float(total_income),
                'total_expenses': float(total_expenses),
                'net_balance': float(net_balance),
                'savings_rate': float(savings_rate),
                'income_change': float(income_change),
                'expense_change': float(expense_change)
            },
            'monthly_data': {
                'labels': labels,
                'income': income_data,
                'expenses': expense_data
            },
            'categories': categories,
            'category_totals': category_totals,
            'category_colors': category_colors[:len(categories)],
            'recent_transactions': recent_transactions_data
        }
        
        return Response(response_data)
def home(request):
    """Home page view"""
    return render(request, 'base.html', {'title': 'Counto - Your Financial Assistant', 'user': request.user})

def login_view(request):
    """User login view"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            return render(request, 'login.html', {'error': 'Invalid username or password'})
    
    return render(request, 'login.html')

def logout_view(request):
    """User logout view"""
    logout(request)
    return redirect('home')

def register_view(request):
    """User registration view"""
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')
        
        # Basic validation
        if password1 != password2:
            return render(request, 'register.html', {'error': 'Passwords do not match'})
        
        # Check if username already exists
        if User.objects.filter(username=username).exists():
            return render(request, 'register.html', {'error': 'Username already exists'})
        
        # Create user
        user = User.objects.create_user(username=username, email=email, password=password1)
        login(request, user)
        return redirect('dashboard')
    
    return render(request, 'register.html')

def dashboard(request):
    """User dashboard"""
    if not request.user.is_authenticated:
        return redirect('login')
    return render(request, 'dashboard.html', {'title': 'Dashboard'})

from django.shortcuts import render, redirect
from django.db.models import Sum
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone
import json

from .models import Transaction, Customer, Vendor


def analytics(request):
    """Financial analytics dashboard"""
    if not request.user.is_authenticated:
        return redirect('login')

    # Check if we need to generate test data for demo purposes
    if Transaction.objects.filter(user=request.user).count() == 0:
        create_sample_data(request.user)

    now = timezone.now()
    first_day = now.replace(day=1).date()
    last_day = (first_day + timedelta(days=32)).replace(day=1) - timedelta(days=1)

    monthly_transactions = Transaction.objects.filter(
        user=request.user,
        date__range=(first_day, last_day)
    )

    # DEBUG
    print("Monthly transaction count:", monthly_transactions.count())
    print("Income count:", monthly_transactions.filter(transaction_type='INCOME').count())
    print("Expense count:", monthly_transactions.filter(transaction_type='EXPENSE').count())

    total_income = monthly_transactions.filter(transaction_type='INCOME').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    total_expenses = monthly_transactions.filter(transaction_type='EXPENSE').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')

    print("Total income:", total_income)
    print("Total expenses:", total_expenses)

    # Ensure Decimal types
    total_income = Decimal(total_income)
    total_expenses = Decimal(total_expenses)
    net_balance = total_income - total_expenses
    savings_rate = (net_balance / total_income * Decimal('100')) if total_income > 0 else Decimal('0')

    # Monthly data for last 6 months
    monthly_data = []
    for i in range(5, -1, -1):
        target_date = now - timedelta(days=30 * i)
        month = target_date.month
        year = target_date.year
        label = datetime(year, month, 1).strftime('%b %Y')

        trans = Transaction.objects.filter(
            user=request.user,
            date__year=year,
            date__month=month
        )
        income = trans.filter(transaction_type='INCOME').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        expense = trans.filter(transaction_type='EXPENSE').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')

        monthly_data.append({
            'month': label,
            'income': float(income),
            'expenses': float(expense)
        })

    # Expense categories for pie chart
    expense_categories = Transaction.objects.filter(
        user=request.user,
        transaction_type='EXPENSE',
        date__range=(first_day, last_day)
    ).values('category').annotate(total=Sum('amount')).order_by('-total')

    categories = []
    category_totals = []
    category_colors = [
        '#4e73df', '#1cc88a', '#36b9cc', '#f6c23e',
        '#e74a3b', '#858796', '#5a5c69', '#3a3b45'
    ]
    for cat in expense_categories:
        if cat['category'] and cat['total'] > 0:
            categories.append(cat['category'])
            category_totals.append(float(cat['total']))

    category_objects = [
        {'name': categories[i], 'amount': category_totals[i], 'color': category_colors[i % len(category_colors)]}
        for i in range(len(categories))
    ]

    # Recent transactions
    recent_transactions_data = [
        {
            'date': tx.date.strftime('%Y-%m-%d'),
            'description': tx.description,
            'category': tx.category or 'Uncategorized',
            'amount': float(tx.amount),
            'transaction_type': tx.transaction_type.lower()
        }
        for tx in Transaction.objects.filter(user=request.user).order_by('-date')[:5]
    ]

    # Customer data
    customer_data = []
    for cust in Customer.objects.filter(user=request.user, is_active=True):
        income = Transaction.objects.filter(user=request.user, customer=cust, transaction_type='INCOME').aggregate(total=Sum('amount'))['total'] or Decimal('0')
        if income > 0 or cust.total_receivable > 0 or cust.total_received > 0:
            customer_data.append({
                'name': cust.name,
                'total_receivable': float(cust.total_receivable or income),
                'total_received': float(cust.total_received),
                'outstanding_balance': float(cust.outstanding_balance or income - cust.total_received),
                'is_overdue': cust.is_overdue
            })

    # Vendor data
    vendor_data = []
    for vendor in Vendor.objects.filter(user=request.user, is_active=True):
        expense = Transaction.objects.filter(user=request.user, vendor=vendor, transaction_type='EXPENSE').aggregate(total=Sum('amount'))['total'] or Decimal('0')
        if expense > 0 or vendor.total_payable > 0 or vendor.total_paid > 0:
            vendor_data.append({
                'name': vendor.name,
                'total_payable': float(vendor.total_payable or expense),
                'total_paid': float(vendor.total_paid),
                'outstanding_balance': float(vendor.outstanding_balance or expense - vendor.total_paid),
            })

    # context = {
    #     'title': 'Financial Analytics',
    #     'summary': json.dumps({
    #         'total_income': float(total_income),
    #         'total_expenses': float(total_expenses),
    #         'net_balance': float(net_balance),
    #         'savings_rate': float(round(savings_rate, 1))
    #     }),
    #     'monthly_data': json.dumps(monthly_data),
    #     'categories': json.dumps(category_objects),
    #     'category_totals': json.dumps(category_totals),
    #     'category_colors': json.dumps(category_colors[:len(categories)]),
    #     'recent_transactions': json.dumps(recent_transactions_data),
    #     'customer_data': json.dumps(customer_data),
    #     'vendor_data': json.dumps(vendor_data)
    # }

        context = {
        'title': 'Financial Analytics',
        'summary': {
            'total_income': float(total_income),
            'total_expenses': float(total_expenses),
            'net_balance': float(net_balance),
            'savings_rate': float(round(savings_rate, 1))
        },
        'monthly_data': monthly_data,
        'categories': category_objects,
        'category_totals': category_totals,
        'category_colors': category_colors[:len(categories)],
        'recent_transactions': recent_transactions_data,
        'customer_data': customer_data,
        'vendor_data': vendor_data,
        }


        print(context)
    #     # Print everything to the terminal
    # print("Context data sent to template:")
    # print("Title:", context['title'])
    # print("Summary:", json.dumps(json.loads(context['summary']), indent=2))
    # print("Monthly Data:", json.dumps(json.loads(context['monthly_data']), indent=2))
    # print("Categories:", json.dumps(json.loads(context['categories']), indent=2))
    # print("Category Totals:", json.dumps(json.loads(context['category_totals']), indent=2))
    # print("Category Colors:", json.dumps(json.loads(context['category_colors']), indent=2))
    # print("Recent Transactions:", json.dumps(json.loads(context['recent_transactions']), indent=2))
    # print("Customer Data:", json.dumps(json.loads(context['customer_data']), indent=2))
    # print("Vendor Data:", json.dumps(json.loads(context['vendor_data']), indent=2))

    return render(request, 'analytics.html', context)


# def analytics(request):
#     """Financial analytics dashboard"""
#     if not request.user.is_authenticated:
#         return redirect('login')
    
#     # Check if we need to generate test data for demo purposes
#     transaction_count = Transaction.objects.filter(user=request.user).count()
#     if transaction_count == 0:
#         # Create sample data for testing if no transactions exist
#         create_sample_data(request.user)
    
#     # Get current month and year for filtering
#     now = timezone.now()
#     current_month = now.month
#     current_year = now.year
    
#     # Get transactions for the current month
#     monthly_transactions = Transaction.objects.filter(
#         user=request.user,
#         date__year=current_year,
#         date__month=current_month
#     )
    
#     # Calculate summary statistics
#     total_income = monthly_transactions.filter(transaction_type='INCOME').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
#     total_expenses = monthly_transactions.filter(transaction_type='EXPENSE').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    
#     # Ensure consistent decimal types
#     if not isinstance(total_income, Decimal):
#         total_income = Decimal(str(total_income))
#     if not isinstance(total_expenses, Decimal):
#         total_expenses = Decimal(str(total_expenses))
        
#     net_balance = total_income - total_expenses
#     savings_rate = (net_balance / total_income * Decimal('100')) if total_income > 0 else Decimal('0')
    
#     # Get data for the last 6 months for the chart
#     months_back = 6
#     monthly_data = []
#     for i in range(months_back - 1, -1, -1):
#         month = now.month - i
#         year = now.year
#         if month <= 0:
#             month += 12
#             year -= 1
            
#         month_date = datetime(year, month, 1)
#         month_name = month_date.strftime('%b %Y')
            
#         month_transactions = Transaction.objects.filter(
#             user=request.user,
#             date__year=year,
#             date__month=month
#         )
        
#         month_income = month_transactions.filter(transaction_type='INCOME').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
#         month_expenses = month_transactions.filter(transaction_type='EXPENSE').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        
#         # Ensure consistent decimal types
#         if not isinstance(month_income, Decimal):
#             month_income = Decimal(str(month_income))
#         if not isinstance(month_expenses, Decimal):
#             month_expenses = Decimal(str(month_expenses))
        
#         monthly_data.append({
#             'month': month_name,
#             # Convert to float only when adding to the context for JSON serialization
#             'income': float(month_income),
#             'expenses': float(month_expenses)
#         })
    
#     # Get expense categories
#     expense_categories = Transaction.objects.filter(
#         user=request.user,
#         transaction_type='EXPENSE',
#         date__year=current_year,
#         date__month=current_month
#     ).values('category').annotate(total=Sum('amount')).order_by('-total')
    
#     # Prepare category data for the chart
#     categories = []
#     category_totals = []
#     category_colors = [
#         '#4e73df', '#1cc88a', '#36b9cc', '#f6c23e', '#e74a3b', '#858796',
#         '#5a5c69', '#3a3b45', '#1cc88a', '#36b9cc', '#f6c23e', '#e74a3b'
#     ]
    
#     for i, cat in enumerate(expense_categories):
#         if cat['category'] and cat['total'] > 0:
#             categories.append(cat['category'])
#             category_totals.append(float(cat['total']))
    
#     # Get recent transactions
#     recent_transactions = Transaction.objects.filter(
#         user=request.user
#     ).order_by('-date')[:5]
    
#     # Serialize recent transactions for JavaScript
#     recent_transactions_data = []
#     for transaction in recent_transactions:
#         recent_transactions_data.append({
#             'date': transaction.date.strftime('%Y-%m-%d'),
#             'description': transaction.description,
#             'category': transaction.category or 'Uncategorized',
#             'amount': float(transaction.amount),
#             'transaction_type': transaction.transaction_type.lower()
#         })
        
#     # Calculate customer data directly from transactions and invoices
#     customers = Customer.objects.filter(user=request.user, is_active=True)
#     customer_data = []
    
#     for customer in customers:
#         # Get total transactions for this customer
#         customer_income = Transaction.objects.filter(
#             user=request.user,
#             customer=customer,
#             transaction_type='INCOME'
#         ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
#         # Ensure we have properly calculated values even if the balance fields aren't updated
#         if customer_income > 0 or customer.total_receivable > 0 or customer.total_received > 0:
#             customer_data.append({
#                 'name': customer.name,
#                 'total_receivable': float(customer.total_receivable) or float(customer_income),
#                 'total_received': float(customer.total_received),
#                 'outstanding_balance': float(customer.outstanding_balance) or float(customer_income - customer.total_received),
#                 'is_overdue': customer.is_overdue
#             })
    
#     # Calculate vendor data directly from transactions and bills
#     vendors = Vendor.objects.filter(user=request.user, is_active=True)
#     vendor_data = []
    
#     for vendor in vendors:
#         # Get total transactions for this vendor
#         vendor_expenses = Transaction.objects.filter(
#             user=request.user,
#             vendor=vendor,
#             transaction_type='EXPENSE'
#         ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
#         # Ensure we have properly calculated values even if the balance fields aren't updated
#         if vendor_expenses > 0 or vendor.total_payable > 0 or vendor.total_paid > 0:
#             vendor_data.append({
#                 'name': vendor.name,
#                 'total_payable': float(vendor.total_payable) or float(vendor_expenses),
#                 'total_paid': float(vendor.total_paid),
#                 'outstanding_balance': float(vendor.outstanding_balance) or float(vendor_expenses - vendor.total_paid),
#             })
            
#     # If we don't have any customer/vendor data, let's add some sample data for testing
#     if not customer_data:
#         # Find all income transactions and group by description as a proxy for customer
#         income_by_source = Transaction.objects.filter(
#             user=request.user,
#             transaction_type='INCOME'
#         ).values('description').annotate(total=Sum('amount')).order_by('-total')[:5]
        
#         for source in income_by_source:
#             if source['total'] > 0:
#                 customer_data.append({
#                     'name': source['description'] or 'Unknown Source',
#                     'total_receivable': float(source['total']),
#                     'total_received': 0,
#                     'outstanding_balance': float(source['total']),
#                     'is_overdue': False
#                 })
    
#     if not vendor_data:
#         # Find all expense transactions and group by description as a proxy for vendor
#         expenses_by_source = Transaction.objects.filter(
#             user=request.user,
#             transaction_type='EXPENSE'
#         ).values('description').annotate(total=Sum('amount')).order_by('-total')[:5]
        
#         for source in expenses_by_source:
#             if source['total'] > 0:
#                 vendor_data.append({
#                     'name': source['description'] or 'Unknown Vendor',
#                     'total_payable': float(source['total']),
#                     'total_paid': 0,
#                     'outstanding_balance': float(source['total'])
#                 })
    
#     # Create category objects for the chart
#     category_objects = []
#     for i, category in enumerate(categories):
#         if i < len(category_totals) and i < len(category_colors):
#             category_objects.append({
#                 'name': category,
#                 'amount': category_totals[i],
#                 'color': category_colors[i]
#             })
    
#     # Prepare context
#     context = {
#         'title': 'Financial Analytics',
#         'summary': {
#             # Convert Decimal to float for JSON serialization
#             'total_income': float(total_income),
#             'total_expenses': float(total_expenses),
#             'net_balance': float(net_balance),
#             'savings_rate': float(round(savings_rate, 1))
#         },
#         'monthly_data': json.dumps(monthly_data),
#         'categories': json.dumps(category_objects),
#         'category_totals': json.dumps(category_totals),
#         'category_colors': json.dumps(category_colors[:len(categories)]),
#         'recent_transactions': json.dumps(recent_transactions_data),
#         'customer_data': json.dumps(customer_data),
#         'vendor_data': json.dumps(vendor_data)
#     }
    
#     return render(request, 'analytics.html', context)


class ConversationView(APIView):
    """Endpoint for managing conversations"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get all conversations for current user"""
        conversations = Conversation.objects.filter(user=request.user)
        serializer = ConversationSerializer(conversations, many=True)
        return Response(serializer.data)
    
    def post(self, request):
        """Create a new conversation"""
        conversation = Conversation.objects.create(user=request.user)
        serializer = ConversationSerializer(conversation)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class MessageView(APIView):
    """Endpoint for handling chat messages"""
    permission_classes = [permissions.IsAuthenticated]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gemini_service = GeminiService()
        # Re-enabled Google Sheets with improved error handling
        try:
            self.sheets_service = GoogleSheetsService()
            self.sheets_enabled = True
        except Exception as e:
            logging.error(f"Failed to initialize Google Sheets: {str(e)}")
            self.sheets_enabled = False
    
    def get(self, request, conversation_id):
        """Get all messages for a specific conversation"""
        conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
        messages = Message.objects.filter(conversation=conversation)
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)
   
    def post(self, request):
        """Process a new message from the user"""
        try:
            # Get or create conversation
            conversation_id = request.data.get('conversation_id')
            if conversation_id:
                conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
            else:
                conversation = Conversation.objects.create(user=request.user)
            
            # Store conversation in the instance for use in handler methods
            self.current_conversation = conversation
            
            # Save user message
            user_message = request.data.get('content', '')
            Message.objects.create(
                conversation=conversation,
                sender='USER',
                content=user_message
            )
            
            # Get conversation history
            history = Message.objects.filter(conversation=conversation).values('sender', 'content')
            
            # Process message through Gemini
            try:
                ai_response, extracted_data, intent_type, is_query = self.gemini_service.process_message(
                    user_message, 
                    list(history)
                )
                # Convert intent_type to the expected format
                if is_query:
                    intent_type = f'QUERY_{intent_type}'
                else:
                    intent_type = f'DATA_ENTRY_{intent_type}'
            except Exception as e:
                logging.error(f"Gemini API error: {str(e)}")
                return Response({
                    'error': 'Error processing message with AI service',
                    'detail': str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Handle different entity types based on intent
            try:
                if intent_type.startswith('DATA_ENTRY_'):
                    if intent_type == 'DATA_ENTRY_TRANSACTION':
                        ai_response = self._handle_transaction_data(request.user, extracted_data, ai_response)
                    elif intent_type == 'DATA_ENTRY_CUSTOMER':
                        ai_response = self._handle_customer_data(request.user, extracted_data, ai_response)
                    elif intent_type == 'DATA_ENTRY_VENDOR':
                        ai_response = self._handle_vendor_data(request.user, extracted_data, ai_response)
                    else:
                        logging.warning(f"Unhandled data entry type: {intent_type}")
                elif intent_type.startswith('QUERY_'):
                    if intent_type == 'QUERY_TRANSACTION':
                        ai_response = self._handle_transaction_query(extracted_data, ai_response)
                    elif intent_type == 'QUERY_CUSTOMER':
                        ai_response = self._handle_customer_query(extracted_data, ai_response)
                    elif intent_type == 'QUERY_VENDOR':
                        ai_response = self._handle_vendor_query(extracted_data, ai_response)
                    else:
                        logging.warning(f"Unhandled query type: {intent_type}")
                else:
                    logging.warning(f"Unknown intent type: {intent_type}")
            except Exception as e:
                error_msg = f"Error handling {intent_type}: {str(e)}"
                logging.error(error_msg, exc_info=True)
                ai_response = f"{ai_response}\n\n⚠️ {error_msg}"
                # If we have a critical error, return a clean error message
                if not ai_response.strip():
                    ai_response = f"Sorry, there was an error processing your {intent_type.replace('_', ' ').lower()} request."

            # Save AI response
            Message.objects.create(
                conversation=conversation,
                sender='AI',
                content=ai_response
            )

            # Update conversation
            conversation.updated_at = timezone.now()
            conversation.save()

            return Response({
                'conversation_id': conversation.id,
                'message': ai_response,
                'intent_type': intent_type if 'intent_type' in locals() else None
            })

        except Exception as e:
            logging.error(f"Unexpected error: {str(e)}", exc_info=True)
            return Response({
                'error': 'An unexpected error occurred',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _handle_transaction_data(self, user, extracted_data, ai_response):
        """Process and save transaction data"""
        # Handle date conversion
        date_str = extracted_data.get('date')
        transaction_date = None
        print("handling transaction data")
        if date_str:
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%m-%d-%Y']:
                try:
                    transaction_date = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue
        
        # Use current date if none provided
        transaction_date = transaction_date or timezone.now().date()
        
        # Handle amount conversion
        amount = self._parse_amount(extracted_data.get('paid_amount', extracted_data.get('amount', '0')))
        
        # Determine transaction type (INCOME or EXPENSE)
        transaction_type = extracted_data.get('transaction_type', 'EXPENSE')
        if transaction_type not in ['INCOME', 'EXPENSE']:
            transaction_type = 'EXPENSE'
        
        # Get or create customer/vendor if applicable
        customer = None
        vendor = None
        
        # Extract the customer/vendor based on name
        customer_name = extracted_data.get('customer')
        vendor_name = extracted_data.get('vendor')
        
        # For INCOME transactions, handle customer reference
        if transaction_type == 'INCOME' and customer_name:
            try:
                customer = Customer.objects.get(user=user, name=customer_name)
            except Customer.DoesNotExist:
                customer = Customer.objects.create(
                    user=user,
                    name=customer_name,
                    email=extracted_data.get('customer_email', ''),
                    phone=extracted_data.get('customer_phone', ''),
                    gst_number=extracted_data.get('customer_gst', ''),
                    address=extracted_data.get('customer_address', '')
                )
        
        # For EXPENSE transactions, handle vendor reference
        if transaction_type == 'EXPENSE' and vendor_name:
            try:
                vendor = Vendor.objects.get(user=user, name=vendor_name)
            except Vendor.DoesNotExist:
                vendor = Vendor.objects.create(
                    user=user,
                    name=vendor_name,
                    email=extracted_data.get('vendor_email', ''),
                    phone=extracted_data.get('vendor_phone', ''),
                    gst_number=extracted_data.get('vendor_gst', ''),
                    address=extracted_data.get('vendor_address', '')
                )

        # Create transaction record based on new Transaction model
        transaction = Transaction.objects.create(
            user=user,
            date=transaction_date,
            description=extracted_data.get('description', ''),
            category=extracted_data.get('category', ''),
            transaction_type=transaction_type,
            amount=amount,
            customer=customer,
            vendor=vendor,
            payment_method=extracted_data.get('payment_method', ''),
            reference_number=extracted_data.get('reference_number', ''),
            notes=extracted_data.get('notes', '')
        )
        
        # Update customer/vendor balances using Decimal for precision
        if transaction_type == 'INCOME' and customer:
            # Ensure total_receivable is a Decimal before adding amount
            if customer.total_receivable is None:
                customer.total_receivable = Decimal('0.00')
            elif not isinstance(customer.total_receivable, Decimal):
                customer.total_receivable = Decimal(str(customer.total_receivable))
                
            customer.total_receivable = (customer.total_receivable + amount).quantize(Decimal('0.00'))
            # outstanding_balance is a read-only property, no need to set it
            customer.save()
        elif transaction_type == 'EXPENSE' and vendor:
            # Ensure total_payable is a Decimal before adding amount
            if vendor.total_payable is None:
                vendor.total_payable = Decimal('0.00')
            elif not isinstance(vendor.total_payable, Decimal):
                vendor.total_payable = Decimal(str(vendor.total_payable))
                
            vendor.total_payable = (vendor.total_payable + amount).quantize(Decimal('0.00'))
            # outstanding_balance is a read-only property, no need to set it
            vendor.save()

        # Create a pending transaction for reference (if needed)
        pending_transaction = PendingTransaction.objects.create(
            user=user,
            conversation=self.current_conversation,  # Use the stored conversation
            date=transaction_date,
            description=transaction.description,
            category=transaction.category,
            amount=transaction.amount,
            transaction_type=transaction.transaction_type,
            payment_method=transaction.payment_method,
            reference_number=transaction.reference_number,
            party=customer_name if transaction_type == 'INCOME' else vendor_name
        )

        # Update AI response
        if "Would you like me to record this transaction?" in ai_response:
            ai_response = ai_response.split("Would you like me to record this transaction?")[0]
            
            # Prepare transaction details for the response
            transaction_type = 'Income' if transaction.transaction_type == 'INCOME' else 'Expense'
            party = customer.name if customer else vendor.name if vendor else 'N/A'
            
            ai_response += f"\n\n✅ {transaction_type} of ₹{amount:,.2f} "
            ai_response += f"for {party} has been recorded!\n"
            
            # Add financial summary for customer/vendor
            if customer:
                ai_response += f"\n💳 Customer Balance Update for {customer.name}:"
                ai_response += f"\n• Total Receivable: ₹{customer.total_receivable:,.2f}"
                ai_response += f"\n• Total Received: ₹{customer.total_received:,.2f}"
                ai_response += f"\n• Outstanding Balance: ₹{customer.outstanding_balance:,.2f}"
            elif vendor:
                ai_response += f"\n💳 Vendor Balance Update for {vendor.name}:"
                ai_response += f"\n• Total Payable: ₹{vendor.total_payable:,.2f}"
                ai_response += f"\n• Total Paid: ₹{vendor.total_paid:,.2f}"
                ai_response += f"\n• Outstanding Balance: ₹{vendor.outstanding_balance:,.2f}"
            
            # Sync with Google Sheets
            sheets_success = False
            sheets_error = None
            if self.sheets_enabled:
                try:
                    # Sync transaction
                    sheets_data = {
                        'date': transaction_date,
                        'description': transaction.description,
                        'category': transaction.category,
                        'transaction_type': transaction.transaction_type,
                        'amount': float(str(amount)),  # Convert Decimal to string then to float
                        'payment_method': transaction.payment_method or '',
                        'reference_number': transaction.reference_number or '',
                        'customer': customer.name if customer else '',
                        'vendor': vendor.name if vendor else '',
                        'notes': transaction.notes or ''
                    }
                    sheets_success = self.sheets_service.add_transaction(sheets_data)
                    
                    # Update customer/vendor in Google Sheets if this is a new transaction
                    if customer:
                        customer_sheets_data = {
                            'name': customer.name,
                            'email': customer.email or '',
                            'phone': customer.phone or '',
                            'gst_number': customer.gst_number or '',
                            'address': customer.address or '',
                            'total_receivable': float(str(customer.total_receivable or '0')),
                            'total_received': float(str(customer.total_received or '0')),
                            'outstanding_balance': float(str(customer.outstanding_balance or '0'))
                        }
                        self.sheets_service.add_customer(customer_sheets_data)
                    elif vendor:
                        vendor_sheets_data = {
                            'name': vendor.name,
                            'email': vendor.email or '',
                            'phone': vendor.phone or '',
                            'gst_number': vendor.gst_number or '',
                            'address': vendor.address or '',
                            'total_payable': float(str(vendor.total_payable or '0')),
                            'total_paid': float(str(vendor.total_paid or '0')),
                            'outstanding_balance': float(str(vendor.outstanding_balance or '0'))
                        }
                        self.sheets_service.add_vendor(vendor_sheets_data)
                        
                except Exception as e:
                    sheets_error = str(e)
                    logging.error(f"Google Sheets sync failed: {sheets_error}")
            
            # Add sync status to response
            if sheets_success:
                ai_response += "\n\n📊 Data synced with Google Sheets."
            elif sheets_error:
                ai_response += f"\n\n⚠️ Note: Google Sheets sync failed ({sheets_error})"
            else:
                ai_response += "\n\n💾 Data saved locally (Google Sheets not configured)."
                
        return ai_response

    def _handle_customer_data(self, user, extracted_data, ai_response):
        """Process and save customer data"""
        # Extract customer data
        customer_data = {
            'name': extracted_data.get('name', ''),
            'email': extracted_data.get('email', ''),
            'phone': extracted_data.get('phone', ''),
            'gst_number': extracted_data.get('gst_number', ''),
            'address': extracted_data.get('address', '')
        }

        # Check if customer already exists
        existing_customer = None
        try:
            existing_customer = Customer.objects.get(user=user, name=customer_data['name'])
        except Customer.DoesNotExist:
            pass

        if existing_customer:
            # Update existing customer
            for key, value in customer_data.items():
                if value:  # Only update non-empty fields
                    setattr(existing_customer, key, value)
            existing_customer.save()
            customer = existing_customer
            operation = "updated"
        else:
            # Create new customer using the updated Customer model
            customer = Customer.objects.create(user=user, **customer_data)
            operation = "created"

        # Sync with Google Sheets
        sheets_success = False
        sheets_error = None
        if self.sheets_enabled:
            try:
                # Include financial data for Google Sheets
                sheets_data = {
                    'name': customer.name,
                    'email': customer.email or '',
                    'phone': customer.phone or '',
                    'gst_number': customer.gst_number or '',
                    'address': customer.address or '',
                    'total_receivable': float(customer.total_receivable or 0),
                    'total_received': float(customer.total_received or 0),
                    'outstanding_balance': float(customer.outstanding_balance or 0),
                    'created_at': customer.created_at.strftime('%Y-%m-%d %H:%M:%S') if customer.created_at else ''
                }
                sheets_success = self.sheets_service.add_customer(sheets_data)
            except Exception as e:
                sheets_error = str(e)
                logging.error(f"Google Sheets sync failed: {sheets_error}")
                
        # Update AI response with financial summary if this is an update
        if operation == "updated":
            ai_response += f"\n\n💵 Financial Summary for {customer.name}:"
            ai_response += f"\n• Total Receivable: ₹{customer.total_receivable:,.2f}"
            ai_response += f"\n• Total Received: ₹{customer.total_received:,.2f}"
            ai_response += f"\n• Outstanding Balance: ₹{customer.outstanding_balance:,.2f}"

        # Update AI response with operation result
        ai_response = f"✅ Customer '{customer.name}' {operation} successfully!\n"
        
        # Add customer details
        ai_response += f"\n📝 Customer Details:"
        if customer.email:
            ai_response += f"\n• Email: {customer.email}"
        if customer.phone:
            ai_response += f"\n• Phone: {customer.phone}"
        if customer.gst_number:
            ai_response += f"\n• GST: {customer.gst_number}"
            
        # Add financial summary
        ai_response += f"\n\n💳 Financial Summary:"
        ai_response += f"\n• Total Receivable: ₹{customer.total_receivable:,.2f}"
        ai_response += f"\n• Total Received: ₹{customer.total_received:,.2f}"
        ai_response += f"\n• Outstanding Balance: ₹{customer.outstanding_balance:,.2f}"
        
        # Add sync status
        if sheets_success:
            ai_response += "\n\n📊 Data synced with Google Sheets."
        elif sheets_error:
            ai_response += f"\n\n⚠️ Note: Google Sheets sync failed ({sheets_error})"
        else:
            ai_response += "\n\n💾 Data saved locally (Google Sheets not configured)."
            
        # Add helpful next steps
        ai_response += "\n\n💡 You can now record transactions for this customer or view their transaction history."
            
        return ai_response

    def _handle_vendor_data(self, user, extracted_data, ai_response):
        """Process and save vendor data"""
        # Extract vendor data
        vendor_data = {
            'name': extracted_data.get('name', ''),
            'email': extracted_data.get('email', ''),
            'phone': extracted_data.get('phone', ''),
            'gst_number': extracted_data.get('gst_number', ''),
            'address': extracted_data.get('address', '')
        }

        # Check if vendor already exists
        existing_vendor = None
        try:
            existing_vendor = Vendor.objects.get(user=user, name=vendor_data['name'])
        except Vendor.DoesNotExist:
            pass

        if existing_vendor:
            # Update existing vendor
            for key, value in vendor_data.items():
                if value:  # Only update non-empty fields
                    setattr(existing_vendor, key, value)
            existing_vendor.save()
            vendor = existing_vendor
            operation = "updated"
        else:
            # Create new vendor using the updated Vendor model
            vendor = Vendor.objects.create(user=user, **vendor_data)
            operation = "created"

        # Sync with Google Sheets
        sheets_success = False
        sheets_error = None
        if self.sheets_enabled:
            try:
                # Include financial data for Google Sheets
                sheets_data = {
                    'name': vendor.name,
                    'email': vendor.email or '',
                    'phone': vendor.phone or '',
                    'gst_number': vendor.gst_number or '',
                    'address': vendor.address or '',
                    'total_payable': float(vendor.total_payable or 0),
                    'total_paid': float(vendor.total_paid or 0),
                    'outstanding_balance': float(vendor.outstanding_balance or 0),
                    'created_at': vendor.created_at.strftime('%Y-%m-%d %H:%M:%S') if vendor.created_at else ''
                }
                sheets_success = self.sheets_service.add_vendor(sheets_data)
            except Exception as e:
                sheets_error = str(e)
                logging.error(f"Google Sheets sync failed: {sheets_error}")
                
        # Update AI response with financial summary if this is an update
        if operation == "updated":
            ai_response += f"\n\n💵 Financial Summary for {vendor.name}:"
            ai_response += f"\n• Total Payable: ₹{vendor.total_payable:,.2f}"
            ai_response += f"\n• Total Paid: ₹{vendor.total_paid:,.2f}"
            ai_response += f"\n• Outstanding Balance: ₹{vendor.outstanding_balance:,.2f}"

        # Update AI response with operation result
        ai_response = f"✅ Vendor '{vendor.name}' {operation} successfully!\n"
        
        # Add vendor details
        ai_response += f"\n📝 Vendor Details:"
        if vendor.email:
            ai_response += f"\n• Email: {vendor.email}"
        if vendor.phone:
            ai_response += f"\n• Phone: {vendor.phone}"
        if vendor.gst_number:
            ai_response += f"\n• GST: {vendor.gst_number}"
            
        # Add financial summary
        ai_response += f"\n\n💳 Financial Summary:"
        ai_response += f"\n• Total Payable: ₹{vendor.total_payable:,.2f}"
        ai_response += f"\n• Total Paid: ₹{vendor.total_paid:,.2f}"
        ai_response += f"\n• Outstanding Balance: ₹{vendor.outstanding_balance:,.2f}"
        
        # Add sync status
        if sheets_success:
            ai_response += "\n\n📊 Data synced with Google Sheets."
        elif sheets_error:
            ai_response += f"\n\n⚠️ Note: Google Sheets sync failed ({sheets_error})"
        else:
            ai_response += "\n\n💾 Data saved locally (Google Sheets not configured)."
            
        # Add helpful next steps
        ai_response += "\n\n💡 You can now record expenses for this vendor or view their transaction history."
            
        return ai_response

    def _handle_transaction_query(self, query_params, ai_response):
        """Process transaction query"""
        if not self.sheets_enabled:
            return ai_response + "\n\nUnable to query transactions as Google Sheets integration is not enabled."

        try:
            transactions = self.sheets_service.search_transactions(query_params)
            
            if transactions:
                ai_response += "\n\nHere are the transactions I found:\n"
                for idx, tx in enumerate(transactions[:10]):  # Show only first 10 for brevity
                    paid = tx.get('paid_amount', '0')
                    expected = tx.get('expected_amount', paid)
                    # Format as plain numbers without currency symbols
                    amount_str = f"{paid}/{expected}" if paid != expected else f"{paid}"
                    ai_response += f"{idx+1}. {tx.get('date', 'N/A')} - {tx.get('description', 'N/A')} - {amount_str} ({tx.get('status', 'N/A')})\n"
                    
                if len(transactions) > 10:
                    ai_response += f"...and {len(transactions)-10} more transactions."
            else:
                ai_response += "\n\nI couldn't find any transactions matching your criteria."
        except Exception as e:
            logging.error(f"Error querying transactions: {str(e)}")
            ai_response += f"\n\nI encountered an error while trying to retrieve your transactions: {str(e)}"

        return ai_response

    def _handle_customer_query(self, query_params, ai_response):
        """Process customer query"""
        if not self.sheets_enabled:
            return ai_response + "\n\nUnable to query customers as Google Sheets integration is not enabled."
        
        try:
            customers = self.sheets_service.search_customers(query_params)
            
            if customers:
                ai_response += "\n\nHere are the customers I found:\n"
                for idx, customer in enumerate(customers[:10]):  # Show only first 10 for brevity
                    ai_response += f"{idx+1}. {customer.get('name', 'N/A')}"
                    if customer.get('phone'):
                        ai_response += f" - {customer.get('phone')}"
                    if customer.get('email'):
                        ai_response += f" - {customer.get('email')}"
                    ai_response += "\n"
                    
                if len(customers) > 10:
                    ai_response += f"...and {len(customers)-10} more customers."
            else:
                ai_response += "\n\nI couldn't find any customers matching your criteria."
        except Exception as e:
            logging.error(f"Error querying customers: {str(e)}")
            ai_response += f"\n\nI encountered an error while trying to retrieve your customers: {str(e)}"
        
        return ai_response

    def _handle_vendor_query(self, query_params, ai_response):
        """Process vendor query"""
        if not self.sheets_enabled:
            return ai_response + "\n\nUnable to query vendors as Google Sheets integration is not enabled."
        
        try:
            vendors = self.sheets_service.search_vendors(query_params)
            
            if vendors:
                ai_response += "\n\nHere are the vendors I found:\n"
                for idx, vendor in enumerate(vendors[:10]):  # Show only first 10 for brevity
                    ai_response += f"{idx+1}. {vendor.get('name', 'N/A')}"
                    if vendor.get('phone'):
                        ai_response += f" - {vendor.get('phone')}"
                    if vendor.get('email'):
                        ai_response += f" - {vendor.get('email')}"
                    ai_response += "\n"
                    
                if len(vendors) > 10:
                    ai_response += f"...and {len(vendors)-10} more vendors."
            else:
                ai_response += "\n\nI couldn't find any vendors matching your criteria."
        except Exception as e:
            logging.error(f"Error querying vendors: {str(e)}")
            ai_response += f"\n\nI encountered an error while trying to retrieve your vendors: {str(e)}"
        
        return ai_response

    def _parse_amount(self, amount_str):
        """Helper method to parse amount strings"""
        if not amount_str or str(amount_str).strip().upper() == '[OPTIONAL]':
            return Decimal('0.00')
        
        # Handle string representation of numbers
        if isinstance(amount_str, str):
            # Remove currency symbols, commas, and any whitespace
            amount_str = amount_str.replace('$', '').replace('€', '').replace('£', '').replace('₹', '').replace(',', '').strip()
            
            # If empty after cleaning, return 0
            if not amount_str:
                return Decimal('0.00')
                
        try:
            # Convert to Decimal with 2 decimal places for currency
            return Decimal(amount_str).quantize(Decimal('0.00'))
        except (ValueError, TypeError, InvalidOperation):
            logging.warning(f"Could not convert amount '{amount_str}' to decimal, using 0")
            return Decimal('0.00')


class CustomerView(APIView):
    """API endpoint for managing customers"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, customer_id=None):
        """Get all customers or a specific customer"""
        if customer_id:
            customer = get_object_or_404(Customer, id=customer_id, user=request.user)
            serializer = CustomerSerializer(customer)
            return Response(serializer.data)
        
        customers = Customer.objects.filter(user=request.user)
        serializer = CustomerSerializer(customers, many=True)
        return Response(serializer.data)
    
    def post(self, request):
        """Create a new customer"""
        serializer = CustomerSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, customer_id):
        """Update an existing customer"""
        customer = get_object_or_404(Customer, id=customer_id, user=request.user)
        serializer = CustomerSerializer(customer, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, customer_id):
        """Delete a customer"""
        customer = get_object_or_404(Customer, id=customer_id, user=request.user)
        customer.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class VendorView(APIView):
    """API endpoint for managing vendors"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, vendor_id=None):
        """Get all vendors or a specific vendor"""
        if vendor_id:
            vendor = get_object_or_404(Vendor, id=vendor_id, user=request.user)
            serializer = VendorSerializer(vendor)
            return Response(serializer.data)
        else:
            vendors = Vendor.objects.filter(user=request.user)
            serializer = VendorSerializer(vendors, many=True)
            return Response(serializer.data)
    
    def post(self, request):
        """Create a new vendor"""
        serializer = VendorSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, vendor_id):
        """Update an existing vendor"""
        vendor = get_object_or_404(Vendor, id=vendor_id, user=request.user)
        serializer = VendorSerializer(vendor, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, vendor_id):
        """Delete a vendor"""
        vendor = get_object_or_404(Vendor, id=vendor_id, user=request.user)
        vendor.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TransactionView(APIView):
    """API endpoint for managing transactions"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, transaction_id=None):
        """Get all transactions or a specific transaction"""
        if transaction_id:
            transaction = get_object_or_404(Transaction, id=transaction_id, user=request.user)
            serializer = TransactionSerializer(transaction)
            return Response(serializer.data)
        else:
            transactions = Transaction.objects.filter(user=request.user).order_by('-date')
            serializer = TransactionSerializer(transactions, many=True)
            return Response(serializer.data)
    
    def post(self, request):
        """Create a new transaction"""
        serializer = TransactionCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            transaction = serializer.save(user=request.user)
            return Response(
                TransactionSerializer(transaction).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, transaction_id):
        """Update an existing transaction"""
        transaction = get_object_or_404(Transaction, id=transaction_id, user=request.user)
        serializer = TransactionCreateSerializer(transaction, data=request.data, partial=True)
        if serializer.is_valid():
            updated_transaction = serializer.save()
            return Response(TransactionSerializer(updated_transaction).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, transaction_id):
        """Delete a transaction"""
        transaction = get_object_or_404(Transaction, id=transaction_id, user=request.user)
        transaction.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TransactionConfirmView(APIView):
    """Endpoint for confirming pending transactions"""
    permission_classes = [permissions.IsAuthenticated]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Re-enabled Google Sheets with improved error handling
        try:
            self.sheets_service = GoogleSheetsService()
            self.sheets_enabled = True
        except Exception as e:
            logging.error(f"Failed to initialize Google Sheets: {str(e)}")
            self.sheets_enabled = False
    
    def post(self, request):
        """Confirm or reject a pending transaction"""
        serializer = TransactionConfirmSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        pending_id = serializer.validated_data['pending_transaction_id']
        confirm = serializer.validated_data['confirm']
        
        # Get the pending transaction
        pending_transaction = get_object_or_404(
            PendingTransaction, 
            id=pending_id, 
            user=request.user
        )
        
        if confirm:
            # Prepare transaction data
            transaction_data = {
                'date': pending_transaction.date,
                'description': pending_transaction.description,
                'category': pending_transaction.category,
                'transaction_type': pending_transaction.transaction_type,
                'expected_amount': pending_transaction.expected_amount,
                'paid_amount': pending_transaction.paid_amount,
                'status': pending_transaction.status,
                'payment_method': pending_transaction.payment_method,
                'reference_number': pending_transaction.reference_number,
                'customer': pending_transaction.customer,
                'vendor': pending_transaction.vendor
            }
            
            # Try to save to Google Sheets if enabled
            sheets_success = False
            if hasattr(self, 'sheets_enabled') and self.sheets_enabled:
                try:
                    sheets_data = transaction_data.copy()
                    # Convert model instances to names for sheets
                    if transaction_data.get('customer'):
                        sheets_data['customer'] = transaction_data['customer'].name
                    if transaction_data.get('vendor'):
                        sheets_data['vendor'] = transaction_data['vendor'].name
                        
                    sheets_success = self.sheets_service.add_transaction(sheets_data)
                except Exception as e:
                    logging.error(f"Failed to add to Google Sheets: {str(e)}")
            
            # Always succeed locally even if Google Sheets fails
            success = True
            
            if success:
                # Create a Transaction record in our database
                transaction = Transaction.objects.create(
                    user=request.user,
                    **transaction_data
                )
                
                # Add confirmation message to conversation
                conversation = pending_transaction.conversation
                Message.objects.create(
                    conversation=conversation,
                    sender='AI',
                    content=f"✅ Transaction confirmed and added to your records:\n\n"
                            f"• {pending_transaction.date}: {pending_transaction.description}\n"
                            f"• Expected Amount: {pending_transaction.expected_amount}\n"
                            f"• Paid Amount: {pending_transaction.paid_amount}\n"
                            f"• Category: {pending_transaction.category or 'Uncategorized'}"
                )
                
                # Delete the pending transaction
                pending_transaction.delete()
                
                return Response({
                    'status': 'success',
                    'message': 'Transaction added successfully',
                    'transaction_id': transaction.id
                })
            else:
                return Response({
                    'status': 'error',
                    'message': 'Failed to add transaction to your records'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            # User rejected the transaction
            conversation = pending_transaction.conversation
            Message.objects.create(
                conversation=conversation,
                sender='AI',
                content="Transaction cancelled. Is there anything else you'd like to do?"
            )
            
            # Delete the pending transaction
            pending_transaction.delete()
            
            return Response({
                'status': 'success',
                'message': 'Transaction cancelled'
            })