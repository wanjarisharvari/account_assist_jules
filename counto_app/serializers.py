from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Conversation, Message, Transaction, PendingTransaction

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