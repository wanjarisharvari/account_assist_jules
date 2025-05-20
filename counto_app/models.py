from django.db import models
from django.contrib.auth.models import User

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
    
class Transaction(models.Model):
    TYPE_CHOICES = [
        ('INCOME', 'Income'),
        ('EXPENSE', 'Expense'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    description = models.CharField(max_length=500)
    category = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    payment_method = models.CharField(max_length=500, blank=True, null=True)
    reference_number = models.CharField(max_length=500, blank=True, null=True)
    party = models.CharField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.description} - {self.amount}"
    
class PendingTransaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    date = models.DateField(null=True, blank=True)
    description = models.CharField(max_length=255, null=True, blank=True)
    category = models.CharField(max_length=100, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    transaction_type = models.CharField(max_length=10, null=True, blank=True)
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    reference_number = models.CharField(max_length=50, blank=True, null=True)
    party = models.CharField(max_length=100, blank=True, null=True)
    
    def __str__(self):
        return f"Pending: {self.description if self.description else 'New Transaction'}"


# class Customer(models.Model):
#     user = models.ForeignKey(User, on_delete=models.CASCADE)
#     name = models.CharField(max_length=255)
#     email = models.EmailField(blank=True, null=True)
#     phone = models.CharField(max_length=20, blank=True, null=True)
#     gst_number = models.CharField(max_length=20, blank=True, null=True)
#     address = models.TextField(blank=True, null=True)
#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return self.name


# class Vendor(models.Model):
#     user = models.ForeignKey(User, on_delete=models.CASCADE)
#     name = models.CharField(max_length=255)
#     email = models.EmailField(blank=True, null=True)
#     phone = models.CharField(max_length=20, blank=True, null=True)
#     gst_number = models.CharField(max_length=20, blank=True, null=True)
#     address = models.TextField(blank=True, null=True)
#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return self.name


# class Transaction(models.Model):
#     TYPE_CHOICES = [
#         ('INCOME', 'Income'),
#         ('EXPENSE', 'Expense'),
#     ]

#     STATUS_CHOICES = [
#         ('PENDING', 'Pending'),
#         ('PARTIAL', 'Partial'),
#         ('PAID', 'Paid'),
#     ]

#     user = models.ForeignKey(User, on_delete=models.CASCADE)
#     date = models.DateField()
#     description = models.CharField(max_length=255)
#     category = models.CharField(max_length=100, blank=True)
#     transaction_type = models.CharField(max_length=7, choices=TYPE_CHOICES)

#     expected_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
#     paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

#     status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PAID')

#     customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
#     vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True)

#     payment_method = models.CharField(max_length=100, blank=True, null=True)
#     reference_number = models.CharField(max_length=100, blank=True, null=True)

#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"{self.transaction_type} - ₹{self.paid_amount}/{self.expected_amount or self.paid_amount} - {self.description}"

#     def update_payment_status(self):
#         if self.paid_amount == 0:
#             self.status = 'PENDING'
#         elif self.paid_amount < (self.expected_amount or self.paid_amount):
#             self.status = 'PARTIAL'
#         else:
#             self.status = 'PAID'
#         self.save()
