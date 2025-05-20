from django.contrib import admin
from .models import Conversation, Message, Transaction, PendingTransaction

# Register your models here.
admin.site.register(Transaction)


