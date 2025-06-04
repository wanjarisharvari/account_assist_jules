from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Sum, F, Q, Count, Avg, Max, Min
from django.utils import timezone
from django.db.models.functions import TruncMonth, TruncYear, TruncDay, TruncWeek
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union
import logging
import json
import os # Already here, but good to confirm
import uuid
from django.conf import settings # Already here, but good to confirm

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

# create_sample_data function removed as it's now a management command.

class AnalyticsDataView(APIView):
    """API endpoint for fetching analytics data for different time periods"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        # Sample data creation is now handled by the management command:
        # `python manage.py create_counto_sample_data <username>`
        # The check below is removed:
        # if not Transaction.objects.filter(user=request.user).exists():
        #     create_sample_data(request.user)
        
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

        # Customer Data - Top 5 by outstanding balance
        customers_query = Customer.objects.filter(user=request.user, is_active=True)
        # Order by outstanding_balance. Since outstanding_balance is a property,
        # we might need to fetch all and sort in Python, or use annotation if it were a direct DB field.
        # For now, let's fetch all and sort, then limit.
        all_customers = list(customers_query)
        # Sort by outstanding_balance in descending order
        all_customers.sort(key=lambda c: (c.outstanding_balance or Decimal('0')), reverse=True)

        customer_data_list = []
        for customer in all_customers[:5]: # Limit to top 5
            customer_data_list.append({
                'name': customer.name,
                'total_receivable': float(customer.total_receivable or 0),
                'total_received': float(customer.total_received or 0),
                'outstanding_balance': float(customer.outstanding_balance or 0),
                'is_overdue': customer.is_overdue
            })
        response_data['customer_data'] = customer_data_list

        # Vendor Data - Top 5 by outstanding balance
        vendors_query = Vendor.objects.filter(user=request.user, is_active=True)
        all_vendors = list(vendors_query)
        # Sort by outstanding_balance (property) in descending order
        all_vendors.sort(key=lambda v: (v.outstanding_balance or Decimal('0')), reverse=True)

        vendor_data_list = []
        for vendor in all_vendors[:5]: # Limit to top 5
            vendor_data_list.append({
                'name': vendor.name,
                'total_payable': float(vendor.total_payable or 0),
                'total_paid': float(vendor.total_paid or 0),
                'outstanding_balance': float(vendor.outstanding_balance or 0),
                'is_overdue': False # Placeholder as Vendor model does not have is_overdue
            })
        response_data['vendor_data'] = vendor_data_list

        # Cash Flow Forecast Data (Placeholder)
        response_data['cash_flow_forecast'] = {
            'labels': ['Current', 'Next Month', 'In 2 Months', 'In 3 Months'],
            'income': [float(total_income), float(total_income * Decimal('1.1')), float(total_income * Decimal('1.15')), float(total_income * Decimal('1.2'))], # Dummy projection
            'expenses': [float(total_expenses), float(total_expenses * Decimal('1.05')), float(total_expenses * Decimal('1.1')), float(total_expenses * Decimal('1.12'))], # Dummy projection
            'balance': [
                float(total_income - total_expenses),
                float((total_income * Decimal('1.1')) - (total_expenses * Decimal('1.05'))),
                float((total_income * Decimal('1.15')) - (total_expenses * Decimal('1.1'))),
                float((total_income * Decimal('1.2')) - (total_expenses * Decimal('1.12')))
            ]
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


@login_required
def analytics(request):
    """Financial analytics dashboard page - data is fetched via API."""
    context = {
        'title': 'Financial Analytics',
    }
    return render(request, 'analytics.html', context)

# The old analytics view code has been removed as per previous subtasks.
# This is just ensuring it's clean and matches the simplified version.


def upload_document(request):
    logger = logging.getLogger(__name__)
    logger.info("Upload document endpoint called")
    
    if request.method != 'POST':
        logger.warning(f"Invalid method: {request.method}")
        return JsonResponse(
            {'status': 'error', 'message': 'Only POST method is allowed'}, 
            status=405
        )
    
    if 'file' not in request.FILES:
        logger.warning("No file part in the request")
        return JsonResponse(
            {'status': 'error', 'message': 'No file part'}, 
            status=400
        )
    
    file = request.FILES['file']
    if not file:
        logger.warning("No file selected")
        return JsonResponse(
            {'status': 'error', 'message': 'No file selected'}, 
            status=400
        )

    # File validation
    ALLOWED_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg']
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

    file_name = file.name
    file_ext = os.path.splitext(file_name)[1].lower()

    if file_ext not in ALLOWED_EXTENSIONS:
        logger.warning(f"Invalid file extension: {file_ext}. Allowed: {ALLOWED_EXTENSIONS}")
        return JsonResponse(
            {'status': 'error', 'message': f"Invalid file type. Allowed extensions are: {', '.join(ALLOWED_EXTENSIONS)}"},
            status=400
        )

    if file.size > MAX_FILE_SIZE:
        logger.warning(f"File size exceeds limit: {file.size} bytes. Max: {MAX_FILE_SIZE} bytes")
        return JsonResponse(
            {'status': 'error', 'message': f"File is too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)}MB."},
            status=400
        )
    
    try:
        logger.info(f"Processing file upload: {file.name} ({file.size} bytes)")
        
        safe_name = f"{uuid.uuid4().hex}{file_ext}"
        
        # Ensure the upload directory exists
        upload_dir = settings.PRIVATE_FILE_STORAGE
        logger.info(f"Upload directory: {upload_dir}")
        
        try:
            os.makedirs(upload_dir, exist_ok=True)
            logger.info(f"Directory created or exists: {upload_dir}")
        except Exception as e:
            logger.error(f"Failed to create directory {upload_dir}: {str(e)}")
            raise Exception(f"Failed to create upload directory: {str(e)}")
        
        # Create the full save path
        save_path = os.path.join(upload_dir, safe_name)
        logger.info(f"Saving file to: {save_path}")
        
        # Save the file in chunks to handle large files
        try:
            with open(save_path, 'wb+') as destination:
                for chunk in file.chunks():
                    destination.write(chunk)
            logger.info("File saved successfully")
            
            return JsonResponse({
                'status': 'ok', 
                'filename': file_name,
                'saved_as': safe_name,
                'path': save_path
            })
            
        except IOError as e:
            logger.error(f"Failed to save file {save_path}: {str(e)}")
            raise Exception(f"Failed to save file: {str(e)}")
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error in file upload: {error_msg}", exc_info=True)
        return JsonResponse(
            {'status': 'error', 'message': error_msg}, 
            status=500
        )


    
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
                
                # For UNKNOWN intents, return the AI response directly
                if intent_type == 'UNKNOWN':
                    return Response({
                        'conversation_id': conversation.id,
                        'message': ai_response,
                        'intent_type': 'GENERAL_RESPONSE'
                    })
                    
                # Convert intent_type to the expected format for known intents
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
        # print("handling transaction data") # Removed
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

        # Create a pending transaction with all extracted details
        # Actual Transaction creation and balance updates will happen upon confirmation
        PendingTransaction.objects.create(
            user=user,
            conversation=self.current_conversation,
            date=transaction_date,
            description=extracted_data.get('description', ''),
            category=extracted_data.get('category'), # Ensures None is passed if key exists and is None, or if key is missing
            amount=amount, # This is the parsed Decimal amount
            transaction_type=transaction_type, # INCOME or EXPENSE
            payment_method=extracted_data.get('payment_method', ''),
            reference_number=extracted_data.get('reference_number', ''),
            notes=extracted_data.get('notes', ''), # Added notes field
            party=customer_name if transaction_type == 'INCOME' else vendor_name,
            # Storing customer/vendor instances directly if models are updated,
            # otherwise, party field (name) is used and objects are fetched/created on confirmation.
            # For now, assuming 'party' (CharField) is sufficient for PendingTransaction.
            # customer=customer, # If PendingTransaction model is updated to link Customer
            # vendor=vendor,     # If PendingTransaction model is updated to link Vendor
            raw_data=json.dumps(extracted_data) # Store the raw extracted data for reference
        )
        
        # Return the original AI response from Gemini, which should ask for confirmation.
        # No modification to ai_response here regarding recording, balance updates, or Sheets sync.
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
            # Prepare Transaction data from PendingTransaction
            transaction_data_for_create = {
                'user': request.user,
                'date': pending_transaction.date,
                'description': pending_transaction.description,
                'category': pending_transaction.category,
                'transaction_type': pending_transaction.transaction_type,
                'amount': pending_transaction.amount, # Using .amount as per model
                'payment_method': pending_transaction.payment_method,
                'reference_number': pending_transaction.reference_number,
                'notes': pending_transaction.notes if hasattr(pending_transaction, 'notes') else '' # Check if notes exists
            }

            customer = None
            vendor = None

            if pending_transaction.party and pending_transaction.party.strip() != "":
                party_name = pending_transaction.party.strip()
                if pending_transaction.transaction_type == 'INCOME':
                    customer, _ = Customer.objects.get_or_create(
                        user=request.user,
                        name=party_name,
                        defaults={'email': '', 'phone': ''} # Provide defaults
                    )
                    transaction_data_for_create['customer'] = customer
                elif pending_transaction.transaction_type == 'EXPENSE':
                    vendor, _ = Vendor.objects.get_or_create(
                        user=request.user,
                        name=party_name,
                        defaults={'email': '', 'phone': ''} # Provide defaults
                    )
                    transaction_data_for_create['vendor'] = vendor
            
            # Create the actual Transaction
            transaction = Transaction.objects.create(**transaction_data_for_create)

            # Update Balances
            if customer and transaction.transaction_type == 'INCOME':
                if customer.total_received is None:
                    customer.total_received = Decimal('0.00')
                customer.total_received += transaction.amount
                customer.save()
            elif vendor and transaction.transaction_type == 'EXPENSE':
                if vendor.total_paid is None:
                    vendor.total_paid = Decimal('0.00')
                vendor.total_paid += transaction.amount
                vendor.save()

            # Google Sheets Sync
            if self.sheets_enabled:
                try:
                    sheets_transaction_data = {
                        'date': transaction.date.strftime('%Y-%m-%d'),
                        'description': transaction.description,
                        'category': transaction.category,
                        'transaction_type': transaction.transaction_type,
                        'amount': float(transaction.amount),
                        'payment_method': transaction.payment_method or '',
                        'reference_number': transaction.reference_number or '',
                        'customer': customer.name if customer else '',
                        'vendor': vendor.name if vendor else '',
                        'notes': transaction.notes or ''
                    }
                    self.sheets_service.add_transaction(sheets_transaction_data)

                    if customer:
                        customer_sheets_data = {
                            'name': customer.name,
                            'email': customer.email or '',
                            'phone': customer.phone or '',
                            'gst_number': customer.gst_number or '',
                            'address': customer.address or '',
                            'total_receivable': float(customer.total_receivable or '0'),
                            'total_received': float(customer.total_received or '0'),
                            'outstanding_balance': float(customer.outstanding_balance or '0')
                        }
                        self.sheets_service.add_customer(customer_sheets_data)
                    elif vendor:
                        vendor_sheets_data = {
                            'name': vendor.name,
                            'email': vendor.email or '',
                            'phone': vendor.phone or '',
                            'gst_number': vendor.gst_number or '',
                            'address': vendor.address or '',
                            'total_payable': float(vendor.total_payable or '0'),
                            'total_paid': float(vendor.total_paid or '0'),
                            'outstanding_balance': float(vendor.outstanding_balance or '0')
                        }
                        self.sheets_service.add_vendor(vendor_sheets_data)
                except Exception as e:
                    logging.error(f"Google Sheets sync failed during transaction confirmation: {str(e)}")

            # Add confirmation message to conversation
            conversation = pending_transaction.conversation
            Message.objects.create(
                conversation=conversation,
                sender='AI',
                content=f"✅ Transaction confirmed and added to your records:\n\n"
                        f"• Date: {pending_transaction.date}\n"
                        f"• Description: {pending_transaction.description}\n"
                        f"• Amount: ₹{pending_transaction.amount:,.2f}\n"
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



@login_required
def financial_summary(request):
    # Get data
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    # Transactions
    transactions = Transaction.objects.filter(
        user=request.user,
        date__gte=thirty_days_ago
    ).order_by('-date')
    
    # Get the date 30 days ago for overdue calculation
    thirty_days_ago = timezone.now().date() - timedelta(days=30)
    
    # Customers with overdue invoices
    customers = Customer.objects.filter(
        user=request.user, 
        is_active=True
    ).annotate(
        overdue_invoices=Count(
            'invoices', 
            filter=Q(
                invoices__due_date__lt=timezone.now().date(),
                invoices__amount_received__lt=F('invoices__amount_due')
            )
        )
    )
    
    # Vendors with overdue bills
    vendors = Vendor.objects.filter(
        user=request.user, 
        is_active=True
    ).annotate(
        overdue_bills=Count(
            'bills',
            filter=Q(
                bills__due_date__lt=timezone.now().date(),
                bills__amount_paid__lt=F('bills__amount_due')
            )
        )
    )
    
    # Prepare data for analysis
    transaction_data = [{
        'date': tx.date.strftime('%Y-%m-%d'),
        'amount': float(tx.amount),
        'category': tx.category,
        'type': tx.transaction_type,
        'party': tx.customer.name if tx.customer else tx.vendor.name if tx.vendor else ''
    } for tx in transactions]
    
    customer_data = [{
        'name': c.name,
        'balance': float(c.outstanding_balance),
        'overdue': c.overdue_invoices
    } for c in customers]
    
    vendor_data = [{
        'name': v.name,
        'balance': float(v.outstanding_balance),
        'overdue': v.overdue_bills
    } for v in vendors]
    
    # Print debug information
    # Removed print statements
    
    # Generate insights
    gemini_service = GeminiService()
    insights = gemini_service.generate_actionable_insights(
        transaction_data,
        customer_data,
        vendor_data
    )
    
    return render(request, 'summary.html', {
        'insights': insights,
        'total_income': sum(t.amount for t in transactions if t.transaction_type == 'INCOME'),
        'total_expenses': sum(t.amount for t in transactions if t.transaction_type == 'EXPENSE')
    })