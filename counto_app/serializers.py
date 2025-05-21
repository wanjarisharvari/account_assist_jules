from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Conversation, Message, Transaction, PendingTransaction, Customer, Vendor

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']
        
class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['id', 'sender', 'content', 'timestamp']
        
class ConversationSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    
    class Meta:
        model = Conversation
        fields = ['id', 'created_at', 'updated_at', 'active', 'messages']

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = '__all__'
        
class PendingTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PendingTransaction
        fields = '__all__'
        
class MessageInputSerializer(serializers.Serializer):
    content = serializers.CharField(required=True)
    conversation_id = serializers.IntegerField(required=False, allow_null=True)
    
class TransactionConfirmSerializer(serializers.Serializer):
    pending_transaction_id = serializers.IntegerField(required=True)
    confirm = serializers.BooleanField(required=True)


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ['id', 'name', 'email', 'phone', 'gst_number', 'address', 'created_at']
        read_only_fields = ['id', 'created_at']


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ['id', 'name', 'email', 'phone', 'gst_number', 'address', 'created_at']
        read_only_fields = ['id', 'created_at']


class TransactionCreateSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    vendor_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    
    class Meta:
        model = Transaction
        fields = [
            'date', 'description', 'category', 'transaction_type',
            'expected_amount', 'paid_amount', 'status', 'payment_method',
            'reference_number', 'customer_name', 'vendor_name'
        ]
    
    def create(self, validated_data):
        customer_name = validated_data.pop('customer_name', None)
        vendor_name = validated_data.pop('vendor_name', None)
        user = self.context['request'].user
        
        # Handle customer
        if customer_name:
            customer, _ = Customer.objects.get_or_create(
                user=user,
                name=customer_name,
                defaults={
                    'email': validated_data.pop('customer_email', ''),
                    'phone': validated_data.pop('customer_phone', ''),
                    'gst_number': validated_data.pop('customer_gst', ''),
                    'address': validated_data.pop('customer_address', '')
                }
            )
            validated_data['customer'] = customer
        
        # Handle vendor
        if vendor_name:
            vendor, _ = Vendor.objects.get_or_create(
                user=user,
                name=vendor_name,
                defaults={
                    'email': validated_data.pop('vendor_email', ''),
                    'phone': validated_data.pop('vendor_phone', ''),
                    'gst_number': validated_data.pop('vendor_gst', ''),
                    'address': validated_data.pop('vendor_address', '')
                }
            )
            validated_data['vendor'] = vendor
        
        return Transaction.objects.create(user=user, **validated_data)