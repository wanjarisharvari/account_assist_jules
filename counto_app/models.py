from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from decimal import Decimal

# Create your models here.
class Conversation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"Conversation {self.id} - {self.user.username}"

class Message(models.Model):
    SENDER_CHOICES = [
        ('USER', 'User'),
        ('AI', 'AI')
    ]
    
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=5, choices=SENDER_CHOICES)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['timestamp']
        
    def __str__(self):
        return f"{self.sender} message in conversation {self.conversation_id}"

class PendingTransaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    date = models.DateField(null=True, blank=True)
    description = models.CharField(max_length=255, null=True, blank=True)
    category = models.CharField(max_length=100, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    transaction_type = models.CharField(max_length=10, null=True, blank=True)
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    reference_number = models.CharField(max_length=50, blank=True, null=True)
    party = models.CharField(max_length=100, blank=True, null=True)
    
    def __str__(self):
        return f"Pending: {self.description if self.description else 'New Transaction'}"


class Customer(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    gst_number = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    
    # Balance tracking
    total_receivable = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_received = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'name']),
            models.Index(fields=['user', 'is_active']),
        ]

    def __str__(self):
        return self.name

    @property
    def outstanding_balance(self):
        """Amount still to be received from customer"""
        # Ensure both values are Decimal before subtraction
        if not isinstance(self.total_receivable, Decimal):
            total_receivable = Decimal(str(self.total_receivable or '0'))
        else:
            total_receivable = self.total_receivable
            
        if not isinstance(self.total_received, Decimal):
            total_received = Decimal(str(self.total_received or '0'))
        else:
            total_received = self.total_received
            
        return (total_receivable - total_received).quantize(Decimal('0.00'))

    @property
    def is_overdue(self):
        """Check if customer has overdue payments"""
        from django.utils import timezone
        from datetime import timedelta
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        
        return self.invoices.filter(
            date__lt=thirty_days_ago,
            amount_received__lt=models.F('amount_due')
        ).exists()

    def update_balances(self):
        """Recalculate balance from related transactions"""
        invoices = self.invoices.aggregate(
            total_due=models.Sum('amount_due', default=0),
            total_received=models.Sum('amount_received', default=0)
        )
        self.total_receivable = invoices['total_due']
        self.total_received = invoices['total_received']
        self.save()


class Vendor(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    gst_number = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    
    # Balance tracking
    total_payable = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'name']),
            models.Index(fields=['user', 'is_active']),
        ]

    def __str__(self):
        return self.name

    @property
    def outstanding_balance(self):
        """Amount still to be paid to vendor"""
        # Ensure both values are Decimal before subtraction
        if not isinstance(self.total_payable, Decimal):
            total_payable = Decimal(str(self.total_payable or '0'))
        else:
            total_payable = self.total_payable
            
        if not isinstance(self.total_paid, Decimal):
            total_paid = Decimal(str(self.total_paid or '0'))
        else:
            total_paid = self.total_paid
            
        return (total_payable - total_paid).quantize(Decimal('0.00'))

    def update_balances(self):
        """Recalculate balance from related transactions"""
        bills = self.bills.aggregate(
            total_due=models.Sum('amount_due', default=0),
            total_paid=models.Sum('amount_paid', default=0)
        )
        self.total_payable = bills['total_due']
        self.total_paid = bills['total_paid']
        self.save()


class Transaction(models.Model):
    """Simplified transaction model - just records what happened"""
    TYPE_CHOICES = [
        ('INCOME', 'Income'),
        ('EXPENSE', 'Expense'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    description = models.CharField(max_length=255)
    category = models.CharField(max_length=100, blank=True)
    transaction_type = models.CharField(max_length=7, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Optional party reference (but not required)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Payment details
    payment_method = models.CharField(max_length=100, blank=True, null=True)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['user', 'transaction_type']),
            models.Index(fields=['user', 'category']),
            models.Index(fields=['date', 'transaction_type']),
        ]

    def __str__(self):
        party = f" - {self.customer or self.vendor}" if (self.customer or self.vendor) else ""
        return f"{self.transaction_type} - ₹{self.amount} - {self.description}{party}"

    def clean(self):
        if self.customer and self.vendor:
            raise ValidationError("Transaction cannot have both customer and vendor")


class Invoice(models.Model):
    """Track what customers owe"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='invoices')
    
    invoice_number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    
    description = models.CharField(max_length=255)
    amount_due = models.DecimalField(max_digits=12, decimal_places=2)
    amount_received = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'customer']),
            models.Index(fields=['date', 'due_date']),
        ]

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.customer.name}"

    @property
    def balance_due(self):
        return self.amount_due - self.amount_received

    @property
    def is_paid(self):
        return self.amount_received >= self.amount_due

    @property
    def is_overdue(self):
        from django.utils import timezone
        return self.due_date and self.due_date < timezone.now().date() and not self.is_paid

    def add_payment(self, amount, transaction=None):
        """Add a payment to this invoice"""
        self.amount_received += amount
        self.save()
        
        # Create payment record
        InvoicePayment.objects.create(
            invoice=self,
            amount=amount,
            transaction=transaction,
            date=transaction.date if transaction else timezone.now().date()
        )
        
        # Update customer balance
        self.customer.update_balances()


class Bill(models.Model):
    """Track what we owe vendors"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='bills')
    
    bill_number = models.CharField(max_length=50)
    date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    
    description = models.CharField(max_length=255)
    amount_due = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'vendor']),
            models.Index(fields=['date', 'due_date']),
        ]
        unique_together = ['user', 'bill_number']

    def __str__(self):
        return f"Bill {self.bill_number} - {self.vendor.name}"

    @property
    def balance_due(self):
        return self.amount_due - self.amount_paid

    @property
    def is_paid(self):
        return self.amount_paid >= self.amount_due

    @property
    def is_overdue(self):
        from django.utils import timezone
        return self.due_date and self.due_date < timezone.now().date() and not self.is_paid

    def add_payment(self, amount, transaction=None):
        """Add a payment to this bill"""
        self.amount_paid += amount
        self.save()
        
        # Create payment record
        BillPayment.objects.create(
            bill=self,
            amount=amount,
            transaction=transaction,
            date=transaction.date if transaction else timezone.now().date()
        )
        
        # Update vendor balance
        self.vendor.update_balances()


class InvoicePayment(models.Model):
    """Track payments received against invoices"""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    transaction = models.ForeignKey(Transaction, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment ₹{self.amount} for {self.invoice.invoice_number}"


class BillPayment(models.Model):
    """Track payments made against bills"""
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    transaction = models.ForeignKey(Transaction, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment ₹{self.amount} for {self.bill.bill_number}"
