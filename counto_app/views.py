from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages

# Create your views here.
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
    
    return render(request, 'dashboard.html', {'user': request.user})

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import datetime

from .models import Conversation, Message, Transaction, PendingTransaction
from .serializers import (
    ConversationSerializer, 
    MessageSerializer, 
    TransactionSerializer, 
    PendingTransactionSerializer,
    MessageInputSerializer,
    TransactionConfirmSerializer
)
from .services.gemini_services import GeminiService
from .services.sheets_services import GoogleSheetsService  # Re-enabled Google Sheets

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
            import logging
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
            serializer = MessageInputSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            user_message = serializer.validated_data['content']
            conversation_id = serializer.validated_data.get('conversation_id')
            
            # Get or create conversation
            if conversation_id:
                conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
            else:
                conversation = Conversation.objects.create(user=request.user)
                
            # Check if there's a pending transaction for this conversation - this helps with follow-up responses
            pending_transaction = None
            try:
                pending_transaction = PendingTransaction.objects.filter(conversation=conversation).order_by('-created_at').first()
            except:
                pass
            
            # Save user message
            Message.objects.create(
                conversation=conversation,
                sender='USER',
                content=user_message
            )
            
            # Get conversation history
            history = Message.objects.filter(conversation=conversation).values('sender', 'content')
            
            # Before sending to Gemini, first check if this is a simple command we can handle directly
            # First, check for confirmation/rejection of pending transactions
            confirmation_words = ["yes", "confirm", "record it", "record this", "save it", "save this", "ok", "okay", "approve"]
            cancellation_words = ["no", "cancel", "don't record", "do not record", "delete", "remove"]
            is_direct_command = False
            ai_response = None
            
            # Check if this is a confirmation of a pending transaction
            if pending_transaction and (user_message.lower().strip() in confirmation_words or any(word in user_message.lower() for word in confirmation_words)):
                is_direct_command = True
                print(f"DEBUG: Detected confirmation command for pending transaction {pending_transaction.id}")
                
                try:
                    # Create a Transaction record in our database
                    transaction = Transaction.objects.create(
                        user=request.user,
                        date=pending_transaction.date,
                        description=pending_transaction.description,
                        category=pending_transaction.category,
                        amount=pending_transaction.amount,
                        transaction_type=pending_transaction.transaction_type,
                        payment_method=pending_transaction.payment_method,
                        reference_number=pending_transaction.reference_number,
                        party=pending_transaction.party
                    )
                    
                    # Try Google Sheets if enabled
                    sheets_success = False
                    sheets_error = None
                    if hasattr(self, 'sheets_enabled') and self.sheets_enabled:
                        try:
                            transaction_data = {
                                'date': pending_transaction.date,
                                'description': pending_transaction.description,
                                'category': pending_transaction.category,
                                'amount': pending_transaction.amount,
                                'transaction_type': pending_transaction.transaction_type,
                                'payment_method': pending_transaction.payment_method,
                                'reference_number': pending_transaction.reference_number,
                                'party': pending_transaction.party
                            }
                            sheets_success = self.sheets_service.add_transaction(transaction_data)
                        except Exception as e:
                            import logging
                            sheets_error = str(e)
                            logging.error(f"Failed to add to Google Sheets: {sheets_error}")
                    
                    # Prepare confirmation message
                    ai_response = f"✅ Transaction confirmed and saved successfully! I've recorded:\n\n"
                    ai_response += f"• {pending_transaction.date}: {pending_transaction.description}\n"
                    ai_response += f"• Amount: {pending_transaction.amount}\n"
                    ai_response += f"• Category: {pending_transaction.category or 'Uncategorized'}\n"
                    
                    if sheets_success:
                        ai_response += "\nThe transaction has been saved both locally and to your Google Sheets."
                    elif sheets_error:
                        ai_response += "\nNote: The transaction was saved locally but couldn't be added to Google Sheets due to an error."
                    else:
                        ai_response += "\nThe transaction has been saved to your local database."
                        
                    # Delete the pending transaction
                    pending_transaction.delete()
                except Exception as e:
                    import logging
                    logging.error(f"Error confirming transaction: {str(e)}")
                    ai_response = f"I encountered an error while trying to save your transaction: {str(e)}"
            
            # Check if this is a cancellation of a pending transaction
            elif pending_transaction and (user_message.lower().strip() in cancellation_words or any(word in user_message.lower() for word in cancellation_words)):
                is_direct_command = True
                print(f"DEBUG: Detected cancellation command for pending transaction {pending_transaction.id}")
                
                # Delete the pending transaction
                pending_transaction.delete()
                ai_response = "❌ Transaction cancelled. Is there anything else you'd like to do?"
            
            # Check for field updates
            is_field_update = False
            update_field = None
            update_value = None
            
            if not is_direct_command and pending_transaction:
                if "payment method" in user_message.lower() and ("is" in user_message.lower() or "was" in user_message.lower()):
                    is_field_update = True
                    update_field = 'payment_method'
                    update_value = user_message.lower().split("was")[-1].strip() if "was" in user_message.lower() else user_message.lower().split("is")[-1].strip()
                elif "party" in user_message.lower() and ("is" in user_message.lower() or "was" in user_message.lower()):
                    is_field_update = True
                    update_field = 'party'
                    update_value = user_message.lower().split("was")[-1].strip() if "was" in user_message.lower() else user_message.lower().split("is")[-1].strip()
            
            # Try to handle field updates we detected before
            try:
                if is_field_update and update_field and update_value:
                    # Update the pending transaction
                    if update_field == 'payment_method':
                        pending_transaction.payment_method = update_value.upper()
                    elif update_field == 'party':
                        pending_transaction.party = update_value.title()
                    pending_transaction.save()
                    
                    # Generate a confirmation response
                    ai_response = f"I've updated the {update_field.replace('_', ' ')} to {update_value}. Here's the updated transaction:\n\n"
                    ai_response += f"Date: {pending_transaction.date}\n"
                    ai_response += f"Description: {pending_transaction.description}\n"
                    ai_response += f"Category: {pending_transaction.category}\n"
                    ai_response += f"Amount: {pending_transaction.amount}\n"
                    ai_response += f"Type: {pending_transaction.transaction_type}\n"
                    ai_response += f"Party: {pending_transaction.party or 'Not specified'}\n"
                    ai_response += f"Payment Method: {pending_transaction.payment_method or 'Not specified'}\n\n"
                    ai_response += "Would you like me to record this transaction with these details?"
                    
                    extracted_data = {}
                    is_query = False
            except Exception as e:
                # Log the error and return a specific error response
                import logging
                logging.error(f"Error processing field update: {str(e)}")
                return Response({
                    'error': 'Error updating transaction field',
                    'detail': str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
            # If we got a direct command response, skip Gemini processing
            if is_direct_command:
                extracted_data = {}
                is_query = False
            # If no direct command and Gemini wasn't called yet, call it now
            elif not ai_response:
                try:
                    ai_response, extracted_data, is_query = self.gemini_service.process_message(
                        user_message, 
                        list(history)
                    )
                except Exception as e:
                    import logging
                    logging.error(f"Gemini API error: {str(e)}")
                    return Response({
                        'error': 'Error processing message with AI service',
                        'detail': str(e)
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # If it's a query, fetch data from Google Sheets if available
            if is_query:
                if hasattr(self, 'sheets_enabled') and self.sheets_enabled:
                    try:
                        # Try to get transactions from Google Sheets
                        transactions = self.sheets_service.get_all_transactions()
                        
                        # Append financial data to response for user's reference
                        if transactions:
                            ai_response += "\n\nHere's the data I found:\n"
                            for idx, tx in enumerate(transactions[:5]):  # Show only first 5 for brevity
                                ai_response += f"{idx+1}. {tx.get('date', 'N/A')} - {tx.get('description', 'N/A')} - {tx.get('amount', 'N/A')} ({tx.get('category', 'N/A')})\n"
                            
                            if len(transactions) > 5:
                                ai_response += f"...and {len(transactions)-5} more transactions."
                    except Exception as e:
                        # Log the error but continue
                        import logging
                        logging.error(f"Google Sheets error: {str(e)}")
                        ai_response += "\n\nI tried to retrieve your financial data but encountered an error with Google Sheets. Your transaction will still be saved locally."
            # If it's a data entry (transaction), create and save it immediately
            elif extracted_data:
                try:
                    # Handle date conversion
                    date_str = extracted_data.get('date')
                    transaction_date = None
                    
                    if date_str:
                        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%m-%d-%Y']:
                            try:
                                transaction_date = datetime.strptime(date_str, fmt).date()
                                break
                            except ValueError:
                                continue
                    
                    # Use current date if none provided
                    if not transaction_date:
                        transaction_date = datetime.now().date()
                    
                    # Handle amount conversion
                    amount_str = extracted_data.get('amount', '0')
                    if amount_str:
                        # Remove currency symbols and commas
                        amount_str = str(amount_str).replace('$', '').replace('€', '').replace('£', '').replace(',', '')
                        try:
                            amount = float(amount_str)
                        except ValueError:
                            amount = 0
                    else:
                        amount = 0
                    
                    # Extract the transaction data
                    transaction_data = {
                        'date': transaction_date,
                        'description': extracted_data.get('description', ''),
                        'category': extracted_data.get('category', ''),
                        'amount': amount,
                        'transaction_type': extracted_data.get('transaction_type', 'EXPENSE'),
                        'payment_method': extracted_data.get('payment_method', ''),
                        'reference_number': extracted_data.get('reference_number', ''),
                        'party': extracted_data.get('party', '')
                    }
                    
                    # Create transaction record in database
                    transaction = Transaction.objects.create(
                        user=request.user,
                        **transaction_data
                    )
                    
                    # Try to save to Google Sheets if enabled
                    sheets_success = False
                    sheets_error = None
                    if hasattr(self, 'sheets_enabled') and self.sheets_enabled:
                        try:
                            sheets_success = self.sheets_service.add_transaction(transaction_data)
                        except Exception as e:
                            import logging
                            sheets_error = str(e)
                            logging.error(f"Failed to add to Google Sheets: {sheets_error}")
                    
                    # Modify the response to indicate the transaction was saved
                    if "Would you like me to record this transaction?" in ai_response:
                        # Replace the confirmation request with a success message
                        ai_response = ai_response.split("Would you like me to record this transaction?")[0]
                        ai_response += f"\n\n✅ Transaction saved automatically!\n"
                        
                        if sheets_success:
                            ai_response += "\nThe transaction has been saved both to your database and Google Sheets."
                        elif sheets_error:
                            ai_response += f"\nNote: The transaction was saved locally but couldn't be added to Google Sheets due to an error: {sheets_error}"
                        else:
                            ai_response += "\nThe transaction has been saved to your local database."
                except Exception as e:
                    # Log the error but continue
                    import logging
                    logging.error(f"Error creating transaction: {str(e)}")
                    ai_response += f"\n\nI tried to create a transaction record but encountered an error: {str(e)}"
            
            # Save AI response
            Message.objects.create(
                conversation=conversation,
                sender='AI',
                content=ai_response
            )
            
            # Update conversation timestamp
            conversation.updated_at = timezone.now()
            conversation.save()
            
            return Response({
                'conversation_id': conversation.id,
                'message': ai_response,
                'is_query': is_query,
                'has_pending_transaction': not is_query and bool(extracted_data)
            })
            
        except Exception as e:
            # Catch any unexpected errors and log them
            import logging
            logging.error(f"Unexpected error in MessageView.post: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return Response({
                'error': 'An unexpected error occurred',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
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
            import logging
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
                'amount': pending_transaction.amount,
                'transaction_type': pending_transaction.transaction_type,
                'payment_method': pending_transaction.payment_method,
                'reference_number': pending_transaction.reference_number,
                'party': pending_transaction.party
            }
            
            # Try to save to Google Sheets if enabled
            sheets_success = False
            if hasattr(self, 'sheets_enabled') and self.sheets_enabled:
                try:
                    sheets_success = self.sheets_service.add_transaction(transaction_data)
                except Exception as e:
                    import logging
                    logging.error(f"Failed to add to Google Sheets: {str(e)}")
            
            # Always succeed locally even if Google Sheets fails
            success = True
            
            if success:
                # Create a Transaction record in our database too
                transaction = Transaction.objects.create(
                    user=request.user,
                    date=pending_transaction.date,
                    description=pending_transaction.description,
                    category=pending_transaction.category,
                    amount=pending_transaction.amount,
                    transaction_type=pending_transaction.transaction_type,
                    payment_method=pending_transaction.payment_method,
                    reference_number=pending_transaction.reference_number,
                    party=pending_transaction.party
                )
                
                # Add confirmation message to conversation
                conversation = pending_transaction.conversation
                Message.objects.create(
                    conversation=conversation,
                    sender='AI',
                    content=f"✅ Transaction confirmed and added to your records:\n\n"
                            f"• {pending_transaction.date}: {pending_transaction.description}\n"
                            f"• Amount: {pending_transaction.amount}\n"
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