import os
import json
import logging
import re
from datetime import datetime
from typing import Dict, Any, Tuple, List, Optional
from django.conf import settings

# Track whether Gemini API is available
gemini_available = False

# Try to import Gemini, but provide fallback if it's not available or configured properly
try:
    import google.generativeai as genai
    if hasattr(settings, 'GEMINI_API_KEY') and settings.GEMINI_API_KEY:
        # Add debug log for API key
        key_preview = settings.GEMINI_API_KEY[:5] + "..." if settings.GEMINI_API_KEY else "None"
        logging.info(f"Found GEMINI_API_KEY in settings (starts with: {key_preview})")
        print(f"💡 DEBUG: Found API key starting with {key_preview}")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        gemini_available = True
    else:
        print("❌ DEBUG: No GEMINI_API_KEY found in settings - FALLBACK REASON")
        logging.warning("No GEMINI_API_KEY found in settings")
except ImportError:
    print("❌ DEBUG: google.generativeai package not installed - FALLBACK REASON")
    logging.warning("google.generativeai package not installed")

class GeminiService:
    def __init__(self):
        self.use_fallback = True
        self.model = None
        self.initialization_error = None
        
        # Only try to initialize Gemini if the API is available
        if gemini_available:
            print("💡 DEBUG: Gemini API is available, trying to initialize...")
            logging.info("Attempting to initialize Gemini service...")
            try:
                # Try with explicit models/ prefix first
                model_name = "models/gemini-pro"
                logging.info(f"Trying to initialize with model: {model_name}")
                self.model = genai.GenerativeModel(model_name)
                
                # Test with a simple message
                logging.info("Sending test message to Gemini API")
                test_response = self.model.generate_content("Hello")
                if test_response and hasattr(test_response, 'text'):
                    logging.info(f"Successfully initialized Gemini with {model_name}")
                    self.use_fallback = False
                    return
                else:
                    logging.warning(f"Response from Gemini didn't have expected format: {test_response}")
            except Exception as e:
                error_details = f"Failed to initialize with {model_name}: {str(e)}"
                logging.warning(error_details)
                self.initialization_error = error_details
                
            try:
                # Try without the models/ prefix
                model_name = "gemini-1.5-flash-latest"
                logging.info(f"Trying to initialize with model: {model_name}")
                self.model = genai.GenerativeModel(model_name)
                
                # Test with a simple message
                logging.info("Sending test message to Gemini API")
                test_response = self.model.generate_content("Hello")
                if test_response and hasattr(test_response, 'text'):
                    logging.info(f"Successfully initialized Gemini with {model_name}")
                    self.use_fallback = False
                    return
                else:
                    logging.warning(f"Response from Gemini didn't have expected format: {test_response}")
            except Exception as e:
                error_details = f"Failed to initialize with {model_name}: {str(e)}"
                logging.warning(error_details)
                self.initialization_error = error_details
        else:
            print("❌ DEBUG: Gemini API not available (missing API key or package) - FALLBACK REASON")
            self.initialization_error = "Gemini API not available (missing API key or package)"
        
        print("⚠️ DEBUG: USING FALLBACK AI IMPLEMENTATION")
        logging.info("Using fallback AI implementation")
        
    def prepare_conversation_history(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert database messages to format expected by Gemini API"""
        formatted_messages = []
        
        for message in messages:
            role = "user" if message['sender'] == 'USER' else "model"
            formatted_messages.append({
                "role": role,
                "parts": [message['content']]
            })
            
        return formatted_messages
    
    def process_message(self, user_message: str, conversation_history: List[Dict[str, Any]]) -> Tuple[str, Dict, bool]:
        """
        Process a user message through Gemini AI or fallback system
        
        Returns:
            Tuple containing:
            - AI response text
            - Extracted data (if any)
            - Boolean indicating if this is a query (True) or data entry (False)
        """
        # Use fallback if Gemini is not available
        if self.use_fallback or self.model is None:
            if self.initialization_error:
                print(f"⚠️ DEBUG: Using fallback due to initialization error: {self.initialization_error}")
                logging.info(f"Using fallback due to initialization error: {self.initialization_error}")
            else:
                print("⚠️ DEBUG: Using fallback (use_fallback={}, model={})".format(self.use_fallback, "None" if self.model is None else "Set"))
            return self._fallback_process_message(user_message)
            
        # Proceed with Gemini API if available
        try:
            logging.info("Processing message with Gemini API")
            # Prepare conversation history
            formatted_history = self.prepare_conversation_history(conversation_history)
            
            # See if this is likely a query based on the user message
            query_patterns = [
                r'how much', r'what is', r'what were', r'what was', r'show me', r'tell me', r'report', 
                r'status', r'balance', r'overview', r'summary', r'total',
                r'analyse', r'analyze', r'check', r'find', r'search'
            ]
            
            # Check if this appears to be a query
            is_likely_query = any(re.search(pattern, user_message.lower()) for pattern in query_patterns)
            
            # If it looks like a query, get all transactions first
            transaction_data = []
            if is_likely_query:
                try:
                    # Only import here to avoid circular imports
                    from counto_app.services.sheets_services import GoogleSheetsService
                    sheets_service = GoogleSheetsService()
                    transaction_data = sheets_service.get_all_transactions()
                    print(f"Retrieved {len(transaction_data)} transactions for query processing")
                except Exception as e:
                    print(f"Error retrieving transactions: {e}")
            
            # Create an even more direct prompt that forces the model to behave as expected
            system_prompt = """
            SYSTEM: You are Counto, a financial assistant integrated into an accounting app. You have TWO primary functions:
            
            FUNCTION 1: DATA EXTRACTION
            When users mention expenses or income, you MUST respond with "DATA_ENTRY" at the start of your message, followed by extracted transaction details.
            
            Examples of expense mentions:
            - "I spent 500 on groceries"
            - "paid 1000 for rent"
            - "bought coffee for 50"
            - "record an expense of 500 for cogs"
            
            For ALL expense or spending mentions, ALWAYS extract and display this data:
            Date: May 13, 2025 (or whatever today's actual date is, not a placeholder)
            Description: [What was purchased]
            Category: [Food, Rent, Business, etc.]
            Amount: [The number mentioned]
            Type: Expense
            Party: [Who received the money or who you paid]
            Payment Method: [Cash, Card, UPI, Bank Transfer, etc.]
            
            For income transactions, ALWAYS extract:
            Date: May 13, 2025 (or whatever today's actual date is, not a placeholder)
            Description: [What the payment was for]
            Category: [Salary, Business Income, Gift, etc.]
            Amount: [The number mentioned]
            Type: Income
            Party: [Who sent you the money or who paid you]
            Payment Method: [Cash, Card, UPI, Bank Transfer, etc.]
            
            FUNCTION 2: ANSWERING QUERIES
            When users ask about their finances, respond with "QUERY" at the start of your message.
            
            For time-based queries, follow these rules:
            1. You will be provided with ALL transaction data as a list of transactions
            2. When a user asks about "today", "yesterday", "last week", "this month", "last month", etc., filter the transaction data accordingly
            3. "burn" or "spend" refers to expenses
            4. Calculate and display the total amount spent/earned for the specified time period
            5. List the matching transactions
            6. NEVER say you don't have access to historical data - you have access to ALL transaction data
            
            Examples of queries:
            - "What was my spend on food today?" → Filter for food transactions from today and calculate total
            - "How much did I spend last month?" → Filter all transactions from last month and sum expenses
            - "What was my burn last week?" → "Burn" means expenses, so filter for expenses from last week
            
            CRITICAL INSTRUCTIONS:
            1. When a user mentions ANY transaction, ALWAYS treat it as a real transaction they want to record in the app
            2. NEVER explain how accounting works - users are using you as a financial recording tool
            3. NEVER say you can't record transactions - your entire purpose is to record financial data
            4. ALWAYS start responses with either "DATA_ENTRY" or "QUERY"
            5. Format transaction data in a clear list format as shown above
            6. ALWAYS ask "Would you like me to record this transaction?" after showing transaction details
            7. When the user says "yes" or "confirm" or "record it", respond with "TRANSACTION_CONFIRMED"
            8. When the user says "no" or "cancel" or "don't record", respond with "TRANSACTION_CANCELLED"
            9. NEVER say you don't have access to past transaction history - when provided with transaction data, you can analyze ANY time period
            
            Example transaction: "record an expense of 500 for cogs today"
            Correct response must start with "DATA_ENTRY" and show the extracted data fields
            
            INCORRECT RESPONSES (NEVER DO THESE):
            - Explaining accounting systems
            - Saying you can't record transactions
            - Referring to yourself as an AI or language model
            - Giving general advice without extracting transaction data when a transaction is mentioned
            - Saying you don't have access to past transaction history
            - Ignoring transaction data when answering time-based queries
            
            This context is already inside a financial app with transaction recording capabilities.
            """
            
            # Enhanced prompt for direct content generation as fallback
            from datetime import datetime
            current_date = datetime.now().strftime('%B %d, %Y')
            
            # Add the current date to the prompt
            system_prompt_with_date = system_prompt.replace("May 13, 2025", current_date)
            
            # Add transaction data to the prompt if this is a query
            transaction_data_str = ""
            if is_likely_query and transaction_data:
                transaction_data_str = "\n\nHere is your COMPLETE TRANSACTION DATA (use this to answer time-based queries):\n"
                transaction_data_str += "ID | DATE | DESCRIPTION | AMOUNT | CATEGORY | TYPE\n"
                transaction_data_str += "--|------|-------------|--------|----------|------\n"
                for i, tx in enumerate(transaction_data, 1):
                    date = tx.get('date', 'Unknown date')
                    if isinstance(date, datetime):
                        date = date.strftime('%Y-%m-%d')
                    desc = tx.get('description', 'No description')
                    amount = tx.get('amount', '0')
                    category = tx.get('category', 'Uncategorized')
                    tx_type = tx.get('transaction_type', 'UNKNOWN')
                    payment_method = tx.get('payment_method', '')
                    party = tx.get('party', '')
                    
                    # Format in a table-like structure for easier analysis
                    transaction_data_str += f"{i} | {date} | {desc} | {amount} | {category} | {tx_type}\n"
                
                # Add explicit instructions for analysis
                transaction_data_str += "\nWhen analyzing this data for time periods:\n"
                transaction_data_str += "1. 'Today' refers to transactions on 2025-05-13\n"
                transaction_data_str += "2. 'This week' refers to transactions from 2025-05-07 to 2025-05-13\n"
                transaction_data_str += "3. 'Last week' refers to transactions from 2025-04-30 to 2025-05-06\n"
                transaction_data_str += "4. 'This month' refers to transactions from 2025-05-01 to 2025-05-13\n"
                transaction_data_str += "5. 'Last month' refers to transactions from 2025-04-01 to 2025-04-30\n"
                transaction_data_str += "6. 'Burn' and 'spend' refer to expenses (where TYPE is EXPENSE)\n"
            
            try:
                # Skip the chat interface entirely as it seems problematic
                # Instead use direct content generation with a very specific prompt
                logging.info("Using direct content generation with explicit transaction prompt")
                print("💡 DEBUG: Using direct content generation with explicit prompt")
                
                # Craft a specific prompt that includes the system instructions, transaction data, and user message
                prompt = f"{system_prompt_with_date}{transaction_data_str}\n\nUSER INPUT: {user_message}\n\nYour response (remember to start with DATA_ENTRY or QUERY and follow the format exactly as instructed, using {current_date} as today's date):"
                
                # Generate content with the complete prompt
                response = self.model.generate_content(prompt)
                response_text = response.text
                logging.info("Successfully got response from content generation")
            except AttributeError as e:
                # Fallback to basic content generation
                logging.warning(f"Chat interface failed with error: {str(e)}")
                logging.info("Falling back to basic content generation")
                prompt = f"{system_prompt}{transaction_data_str}\n\nUser: {user_message}"
                response = self.model.generate_content(prompt)
                response_text = response.text
                logging.info("Successfully got response from basic content generation")
        
            # Process the response
            is_query = response_text.startswith("QUERY")
            is_data_entry = response_text.startswith("DATA_ENTRY")
            
            logging.info(f"Response type - Query: {is_query}, Data Entry: {is_data_entry}")
            
            extracted_data = {}
            
            if is_data_entry:
                extracted_data = self._extract_transaction_data(response_text)
                response_text = response_text.replace("DATA_ENTRY", "", 1).strip()
            elif is_query:
                response_text = response_text.replace("QUERY", "", 1).strip()
            
            # Clean up any response formatting issues
            # Remove leading colon and space if present (common formatting issue)
            if response_text.startswith(":"):
                response_text = response_text[1:].strip()
            
            return response_text, extracted_data, is_query
        except Exception as e:
            logging.error(f"Error in Gemini processing: {str(e)}")
            # Log more details about the error
            import traceback
            print(f"❌ DEBUG: Error in Gemini processing: {str(e)} - FALLBACK REASON")
            logging.error(f"Detailed error traceback: {traceback.format_exc()}")
            # Switch to fallback if Gemini fails
            self.use_fallback = True
            return self._fallback_process_message(user_message)
    
    def _extract_transaction_data(self, response_text: str) -> Dict[str, Any]:
        """Extract transaction data from the AI response"""
        # This is a simplified extraction - in a real app you'd want to use more robust parsing
        extracted_data = {
            'date': None,
            'description': None,
            'category': None,
            'amount': None,
            'transaction_type': None,
            'payment_method': None,
            'reference_number': None,
            'party': None
        }
        
        # These are patterns we expect to see in the AI response
        patterns = {
            'date': ['Date:', 'Date :', 'DATE:'],
            'description': ['Description:', 'Description :', 'DESC:'],
            'category': ['Category:', 'Category :', 'CAT:'],
            'amount': ['Amount:', 'Amount :', 'AMT:'],
            'transaction_type': ['Type:', 'Type :', 'Transaction Type:'],
            'payment_method': ['Payment Method:', 'Payment :', 'Method:'],
            'reference_number': ['Reference:', 'Ref No:', 'Reference Number:'],
            'party': ['Party:', 'Party :', 'Payee:', 'Recipient:']
        }
        
        lines = response_text.split('\n')
        for line in lines:
            line = line.strip()
            
            for field, field_patterns in patterns.items():
                for pattern in field_patterns:
                    if line.startswith(pattern):
                        value = line[len(pattern):].strip()
                        extracted_data[field] = value
                        break
        
        # Handle transaction type specifically (income/expense)
        if extracted_data['transaction_type']:
            if 'income' in extracted_data['transaction_type'].lower():
                extracted_data['transaction_type'] = 'INCOME'
            elif 'expense' in extracted_data['transaction_type'].lower():
                extracted_data['transaction_type'] = 'EXPENSE'
        
        # Try to infer type from amount if not detected
        if not extracted_data['transaction_type'] and extracted_data['amount']:
            amount_str = extracted_data['amount'].replace('$', '').replace(',', '').strip()
            try:
                if amount_str.startswith('-'):
                    extracted_data['transaction_type'] = 'EXPENSE'
                else:
                    # If no sign, default to expense as more common
                    extracted_data['transaction_type'] = 'EXPENSE'
            except:
                pass
                
        return extracted_data
    
    def _fallback_process_message(self, user_message: str) -> Tuple[str, Dict, bool]:
        """
        Simple rule-based processor when AI service is unavailable
        
        Analyzes the user's message to determine if it's a transaction entry or a query,
        and provides appropriate responses without external AI services.
        """
        # Analyze the message to determine intent
        transaction_patterns = [
            r'\$\d+\.?\d*', r'spent', r'paid', r'bought', r'purchased', 
            r'cost', r'transaction', r'payment', r'expense', r'income',
            r'received', r'earned', r'transfer'
        ]
        query_patterns = [
            r'how much', r'what is', r'what were', r'what was', r'show me', r'tell me', r'report', 
            r'status', r'balance', r'overview', r'summary', r'total',
            r'analyse', r'analyze', r'check', r'find', r'search'
        ]
        
        # Time-related pattern detection
        time_patterns = {
            'today': [r'today', r'this day'],
            'yesterday': [r'yesterday'],
            'this_week': [r'this week', r'current week'],
            'last_week': [r'last week', r'previous week', r'past week'],
            'this_month': [r'this month', r'current month'],
            'last_month': [r'last month', r'previous month', r'past month'],
            'this_year': [r'this year', r'current year'],
            'last_year': [r'last year', r'previous year', r'past year'],
            'last_30_days': [r'last 30 days', r'past 30 days', r'last month', r'past month'],
            'last_90_days': [r'last 90 days', r'past 90 days', r'last quarter', r'past quarter'],
            'last_180_days': [r'last 180 days', r'past 180 days', r'last 6 months', r'past 6 months', r'half year'],
            'last_365_days': [r'last 365 days', r'past 365 days', r'last 12 months', r'past 12 months', r'past year']
        }
        
        # Check if this is likely a transaction entry
        is_transaction = any(re.search(pattern, user_message.lower()) for pattern in transaction_patterns)
        is_query = any(re.search(pattern, user_message.lower()) for pattern in query_patterns)
        
        # Default to query if neither is detected
        if not is_transaction and not is_query:
            is_query = True
            
        # Process as transaction entry
        if is_transaction and not is_query:
            extracted_data = self._extract_transaction_from_message(user_message)
            response_text = f"I've identified what looks like a transaction. Here's what I found:\n\n"
            
            # List the extracted data
            for field, value in extracted_data.items():
                if value:
                    readable_field = field.replace('_', ' ').title()
                    response_text += f"**{readable_field}**: {value}\n"
            
            response_text += "\nWould you like me to save this transaction? Please confirm or provide any corrections."
            return response_text, extracted_data, False
        
        # Process as query
        if is_query:
            # Try to extract what type of data the user is looking for
            data_type = None
            if re.search(r'expense', user_message.lower()) or re.search(r'spent', user_message.lower()):
                data_type = 'EXPENSE'
            elif re.search(r'income', user_message.lower()) or re.search(r'earn', user_message.lower()):
                data_type = 'INCOME'
            
            # Try to extract time period
            time_period = None
            for period, patterns in time_patterns.items():
                if any(re.search(pattern, user_message.lower()) for pattern in patterns):
                    time_period = period
                    break
            
            # Try to fetch data from sheets using the extracted time period
            if time_period:
                try:
                    from counto_app.services.sheets_services import GoogleSheetsService
                    sheets_service = GoogleSheetsService()
                    
                    # Build query parameters
                    query_params = {'time_period': time_period}
                    if data_type:
                        query_params['transaction_type'] = data_type
                    
                    # Check for category mentions
                    categories = ['food', 'groceries', 'rent', 'utilities', 'transportation', 
                                 'entertainment', 'shopping', 'travel', 'healthcare', 'education',
                                 'personal', 'business', 'income', 'salary', 'investment']
                    
                    for category in categories:
                        if category in user_message.lower():
                            query_params['category'] = category
                            break
                    
                    # Get transactions
                    transactions = sheets_service.query_transactions(query_params)
                    
                    if transactions:
                        # Calculate total for expenses or income
                        if data_type == 'EXPENSE' or data_type == 'INCOME':
                            total = sum(
                                float(str(t.get('amount', '0')).replace('$', '').replace(',', '')) 
                                for t in transactions if t.get('amount')
                            )
                            
                            # Format the response
                            period_display = time_period.replace('_', ' ')
                            response_text = f"I found {len(transactions)} {data_type.lower()} transactions for {period_display}. "
                            response_text += f"The total amount is ${total:.2f}.\n\n"
                            
                            # Add transaction details
                            response_text += "Here are the details:\n"
                            for i, t in enumerate(transactions, 1):
                                response_text += f"{i}. {t.get('date', 'Unknown date')} - {t.get('description', 'No description')} - "
                                response_text += f"{t.get('amount', '0')} ({t.get('category', 'Uncategorized')})\n"
                        else:
                            # For general queries without data type specified
                            response_text = f"I found {len(transactions)} transactions for {time_period.replace('_', ' ')}. Here are the details:\n"
                            for i, t in enumerate(transactions, 1):
                                response_text += f"{i}. {t.get('date', 'Unknown date')} - {t.get('description', 'No description')} - "
                                response_text += f"{t.get('amount', '0')} ({t.get('category', 'Uncategorized')}) - {t.get('transaction_type', 'Unknown type')}\n"
                        
                        return response_text, {}, True
                    else:
                        response_text = f"I didn't find any transactions for {time_period.replace('_', ' ')}."
                        if data_type:
                            response_text += f" with type {data_type.lower()}"
                        return response_text, {}, True
                        
                except Exception as e:
                    print(f"Error processing time-based query: {e}")
            
            # Default query response if we couldn't extract time or fetch data
            response_text = "I can help with your financial query. "
            if time_period:
                response_text += f"You asked about {time_period.replace('_', ' ')}. "
            response_text += "To see specific transactions, try asking about a time period like 'last week', 'this month', or 'today'.\n\n"
            response_text += "You can also specify the type of transaction (income or expenses) and categories."
            return response_text, {}, True
            
        # Default response if we can't determine intent
        return "I'm here to help with your finances. You can enter transactions or ask questions about your financial data.", {}, False
            
    def _extract_transaction_from_message(self, message: str) -> Dict[str, Any]:
        """
        Extract transaction details from a user message using pattern matching
        """
        extracted_data = {
            'date': None,
            'description': None,
            'category': None,
            'amount': None,
            'transaction_type': None,
            'payment_method': None,
            'reference_number': None,
            'party': None
        }
        
        # Extract date - look for common formats
        date_patterns = [
            (r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', '%m/%d/%Y'),  # MM/DD/YYYY or MM-DD-YYYY
            (r'\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b', '%Y/%m/%d'),  # YYYY/MM/DD or YYYY-MM-DD
            (r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}\b', '%b %d')  # Month DD
        ]
        
        for pattern, fmt in date_patterns:
            match = re.search(pattern, message.lower())
            if match:
                extracted_data['date'] = match.group(1)
                break
                
        # If no date found, use today
        if not extracted_data['date']:
            if 'yesterday' in message.lower():
                # Could implement yesterday's date, but using today for simplicity
                extracted_data['date'] = datetime.now().strftime('%Y-%m-%d')
            else:
                extracted_data['date'] = datetime.now().strftime('%Y-%m-%d')
                
        # Extract amount - look for currency patterns
        amount_match = re.search(r'\$?(\d+(?:\.\d{2})?)', message)
        if amount_match:
            extracted_data['amount'] = amount_match.group(0)
            
        # Determine if income or expense
        income_terms = ['received', 'earned', 'income', 'salary', 'deposit', 'refund']
        expense_terms = ['spent', 'paid', 'bought', 'purchased', 'expense']
        
        if any(term in message.lower() for term in income_terms):
            extracted_data['transaction_type'] = 'INCOME'
        elif any(term in message.lower() for term in expense_terms):
            extracted_data['transaction_type'] = 'EXPENSE'
        else:
            # Default to expense as more common
            extracted_data['transaction_type'] = 'EXPENSE'
            
        # Try to extract a description
        # This is very basic - in a real implementation you'd want more sophisticated NLP
        words = message.split()
        if len(words) >= 3:
            # Use a portion of the message as description
            extracted_data['description'] = ' '.join(words[:min(8, len(words))]) + \
                ('...' if len(words) > 8 else '')
            
        # Try to detect common categories
        categories = {
            'food': ['restaurant', 'meal', 'lunch', 'dinner', 'breakfast', 'grocery', 'food'],
            'transportation': ['gas', 'uber', 'lyft', 'taxi', 'fare', 'bus', 'train', 'transport'],
            'entertainment': ['movie', 'show', 'netflix', 'subscription', 'entertainment'],
            'shopping': ['store', 'mall', 'shopping', 'clothes', 'amazon', 'buy'],
            'utilities': ['bill', 'utility', 'electric', 'water', 'gas', 'internet', 'phone'],
            'housing': ['rent', 'mortgage', 'lease', 'housing', 'apartment']
        }
        
        for category, terms in categories.items():
            if any(term in message.lower() for term in terms):
                extracted_data['category'] = category.upper()
                break
                
        # Try to extract payment method
        payment_methods = {
            'credit_card': ['credit card', 'credit', 'visa', 'mastercard', 'amex'],
            'debit_card': ['debit card', 'debit'],
            'cash': ['cash', 'paid cash', 'in cash'],
            'bank_transfer': ['transfer', 'wire', 'ach', 'direct deposit'],
            'check': ['check', 'cheque']
        }
        
        for method, terms in payment_methods.items():
            if any(term in message.lower() for term in terms):
                extracted_data['payment_method'] = method.upper().replace('_', ' ')
                break
                
        return extracted_data
        
    def generate_financial_insights(self, financial_data: List[Dict[str, Any]]) -> str:
        """Generate insights based on financial data"""
        if self.use_fallback or self.model is None:
            # Fallback basic insights generator
            insights = "Based on the available data, here are some basic insights:\n\n"
            
            # Count transactions by type
            income_count = sum(1 for item in financial_data if item.get('transaction_type') == 'INCOME')
            expense_count = sum(1 for item in financial_data if item.get('transaction_type') == 'EXPENSE')
            
            # Calculate total income and expenses
            total_income = sum(float(item.get('amount', 0)) for item in financial_data 
                            if item.get('transaction_type') == 'INCOME' and item.get('amount'))
            total_expenses = sum(float(item.get('amount', 0)) for item in financial_data 
                              if item.get('transaction_type') == 'EXPENSE' and item.get('amount'))
            
            # Generate some basic insights
            insights += f"1. You have {income_count} income transactions and {expense_count} expense transactions.\n"
            insights += f"2. Your total income is ${total_income:.2f} and total expenses are ${total_expenses:.2f}.\n"
            
            # Net position
            net = total_income - total_expenses
            if net > 0:
                insights += f"3. You have a positive cash flow of ${net:.2f}.\n"
            else:
                insights += f"3. You have a negative cash flow of ${abs(net):.2f}. Consider reducing expenses.\n"
                
            return insights
            
        # Use Gemini if available
        try:
            # Format the financial data into a readable prompt
            data_prompt = "Here is recent financial data:\n"
            for item in financial_data[:20]:  # Limit to recent entries
                data_prompt += f"- {item['date']}: {item['description']} - {item['amount']} ({item['category']})\n"
                
            prompt = f"""
            {data_prompt}
            
            Based on this financial data, provide 3 key insights and recommendations.
            Focus on spending patterns, potential savings, or financial opportunities.
            Keep your response concise and actionable.
            """
            
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logging.error(f"Error generating financial insights: {str(e)}")
            # Fall back to basic insights if Gemini fails
            self.use_fallback = True
            return self.generate_financial_insights(financial_data)