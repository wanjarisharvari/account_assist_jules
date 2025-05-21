# import os
# import json
# import logging
# import re
# from datetime import datetime
# from typing import Dict, Any, Tuple, List, Optional
# from django.conf import settings

# # Configure logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# # Initialize Gemini API
# try:
#     import google.generativeai as genai
#     if hasattr(settings, 'GEMINI_API_KEY') and settings.GEMINI_API_KEY:
#         # Configure Gemini with API key
#         genai.configure(api_key=settings.GEMINI_API_KEY)
#         GEMINI_AVAILABLE = True
#         logger.info("Gemini API successfully configured")
#     else:
#         GEMINI_AVAILABLE = False
#         logger.warning("No GEMINI_API_KEY found in settings")
# except ImportError:
#     GEMINI_AVAILABLE = False
#     logger.warning("google.generativeai package not installed")

# class GeminiService:
#     """Service for processing financial messages using Google's Gemini API"""
    
#     def __init__(self):
#         """Initialize the Gemini service with the appropriate model"""
#         self.model = None
        
#         if not GEMINI_AVAILABLE:
#             logger.warning("Gemini API not available - Service will not function")
#             return
            
#         try:
#             # Initialize with a single model name
#             model_name = "gemini-1.5-flash-latest"  # Use latest model version
#             logger.info(f"Initializing Gemini with model: {model_name}")
#             self.model = genai.GenerativeModel(model_name)
            
#             # Verify the model works
#             test_response = self.model.generate_content("Hello")
#             if test_response and hasattr(test_response, 'text'):
#                 logger.info(f"Successfully initialized Gemini")
#             else:
#                 logger.warning("Response from Gemini didn't have expected format")
#                 self.model = None
#         except Exception as e:
#             logger.error(f"Failed to initialize Gemini: {str(e)}")
#             self.model = None
    
#     def prepare_conversation_history(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
#         """Convert database messages to format expected by Gemini API"""
#         formatted_messages = []
        
#         for message in messages:
#             role = "user" if message['sender'] == 'USER' else "model"
#             formatted_messages.append({
#                 "role": role,
#                 "parts": [message['content']]
#             })
            
#         return formatted_messages
    
#     def process_message(self, user_message: str, conversation_history: List[Dict[str, Any]]) -> Tuple[str, Dict, bool]:
#         """
#         Process a user message through Gemini AI
        
#         Returns:
#             Tuple containing:
#             - AI response text
#             - Extracted data (if any)
#             - Boolean indicating if this is a query (True) or data entry (False)
#         """
#         if not GEMINI_AVAILABLE or not self.model:
#             logger.error("Gemini service unavailable")
#             return "Sorry, the AI service is currently unavailable.", {}, False
            
#         # Get current date for transaction processing
#         current_date = datetime.now().strftime('%B %d, %Y')
        
#         # Check if this is likely a query based on the user message
#         query_patterns = [
#             r'how much', r'what is', r'what were', r'what was', r'show me', r'tell me', r'report', 
#             r'status', r'balance', r'overview', r'summary', r'total',
#             r'analyse', r'analyze', r'check', r'find', r'search'
#         ]
#         is_likely_query = any(re.search(pattern, user_message.lower()) for pattern in query_patterns)
        
#         # If it looks like a query, get all transactions
#         transaction_data = []
#         if is_likely_query:
#             try:
#                 # Only import here to avoid circular imports
#                 from counto_app.services.sheets_services import GoogleSheetsService
#                 sheets_service = GoogleSheetsService()
#                 transaction_data = sheets_service.get_all_transactions()
#                 logger.info(f"Retrieved {len(transaction_data)} transactions for query processing")
#             except Exception as e:
#                 logger.error(f"Error retrieving transactions: {e}")
        
#         # Create system prompt with current date
#         system_prompt = f"""
#         SYSTEM: You are Counto, a financial assistant integrated into an accounting app. You have TWO primary functions:
        
#         FUNCTION 1: DATA EXTRACTION
#         When users mention expenses or income, you MUST respond with "DATA_ENTRY" at the start of your message, followed by extracted transaction details.
        
#         Examples of expense mentions:
#         - "I spent 500 on groceries"
#         - "paid 1000 for rent"
#         - "bought coffee for 50"
#         - "record an expense of 500 for cogs"
        
#         For ALL expense or spending mentions, ALWAYS extract and display this data:
#         Date: {current_date} (today's actual date)
#         Description: [What was purchased]
#         Category: [Food, Rent, Business, etc.]
#         Amount: [The number mentioned]
#         Type: Expense
#         Party: [Who received the money or who you paid]
#         Payment Method: [Cash, Card, UPI, Bank Transfer, etc.]
        
#         For income transactions, ALWAYS extract:
#         Date: {current_date} (today's actual date)
#         Description: [What the payment was for]
#         Category: [Salary, Business Income, Gift, etc.]
#         Amount: [The number mentioned]
#         Type: Income
#         Party: [Who sent you the money or who paid you]
#         Payment Method: [Cash, Card, UPI, Bank Transfer, etc.]
        
#         FUNCTION 2: ANSWERING QUERIES
#         When users ask about their finances, respond with "QUERY" at the start of your message.
        
#         For time-based queries, follow these rules:
#         1. You will be provided with ALL transaction data as a list of transactions
#         2. When a user asks about "today", "yesterday", "last week", "this month", "last month", etc., filter the transaction data accordingly
#         3. "burn" or "spend" refers to expenses
#         4. Calculate and display the total amount spent/earned for the specified time period
#         5. List the matching transactions
        
#         CRITICAL INSTRUCTIONS:
#         1. When a user mentions ANY transaction, ALWAYS treat it as a real transaction they want to record in the app
#         2. NEVER explain how accounting works - users are using you as a financial recording tool
#         3. ALWAYS start responses with either "DATA_ENTRY" or "QUERY"
#         4. Format transaction data in a clear list format as shown above
#         5. ALWAYS ask "Would you like me to record this transaction?" after showing transaction details
#         6. When the user says "yes" or "confirm" or "record it", respond with "TRANSACTION_CONFIRMED"
#         7. When the user says "no" or "cancel" or "don't record", respond with "TRANSACTION_CANCELLED"
#         """
        
#         # Add transaction data to the prompt if this is a query
#         transaction_data_str = ""
#         if is_likely_query and transaction_data:
#             transaction_data_str = "\n\nHere is your COMPLETE TRANSACTION DATA (use this to answer time-based queries):\n"
#             transaction_data_str += "ID | DATE | DESCRIPTION | AMOUNT | CATEGORY | TYPE\n"
#             transaction_data_str += "--|------|-------------|--------|----------|------\n"
            
#             for i, tx in enumerate(transaction_data, 1):
#                 date = tx.get('date', 'Unknown date')
#                 if isinstance(date, datetime):
#                     date = date.strftime('%Y-%m-%d')
#                 desc = tx.get('description', 'No description')
#                 amount = tx.get('amount', '0')
#                 category = tx.get('category', 'Uncategorized')
#                 tx_type = tx.get('transaction_type', 'UNKNOWN')
                
#                 # Format in a table-like structure for easier analysis
#                 transaction_data_str += f"{i} | {date} | {desc} | {amount} | {category} | {tx_type}\n"
            
#             # Add explicit instructions for analysis
#             transaction_data_str += "\nWhen analyzing this data for time periods:\n"
#             transaction_data_str += "1. 'Today' refers to transactions on current date\n"
#             transaction_data_str += "2. 'Burn' and 'spend' refer to expenses (where TYPE is EXPENSE)\n"
        
#         try:
#             # Craft the complete prompt
#             prompt = f"{system_prompt}{transaction_data_str}\n\nUSER INPUT: {user_message}\n\n"
#             prompt += f"Your response (remember to start with DATA_ENTRY or QUERY and follow the format exactly as instructed, using {current_date} as today's date):"
            
#             # Generate content with the complete prompt
#             response = self.model.generate_content(prompt)
#             response_text = response.text
#             logger.info("Successfully received response from Gemini")
            
#             # Process the response
#             is_query = response_text.startswith("QUERY")
#             is_data_entry = response_text.startswith("DATA_ENTRY")
            
#             logger.info(f"Response type - Query: {is_query}, Data Entry: {is_data_entry}")
            
#             extracted_data = {}
            
#             if is_data_entry:
#                 extracted_data = self._extract_transaction_data(response_text)
#                 response_text = response_text.replace("DATA_ENTRY", "", 1).strip()
#             elif is_query:
#                 response_text = response_text.replace("QUERY", "", 1).strip()
            
#             # Clean up formatting issues
#             if response_text.startswith(":"):
#                 response_text = response_text[1:].strip()
            
#             return response_text, extracted_data, is_query
#         except Exception as e:
#             logger.error(f"Error in Gemini processing: {str(e)}")
#             return f"Sorry, there was an error processing your request: {str(e)}", {}, False
    
#     def _extract_transaction_data(self, response_text: str) -> Dict[str, Any]:
#         """Extract transaction data from the AI response"""
#         extracted_data = {
#             'date': datetime.now().strftime('%Y-%m-%d'),  # Always use current date
#             'description': None,
#             'category': None,
#             'amount': None,
#             'transaction_type': None,
#             'payment_method': None,
#             'reference_number': None,
#             'party': None
#         }
        
#         # Patterns to extract data from response
#         patterns = {
#             'date': ['Date:', 'Date :', 'DATE:'],
#             'description': ['Description:', 'Description :', 'DESC:'],
#             'category': ['Category:', 'Category :', 'CAT:'],
#             'amount': ['Amount:', 'Amount :', 'AMT:'],
#             'transaction_type': ['Type:', 'Type :', 'Transaction Type:'],
#             'payment_method': ['Payment Method:', 'Payment :', 'Method:'],
#             'reference_number': ['Reference:', 'Ref No:', 'Reference Number:'],
#             'party': ['Party:', 'Party :', 'Payee:', 'Recipient:']
#         }
        
#         # Extract data using patterns
#         lines = response_text.split('\n')
#         for line in lines:
#             line = line.strip()
            
#             for field, field_patterns in patterns.items():
#                 for pattern in field_patterns:
#                     if line.startswith(pattern):
#                         value = line[len(pattern):].strip()
#                         extracted_data[field] = value
#                         break
        
#         # Normalize transaction type
#         if extracted_data['transaction_type']:
#             if 'income' in extracted_data['transaction_type'].lower():
#                 extracted_data['transaction_type'] = 'INCOME'
#             elif 'expense' in extracted_data['transaction_type'].lower():
#                 extracted_data['transaction_type'] = 'EXPENSE'
        
#         return extracted_data
    
#     def generate_financial_insights(self, financial_data: List[Dict[str, Any]]) -> str:
#         """Generate insights based on financial data using Gemini"""
#         if not GEMINI_AVAILABLE or not self.model:
#             return "Sorry, insights generation is unavailable without Gemini API access."
            
#         try:
#             # Format the financial data into a readable prompt
#             data_prompt = "Here is recent financial data:\n"
#             for item in financial_data[:20]:  # Limit to recent entries
#                 data_prompt += f"- {item['date']}: {item['description']} - {item['amount']} ({item['category']})\n"
                
#             prompt = f"""
#             {data_prompt}
            
#             Based on this financial data, provide 3 key insights and recommendations.
#             Focus on spending patterns, potential savings, or financial opportunities.
#             Keep your response concise and actionable.
#             """
            
#             response = self.model.generate_content(prompt)
#             return response.text
#         except Exception as e:
#             logger.error(f"Error generating financial insights: {str(e)}")
#             return f"Sorry, I couldn't generate insights due to an error: {str(e)}"

import os
import json
import logging
import re
from datetime import datetime
from typing import Dict, Any, Tuple, List, Optional
from django.conf import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Gemini API
try:
    import google.generativeai as genai
    if hasattr(settings, 'GEMINI_API_KEY') and settings.GEMINI_API_KEY:
        # Configure Gemini with API key
        genai.configure(api_key=settings.GEMINI_API_KEY)
        GEMINI_AVAILABLE = True
        logger.info("Gemini API successfully configured")
    else:
        GEMINI_AVAILABLE = False
        logger.warning("No GEMINI_API_KEY found in settings")
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google.generativeai package not installed")

class GeminiService:
    """Service for processing financial messages using Google's Gemini API"""
    
    def __init__(self):
        """Initialize the Gemini service with the appropriate model"""
        self.model = None
        
        if not GEMINI_AVAILABLE:
            logger.warning("Gemini API not available - Service will not function")
            return
            
        try:
            # Initialize with a single model name
            model_name = "gemini-1.5-flash-latest"  # Use latest model version
            logger.info(f"Initializing Gemini with model: {model_name}")
            self.model = genai.GenerativeModel(model_name)
            
            # Verify the model works
            test_response = self.model.generate_content("Hello")
            if test_response and hasattr(test_response, 'text'):
                logger.info(f"Successfully initialized Gemini")
            else:
                logger.warning("Response from Gemini didn't have expected format")
                self.model = None
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {str(e)}")
            self.model = None
    
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
    
    def process_message(self, user_message: str, conversation_history: List[Dict[str, Any]]) -> Tuple[str, Dict, str, bool]:
        """
        Process a user message through Gemini AI
        
        Returns:
            Tuple containing:
            - AI response text
            - Extracted data (if any)
            - Intent type (TRANSACTION, CUSTOMER, VENDOR)
            - Boolean indicating if this is a query (True) or data entry (False)
        """
        if not GEMINI_AVAILABLE or not self.model:
            logger.error("Gemini service unavailable")
            return "Sorry, the AI service is currently unavailable.", {}, "UNKNOWN", False
            
        # Get current date for transaction processing
        current_date = datetime.now().strftime('%B %d, %Y')
        
        # Check if this is likely a query based on the user message
        query_patterns = [
            r'how much', r'what is', r'what were', r'what was', r'show me', r'tell me', r'report', 
            r'status', r'balance', r'overview', r'summary', r'total',
            r'analyse', r'analyze', r'check', r'find', r'search', r'list'
        ]
        is_likely_query = any(re.search(pattern, user_message.lower()) for pattern in query_patterns)
        
        # Determine the intent type (transaction, customer, or vendor)
        intent_type = self._determine_intent_type(user_message)
        
        # Fetch relevant data for queries
        data_for_query = []
        if is_likely_query:
            try:
                # Only import here to avoid circular imports
                from counto_app.services.sheets_services import GoogleSheetsService
                sheets_service = GoogleSheetsService()
                
                if intent_type == "TRANSACTION":
                    data_for_query = sheets_service.get_all_transactions()
                    logger.info(f"Retrieved {len(data_for_query)} transactions for query processing")
                elif intent_type == "CUSTOMER":
                    data_for_query = sheets_service.get_all_customers()
                    logger.info(f"Retrieved {len(data_for_query)} customers for query processing")
                elif intent_type == "VENDOR":
                    data_for_query = sheets_service.get_all_vendors()
                    logger.info(f"Retrieved {len(data_for_query)} vendors for query processing")
            except Exception as e:
                logger.error(f"Error retrieving data: {e}")
        
        # Create system prompt based on intent type
        system_prompt = self._create_system_prompt(intent_type, current_date)
        
        # Add data to the prompt if this is a query
        data_str = ""
        if is_likely_query and data_for_query:
            data_str = self._format_data_for_query(intent_type, data_for_query)
        
        try:
            # Craft the complete prompt
            prompt = f"{system_prompt}{data_str}\n\nUSER INPUT: {user_message}\n\n"
            prompt += f"Your response (remember to start with the appropriate tag (DATA_ENTRY_TRANSACTION, DATA_ENTRY_CUSTOMER, DATA_ENTRY_VENDOR, QUERY_TRANSACTION, QUERY_CUSTOMER, QUERY_VENDOR) and follow the format exactly as instructed, using {current_date} as today's date):"
            
            # Generate content with the complete prompt
            response = self.model.generate_content(prompt)
            response_text = response.text
            logger.info("Successfully received response from Gemini")
            
            # Process the response to determine if it's a query or data entry
            response_tags = {
                "DATA_ENTRY_TRANSACTION": ("TRANSACTION", False),
                "DATA_ENTRY_CUSTOMER": ("CUSTOMER", False),
                "DATA_ENTRY_VENDOR": ("VENDOR", False),
                "QUERY_TRANSACTION": ("TRANSACTION", True),
                "QUERY_CUSTOMER": ("CUSTOMER", True),
                "QUERY_VENDOR": ("VENDOR", True)
            }
            
            # Determine intent and query status from response
            detected_intent = "UNKNOWN"
            is_query = False
            
            for tag, (intent, query_status) in response_tags.items():
                if response_text.startswith(tag):
                    detected_intent = intent
                    is_query = query_status
                    response_text = response_text.replace(tag, "", 1).strip()
                    break
            
            logger.info(f"Response type - Intent: {detected_intent}, Query: {is_query}")
            
            extracted_data = {}
            
            # Extract data if this is a data entry
            if not is_query:
                if detected_intent == "TRANSACTION":
                    extracted_data = self._extract_transaction_data(response_text)
                elif detected_intent == "CUSTOMER":
                    extracted_data = self._extract_customer_data(response_text)
                elif detected_intent == "VENDOR":
                    extracted_data = self._extract_vendor_data(response_text)
            
            # Clean up formatting issues
            if response_text.startswith(":"):
                response_text = response_text[1:].strip()
            
            return response_text, extracted_data, detected_intent, is_query
        except Exception as e:
            logger.error(f"Error in Gemini processing: {str(e)}")
            return f"Sorry, there was an error processing your request: {str(e)}", {}, "UNKNOWN", False
    
    def _determine_intent_type(self, user_message: str) -> str:
        """Determine if the message is about transactions, customers, or vendors"""
        transaction_keywords = [
            "spent", "paid", "bought", "purchased", "expense", "income", "transaction", 
            "bill", "invoice", "payment", "receipt", "money", "cash", "card", "upi", 
            "amount", "total", "cost", "price", "fee", "charge", "sale", "refund",
            "profit", "loss", "balance", "budget", "account", "financial", "finance",
            "deposit", "withdraw", "transfer", "salary", "revenue", "earnings"
        ]
        
        customer_keywords = [
            "customer", "client", "buyer", "consumer", "purchaser", "shopper",
            "patron", "clientele", "add customer", "new customer", "customer list",
            "client details", "buyer info", "customer contact", "client database"
        ]
        
        vendor_keywords = [
            "vendor", "supplier", "distributor", "provider", "manufacturer", "wholesaler",
            "retailer", "dealer", "add vendor", "new vendor", "vendor list", "supplier details",
            "distributor info", "vendor contact", "supplier database"
        ]
        
        user_msg_lower = user_message.lower()
        
        # Count keyword matches for each category
        transaction_count = sum(1 for keyword in transaction_keywords if keyword in user_msg_lower)
        customer_count = sum(1 for keyword in customer_keywords if keyword in user_msg_lower)
        vendor_count = sum(1 for keyword in vendor_keywords if keyword in user_msg_lower)
        
        # Determine the intent based on keyword match counts
        if customer_count > transaction_count and customer_count > vendor_count:
            return "CUSTOMER"
        elif vendor_count > transaction_count and vendor_count > customer_count:
            return "VENDOR"
        else:
            # Default to transaction if we can't clearly determine or if transaction has most matches
            return "TRANSACTION"
    
    def _create_system_prompt(self, intent_type: str, current_date: str) -> str:
        """Create a system prompt based on the intent type"""
        base_prompt = f"""
        SYSTEM: You are Counto, a financial assistant integrated into an accounting app. You have THREE primary functions:
        
        Based on the user's message, you must determine if they want to:
        1. Add/modify TRANSACTION data
        2. Add/modify CUSTOMER data 
        3. Add/modify VENDOR data
        4. Query TRANSACTION, CUSTOMER, or VENDOR data
        
        For EACH response, you MUST start with ONE of these tags:
        - DATA_ENTRY_TRANSACTION: When adding/modifying transaction information
        - DATA_ENTRY_CUSTOMER: When adding/modifying customer information
        - DATA_ENTRY_VENDOR: When adding/modifying vendor information
        - QUERY_TRANSACTION: When querying transaction information
        - QUERY_CUSTOMER: When querying customer information
        - QUERY_VENDOR: When querying vendor information
        """
        
        transaction_prompt = f"""
        FUNCTION 1: TRANSACTION DATA EXTRACTION
        When users mention expenses or income, respond with "DATA_ENTRY_TRANSACTION" at the start, followed by extracted details.
        
        Examples of transaction mentions:
        - "I spent 500 on groceries"
        - "paid 1000 for rent"
        - "received 5000 from client XYZ"
        - "record an expense of 500 for cogs"
        
        For ALL expense or spending mentions, ALWAYS extract and display this data:
        Date: {current_date} (today's actual date)
        Description: [What was purchased]
        Category: [Food, Rent, Business, etc.]
        Amount: [The number mentioned]
        Type: Expense
        Payment Method: [Cash, Card, UPI, Bank Transfer, etc.]
        Reference Number: [Optional]
        Vendor: [Who received the payment]
        Status: [PENDING, PARTIAL, PAID] (default: PAID)
        Expected Amount: [Optional - if different from paid amount]
        Paid Amount: [The actual amount paid]
        
        For income transactions, ALWAYS extract:
        Date: {current_date} (today's actual date)
        Description: [What the payment was for]
        Category: [Salary, Business Income, Gift, etc.]
        Amount: [The number mentioned]
        Type: Income
        Payment Method: [Cash, Card, UPI, Bank Transfer, etc.]
        Reference Number: [Optional]
        Customer: [Who sent the payment]
        Status: [PENDING, PARTIAL, PAID] (default: PAID)
        Expected Amount: [Optional - if different from paid amount]
        Paid Amount: [The actual amount received]
        """
        
        customer_prompt = """
        FUNCTION 2: CUSTOMER DATA EXTRACTION
        When users mention adding or updating customer information, respond with "DATA_ENTRY_CUSTOMER" at the start.
        
        Examples of customer mentions:
        - "Add a new customer named ABC Corp"
        - "Create customer record for John Doe"
        - "Update customer XYZ's details"
        
        For ALL customer mentions, ALWAYS extract and display this data:
        Name: [Customer name]
        Email: [Customer email, if mentioned]
        Phone: [Customer phone, if mentioned]
        GST Number: [Customer GST number, if mentioned]
        Address: [Customer address, if mentioned]
        """
        
        vendor_prompt = """
        FUNCTION 3: VENDOR DATA EXTRACTION
        When users mention adding or updating vendor information, respond with "DATA_ENTRY_VENDOR" at the start.
        
        Examples of vendor mentions:
        - "Add a new vendor named ABC Supplies"
        - "Create vendor record for Smith & Co"
        - "Update vendor XYZ's details"
        
        For ALL vendor mentions, ALWAYS extract and display this data:
        Name: [Vendor name]
        Email: [Vendor email, if mentioned]
        Phone: [Vendor phone, if mentioned]
        GST Number: [Vendor GST number, if mentioned]
        Address: [Vendor address, if mentioned]
        """
        
        query_prompt = """
        FUNCTION 4: ANSWERING QUERIES
        When users ask about their finances, customers, or vendors, respond with the appropriate QUERY tag.
        
        For time-based queries, follow these rules:
        1. You will be provided with ALL relevant data as a list
        2. When a user asks about "today", "yesterday", "last week", "this month", "last month", etc., filter the data accordingly
        3. Calculate and display the total amount (for transactions) or total count (for customers/vendors)
        4. List the matching records
        
        Example query responses:
        - "QUERY_TRANSACTION" for "Show me my expenses this month"
        - "QUERY_CUSTOMER" for "List all my customers"
        - "QUERY_VENDOR" for "Who are my vendors in Delhi?"
        """
        
        critical_instructions = """
        CRITICAL INSTRUCTIONS:
        1. ALWAYS treat user mentions as real data they want to record in the app
        2. NEVER explain how accounting works - users are using you as a financial recording tool
        3. ALWAYS start responses with one of the specified tags
        4. Format data in a clear list format as shown above
        5. ALWAYS ask "Would you like me to record this [transaction/customer/vendor]?" after showing details
        6. When the user says "yes" or "confirm" or "record it", respond with "[TRANSACTION/CUSTOMER/VENDOR]_CONFIRMED"
        7. When the user says "no" or "cancel" or "don't record", respond with "[TRANSACTION/CUSTOMER/VENDOR]_CANCELLED"
        """
        
        # Combine relevant prompts based on intent type
        if intent_type == "TRANSACTION":
            return base_prompt + transaction_prompt + query_prompt + critical_instructions
        elif intent_type == "CUSTOMER":
            return base_prompt + customer_prompt + query_prompt + critical_instructions
        elif intent_type == "VENDOR":
            return base_prompt + vendor_prompt + query_prompt + critical_instructions
        else:
            # Return all prompts if intent is unknown
            return base_prompt + transaction_prompt + customer_prompt + vendor_prompt + query_prompt + critical_instructions
    
    def _format_data_for_query(self, intent_type: str, data: List[Dict[str, Any]]) -> str:
        """Format data for inclusion in the query prompt"""
        data_str = "\n\nHere is your COMPLETE DATA for querying:\n"
        
        if intent_type == "TRANSACTION":
            data_str += "ID | DATE | DESCRIPTION | AMOUNT | CATEGORY | TYPE | STATUS | CUSTOMER/VENDOR\n"
            data_str += "--|------|-------------|--------|----------|------|--------|---------------\n"
            
            for i, tx in enumerate(data, 1):
                date = tx.get('date', 'Unknown date')
                if isinstance(date, datetime):
                    date = date.strftime('%Y-%m-%d')
                desc = tx.get('description', 'No description')
                amount = tx.get('paid_amount', '0')
                category = tx.get('category', 'Uncategorized')
                tx_type = tx.get('transaction_type', 'UNKNOWN')
                status = tx.get('status', 'PAID')
                party = tx.get('customer', '') if tx_type == 'INCOME' else tx.get('vendor', '')
                
                # Format in a table-like structure for easier analysis
                data_str += f"{i} | {date} | {desc} | {amount} | {category} | {tx_type} | {status} | {party}\n"
            
        elif intent_type == "CUSTOMER":
            data_str += "ID | NAME | EMAIL | PHONE | GST NUMBER | ADDRESS\n"
            data_str += "--|------|------|-------|------------|--------\n"
            
            for i, customer in enumerate(data, 1):
                name = customer.get('name', 'Unknown')
                email = customer.get('email', '-')
                phone = customer.get('phone', '-')
                gst = customer.get('gst_number', '-')
                address = customer.get('address', '-')
                
                data_str += f"{i} | {name} | {email} | {phone} | {gst} | {address}\n"
                
        elif intent_type == "VENDOR":
            data_str += "ID | NAME | EMAIL | PHONE | GST NUMBER | ADDRESS\n"
            data_str += "--|------|------|-------|------------|--------\n"
            
            for i, vendor in enumerate(data, 1):
                name = vendor.get('name', 'Unknown')
                email = vendor.get('email', '-')
                phone = vendor.get('phone', '-')
                gst = vendor.get('gst_number', '-')
                address = vendor.get('address', '-')
                
                data_str += f"{i} | {name} | {email} | {phone} | {gst} | {address}\n"
        
        # Add explicit instructions for analysis
        data_str += "\nWhen analyzing this data for time periods:\n"
        data_str += "1. 'Today' refers to transactions/records on current date\n"
        data_str += "2. 'This month' refers to the current calendar month\n"
        data_str += "3. 'This year' refers to the current calendar year\n"
        
        return data_str
    
    def _extract_transaction_data(self, response_text: str) -> Dict[str, Any]:
        """Extract transaction data from the AI response"""
        def safe_float_convert(value):
            """Safely convert string to float, handling various formats and optional values"""
            if not value or value.lower() in ['', 'optional', '[optional]']:
                return None
            try:
                # Remove any non-numeric characters except decimal point and minus
                clean_value = ''.join(c for c in str(value) if c.isdigit() or c in '.-')
                return float(clean_value) if clean_value else None
            except (ValueError, TypeError):
                return None

        extracted_data = {
            'date': datetime.now().strftime('%Y-%m-%d'),  # Always use current date
            'description': 'No description',
            'category': 'Uncategorized',
            'transaction_type': 'EXPENSE',  # Default to expense
            'expected_amount': None,
            'paid_amount': None,
            'status': 'PAID',  # Default status
            'customer': None,
            'vendor': None,
            'payment_method': 'Cash',  # Default payment method
            'reference_number': None
        }
        
        # Patterns to extract data from response
        patterns = {
            'date': ['Date:', 'Date :', 'DATE:'],
            'description': ['Description:', 'Description :', 'DESC:'],
            'category': ['Category:', 'Category :', 'CAT:'],
            'transaction_type': ['Type:', 'Type :', 'Transaction Type:'],
            'expected_amount': ['Expected Amount:', 'Expected:'],
            'paid_amount': ['Paid Amount:', 'Amount:', 'Amount :', 'AMT:'],
            'status': ['Status:', 'Status :'],
            'customer': ['Customer:', 'Customer :', 'Client:'],
            'vendor': ['Vendor:', 'Vendor :', 'Supplier:', 'Paid to:'],
            'payment_method': ['Payment Method:', 'Payment :', 'Method:'],
            'reference_number': ['Reference:', 'Ref No:', 'Reference Number:']
        }
        
        # Extract data using patterns
        lines = response_text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            for field, field_patterns in patterns.items():
                for pattern in field_patterns:
                    if line.startswith(pattern):
                        value = line[len(pattern):].strip()
                        if value:  # Only update if we have a value
                            extracted_data[field] = value
                        break
        
        # Normalize transaction type
        if extracted_data['transaction_type']:
            tx_type = extracted_data['transaction_type'].lower()
            if 'income' in tx_type:
                extracted_data['transaction_type'] = 'INCOME'
            elif 'expense' in tx_type:
                extracted_data['transaction_type'] = 'EXPENSE'
        
        # Convert amount strings to float, handling optional values
        if extracted_data['paid_amount']:
            extracted_data['paid_amount'] = safe_float_convert(extracted_data['paid_amount'])
        
        # Set expected_amount equal to paid_amount if not explicitly set
        if not extracted_data['expected_amount'] and extracted_data['paid_amount'] is not None:
            extracted_data['expected_amount'] = extracted_data['paid_amount']
        elif extracted_data['expected_amount']:
            extracted_data['expected_amount'] = safe_float_convert(extracted_data['expected_amount'])
        
        # Set default paid amount if not provided (for expenses, assume full payment)
        if (extracted_data['transaction_type'] == 'EXPENSE' and 
            extracted_data['expected_amount'] is not None and 
            extracted_data['paid_amount'] is None):
            extracted_data['paid_amount'] = extracted_data['expected_amount']
        
        # Update status based on payment amounts
        paid = extracted_data['paid_amount'] or 0
        expected = extracted_data['expected_amount'] or 0
        
        if paid == 0 and expected > 0:
            extracted_data['status'] = 'PENDING'
        elif 0 < paid < expected:
            extracted_data['status'] = 'PARTIAL'
        else:
            extracted_data['status'] = 'PAID'
            
        # If we have a vendor but no customer (for expenses), set it
        if extracted_data['transaction_type'] == 'EXPENSE' and extracted_data['vendor'] and not extracted_data['customer']:
            extracted_data['customer'] = extracted_data['vendor']
        # If we have a customer but no vendor (for income), set it
        elif extracted_data['transaction_type'] == 'INCOME' and extracted_data['customer'] and not extracted_data['vendor']:
            extracted_data['vendor'] = extracted_data['customer']
        
        return extracted_data
    
    def _extract_customer_data(self, response_text: str) -> Dict[str, Any]:
        """Extract customer data from the AI response"""
        extracted_data = {
            'name': None,
            'email': None,
            'phone': None,
            'gst_number': None,
            'address': None
        }
        
        # Patterns to extract data from response
        patterns = {
            'name': ['Name:', 'Name :', 'Customer Name:'],
            'email': ['Email:', 'Email :', 'Email Address:'],
            'phone': ['Phone:', 'Phone :', 'Contact:', 'Mobile:'],
            'gst_number': ['GST Number:', 'GST:', 'GSTIN:'],
            'address': ['Address:', 'Address :', 'Location:']
        }
        
        # Extract data using patterns
        lines = response_text.split('\n')
        for line in lines:
            line = line.strip()
            
            for field, field_patterns in patterns.items():
                for pattern in field_patterns:
                    if line.startswith(pattern):
                        value = line[len(pattern):].strip()
                        extracted_data[field] = value
                        break
        
        return extracted_data
    
    def _extract_vendor_data(self, response_text: str) -> Dict[str, Any]:
        """Extract vendor data from the AI response"""
        extracted_data = {
            'name': None,
            'email': None,
            'phone': None,
            'gst_number': None,
            'address': None
        }
        
        # Patterns to extract data from response
        patterns = {
            'name': ['Name:', 'Name :', 'Vendor Name:'],
            'email': ['Email:', 'Email :', 'Email Address:'],
            'phone': ['Phone:', 'Phone :', 'Contact:', 'Mobile:'],
            'gst_number': ['GST Number:', 'GST:', 'GSTIN:'],
            'address': ['Address:', 'Address :', 'Location:']
        }
        
        # Extract data using patterns
        lines = response_text.split('\n')
        for line in lines:
            line = line.strip()
            
            for field, field_patterns in patterns.items():
                for pattern in field_patterns:
                    if line.startswith(pattern):
                        value = line[len(pattern):].strip()
                        extracted_data[field] = value
                        break
        
        return extracted_data
    
    def generate_financial_insights(self, financial_data: List[Dict[str, Any]]) -> str:
        """Generate insights based on financial data using Gemini"""
        if not GEMINI_AVAILABLE or not self.model:
            return "Sorry, insights generation is unavailable without Gemini API access."
            
        try:
            # Format the financial data into a readable prompt
            data_prompt = "Here is recent financial data:\n"
            for item in financial_data[:20]:  # Limit to recent entries
                data_prompt += f"- {item['date']}: {item['description']} - {item['paid_amount']} ({item['category']})\n"
                
            prompt = f"""
            {data_prompt}
            
            Based on this financial data, provide 3 key insights and recommendations.
            Focus on spending patterns, potential savings, or financial opportunities.
            Keep your response concise and actionable.
            """
            
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Error generating financial insights: {str(e)}")
            return f"Sorry, I couldn't generate insights due to an error: {str(e)}"


