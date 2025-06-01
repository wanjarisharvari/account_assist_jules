import random
from decimal import Decimal
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.utils import timezone
# Assuming your models are in counto_app.models
from counto_app.models import Customer, Vendor, Transaction

class Command(BaseCommand):
    help = 'Creates sample data (customers, vendors, transactions) for a specified user.'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='The username of the user for whom to create sample data.')

    def handle(self, *args, **options):
        username = options['username']
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'User "{username}" does not exist.')

        self.stdout.write(f'Creating sample data for user "{username}"...')

        # --- Start of moved create_sample_data logic ---

        # Clear existing sample data for this user (optional, but good for idempotency)
        # This is a simple way; more specific sample data flagging would be better in a real app.
        Transaction.objects.filter(user=user, description__icontains='Sample').delete()
        Customer.objects.filter(user=user, name__startswith='Sample Customer').delete()
        Vendor.objects.filter(user=user, name__startswith='Sample Vendor').delete()


        customers = []
        for i in range(3):
            customer, created = Customer.objects.get_or_create(
                user=user,
                name=f"Sample Customer {i+1}",
                defaults={
                    'email': f"samplecustomer{i+1}@example.com",
                    'phone': f"123-456-{7890+i}",
                    'total_receivable': Decimal(str(random.randint(5000, 15000))),
                    'total_received': Decimal(str(random.randint(2000, 4000)))
                }
            )
            customers.append(customer)

        vendors = []
        for i in range(3):
            vendor, created = Vendor.objects.get_or_create(
                user=user,
                name=f"Sample Vendor {i+1}",
                defaults={
                    'email': f"samplevendor{i+1}@example.com",
                    'phone': f"987-654-{3210+i}",
                    'total_payable': Decimal(str(random.randint(3000, 10000))),
                    'total_paid': Decimal(str(random.randint(1000, 2500)))
                }
            )
            vendors.append(vendor)

        income_categories = ['Sample Salary', 'Sample Freelance Work', 'Sample Investments']
        expense_categories = ['Sample Groceries', 'Sample Rent', 'Sample Utilities']

        now_date = timezone.now().date() # Renamed from 'now' to avoid conflict if timezone.now is used directly
        start_date = now_date - timedelta(days=180)

        # Create fewer transactions for sample data to keep it manageable
        for i in range(15): # Reduced from 50
            transaction_date = start_date + timedelta(days=random.randint(0, 180))
            transaction_type = random.choice(['INCOME', 'EXPENSE'])

            description_suffix = f" - Sample {transaction_date.strftime('%b')}"

            if transaction_type == 'INCOME':
                category = random.choice(income_categories)
                amount = Decimal(str(random.randint(1000, 5000)))
                customer = random.choice(customers) if customers and random.random() > 0.3 else None
                vendor_obj = None # Renamed to avoid conflict
                description = f"{category}{description_suffix}"
            else:  # EXPENSE
                category = random.choice(expense_categories)
                amount = Decimal(str(random.randint(500, 3000)))
                customer = None
                vendor_obj = random.choice(vendors) if vendors and random.random() > 0.3 else None # Renamed
                description = f"{category}{description_suffix}"

            Transaction.objects.create(
                user=user,
                date=transaction_date,
                description=description,
                category=category,
                transaction_type=transaction_type,
                amount=amount,
                customer=customer,
                vendor=vendor_obj, # Use renamed variable
                payment_method=random.choice(['Cash', 'Credit Card', 'Bank Transfer', 'UPI'])
            )
        # --- End of moved create_sample_data logic ---

        self.stdout.write(self.style.SUCCESS(f'Successfully created sample data for user "{username}".'))
