from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.utils import timezone
from datetime import datetime
import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

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
from .services.gemini_services import GeminiService
from .services.sheets_services import GoogleSheetsService  # Re-enabled Google Sheets

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
        expected_amount = self._parse_amount(extracted_data.get('expected_amount', extracted_data.get('amount', '0')))
        paid_amount = self._parse_amount(extracted_data.get('paid_amount', expected_amount))
        
        # Determine transaction status
        status = 'PAID'  # Default
        if paid_amount == 0:
            status = 'PENDING'
        elif paid_amount < expected_amount:
            status = 'PARTIAL'
        
        # Get or create customer/vendor if applicable
        customer = None
        vendor = None
        
        if extracted_data.get('customer_name'):
            customer, _ = Customer.objects.get_or_create(
                user=user,
                name=extracted_data.get('customer_name'),
                defaults={
                    'email': extracted_data.get('customer_email', ''),
                    'phone': extracted_data.get('customer_phone', ''),
                    'gst_number': extracted_data.get('customer_gst', ''),
                    'address': extracted_data.get('customer_address', '')
                }
            )
        
        if extracted_data.get('vendor_name'):
            vendor, _ = Vendor.objects.get_or_create(
                user=user,
                name=extracted_data.get('vendor_name'),
                defaults={
                    'email': extracted_data.get('vendor_email', ''),
                    'phone': extracted_data.get('vendor_phone', ''),
                    'gst_number': extracted_data.get('vendor_gst', ''),
                    'address': extracted_data.get('vendor_address', '')
                }
            )

        # Create transaction record
        transaction_data = {
            'date': transaction_date,
            'description': extracted_data.get('description', ''),
            'category': extracted_data.get('category', ''),
            'transaction_type': extracted_data.get('transaction_type', 'EXPENSE'),
            'expected_amount': expected_amount,
            'paid_amount': paid_amount,
            'status': status,
            'customer': customer,
            'vendor': vendor,
            'payment_method': extracted_data.get('payment_method', ''),
            'reference_number': extracted_data.get('reference_number', '')
        }

        # Save to database
        transaction = Transaction.objects.create(
            user=user,
            **transaction_data
        )

        # Sync with Google Sheets
        sheets_success = False
        sheets_error = None
        if self.sheets_enabled:
            try:
                sheets_data = transaction_data.copy()
                # Convert model instances to names for sheets
                if customer:
                    sheets_data['customer'] = customer.name
                if vendor:
                    sheets_data['vendor'] = vendor.name
                    
                sheets_success = self.sheets_service.add_transaction(sheets_data)
            except Exception as e:
                sheets_error = str(e)
                logging.error(f"Google Sheets sync failed: {sheets_error}")

        # Update AI response
        if "Would you like me to record this transaction?" in ai_response:
            ai_response = ai_response.split("Would you like me to record this transaction?")[0]
            ai_response += "\n\n✅ Transaction saved automatically!\n"
            
            if sheets_success:
                ai_response += "\nSaved to database and Google Sheets."
            elif sheets_error:
                ai_response += f"\nNote: Google Sheets sync failed ({sheets_error})"
            else:
                ai_response += "\nSaved to local database."
                
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
            # Create new customer
            customer = Customer.objects.create(user=user, **customer_data)
            operation = "created"

        # Sync with Google Sheets
        sheets_success = False
        sheets_error = None
        if self.sheets_enabled:
            try:
                sheets_success = self.sheets_service.add_customer(customer_data)
            except Exception as e:
                sheets_error = str(e)
                logging.error(f"Google Sheets sync failed: {sheets_error}")

        # Update AI response
        ai_response += f"\n\n✅ Customer {operation} successfully!\n"
        if sheets_success:
            ai_response += "\nSaved to database and Google Sheets."
        elif sheets_error:
            ai_response += f"\nNote: Google Sheets sync failed ({sheets_error})"
        else:
            ai_response += "\nSaved to local database."
            
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
            # Create new vendor
            vendor = Vendor.objects.create(user=user, **vendor_data)
            operation = "created"

        # Sync with Google Sheets
        sheets_success = False
        sheets_error = None
        if self.sheets_enabled:
            try:
                sheets_success = self.sheets_service.add_vendor(vendor_data)
            except Exception as e:
                sheets_error = str(e)
                logging.error(f"Google Sheets sync failed: {sheets_error}")

        # Update AI response
        ai_response += f"\n\n✅ Vendor {operation} successfully!\n"
        if sheets_success:
            ai_response += "\nSaved to database and Google Sheets."
        elif sheets_error:
            ai_response += f"\nNote: Google Sheets sync failed ({sheets_error})"
        else:
            ai_response += "\nSaved to local database."
            
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
                    amount_str = f"₹{tx.get('paid_amount', 'N/A')}/{tx.get('expected_amount', tx.get('paid_amount', 'N/A'))}"
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
            return 0.0
        
        # Handle string representation of numbers
        if isinstance(amount_str, str):
            # Remove currency symbols, commas, and any whitespace
            amount_str = amount_str.replace('$', '').replace('€', '').replace('£', '').replace('₹', '').replace(',', '').strip()
            
            # If empty after cleaning, return 0
            if not amount_str:
                return 0.0
                
        try:
            return float(amount_str)
        except (ValueError, TypeError):
            logging.warning(f"Could not convert amount '{amount_str}' to float, using 0")
            return 0.0


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