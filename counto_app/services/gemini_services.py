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
            - Intent type (TRANSACTION, CUSTOMER, VENDOR, UNKNOWN)
            - Boolean indicating if this is a query (True) or data entry (False)
        """
        if not GEMINI_AVAILABLE or not self.model:
            logger.error("Gemini service unavailable")
            return "Sorry, the AI service is currently unavailable.", {}, "UNKNOWN", False
            
        # Get current date for transaction processing
        current_date = datetime.now().strftime('%B %d, %Y')
        
        # Determine the intent type (transaction, customer, or vendor)
        intent_type = self._determine_intent_type(user_message)
        
        print("Intent type: ", intent_type)
        # For unknown intents, handle general queries including accounting questions
        # if intent_type == "UNKNOWN":
        #     try:
        #         # Enhanced prompt for accounting-related queries
        #         print("Unknown intent")
        #         general_prompt = f"""You are a knowledgeable accounting assistant. Please respond to the following query in a clear and concise manner.
                
        #         If the question is related to accounting principles, bookkeeping, financial reporting, or general financial advice, provide a helpful and accurate response.
        #         If the question is not related to accounting or finance, simply state that you are an accounting-focused assistant and can help with financial matters.
                
        #         Current date: {current_date}
        #         Query: {user_message}
                
        #         Response:"""
                
        #         response = self.model.generate_content(general_prompt)
        #         response_text = response.text.strip()
        #         print("General Response: ", response_text)
        #         logger.info("Processed general query with Gemini")
        #         return response_text, {}, "UNKNOWN", True
        #     except Exception as e:
        #         logger.error(f"Error processing general query: {str(e)}")
        #         return "I'm sorry, I encountered an error processing your request. Please try again.", {}, "UNKNOWN", True
        
        # For known intents, proceed with the existing logic
        # Check if this is likely a query based on the user message
        query_patterns = [
            r'how much', r'what is', r'what were', r'what was', r'show me', r'tell me', r'report', 
            r'status', r'balance', r'overview', r'summary', r'total',
            r'analyse', r'analyze', r'check', r'find', r'search', r'list'
        ]
        is_likely_query = any(re.search(pattern, user_message.lower()) for pattern in query_patterns)
        
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
                else:
                    # Enhanced prompt for accounting-related queries
                    print("Unknown intent")
                    general_prompt = f"""You are a knowledgeable accounting assistant. Please respond to the following query in a clear and concise manner.
                    
                    If the question is related to accounting principles, bookkeeping, financial reporting, or general financial advice, provide a helpful and accurate response.
                    If the question is not related to accounting or finance, simply state that you are an accounting-focused assistant and can help with financial matters.
                    
                    Current date: {current_date}
                    Query: {user_message}
                    
                    Response:"""
                    
                    response = self.model.generate_content(general_prompt)
                    response_text = response.text.strip()
                    print("General Response: ", response_text)
                    logger.info("Processed general query with Gemini")
                    return response_text, {}, "UNKNOWN", True
            
            # Clean up formatting issues
            if response_text.startswith(":"):
                response_text = response_text[1:].strip()
            
            print("response_text", response_text)
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
        total_matches = transaction_count + customer_count + vendor_count
        
        # If no keywords matched, return UNKNOWN
        if total_matches == 0:
            return "UNKNOWN"
            
        # If we have matches, return the category with the highest count
        max_count = max(transaction_count, customer_count, vendor_count)
        
        # If the maximum count is too low, treat as UNKNOWN
        if max_count < 1:
            return "UNKNOWN"
            
        # Return the intent with the highest count
        if transaction_count == max_count:
            return "TRANSACTION"
        elif customer_count == max_count:
            return "CUSTOMER"
        else:
            return "VENDOR"
    
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
        FUNCTION 4: ANSWERING QUERIES ABOUT FINANCES

        You will receive a list of all relevant transactions, customers, or vendors. Based on the user's query, classify it into one of the following tags:
        - QUERY_TRANSACTION: For income or expense-related queries
        - QUERY_CUSTOMER: For customer-related queries
        - QUERY_VENDOR: For vendor-related queries

        RULES FOR RESPONDING:

        1. TIME FILTERING:
        - When users ask for time periods like "today", "yesterday", "this week", "last month", etc., filter the data accordingly.
        - You will be given all data; apply filters based on the user's query. Current date is {current_date}

        2. TRANSACTION QUERIES (QUERY_TRANSACTION):     
        - You will be provided with ALL transaction data as a list of transactions
        - When a user asks about "today", "yesterday", "last week", "this month", "last month", etc., filter the transaction data accordingly
        - "burn" or "spend" refers to expenses
        - Calculate and display the total amount spent/earned for the specified time period
        - List the matching transactions

        3. CUSTOMER OR VENDOR QUERIES:
        - Return the **total count** and list relevant names or details.
        - Include relevant filters like city or category if provided.
        - contact details of the customer or vendor if asked

        4. If no matching data is found, respond clearly: 
        - “There are no matching records in the provided dataset.”

        EXAMPLES:
        - Query: "Show me my expenses this month"
        Response:
        QUERY_TRANSACTION
        Total: 2100.00
        1. 2025-05-22 - Paid Mr. Das for COGS - EXPENSE/500 (Mr. Das)
        2. 2025-05-22 - Payment to Mr. Raju - EXPENSE/500 (Mr. Raju)
        3. 2025-05-22 - Payment to Mr. Shah - EXPENSE/500 (Mr. Shah)
        4. 2025-05-22 - Paid Pakshi for COGS - EXPENSE/600 (Pakshi)

        - Query: "List all customers in Delhi"
        Response:
        QUERY_CUSTOMER
        Total customers: 3
        1. Prakash Traders (Delhi)
        2. Suman & Co. (Delhi)
        3. Omkar Textiles (Delhi)
        """

        
        critical_instructions = """
        CRITICAL INSTRUCTIONS:
        1. ALWAYS treat user mentions as real data they want to record in the app
        2. NEVER explain how accounting works - users are using you as a financial recording tool
        3. ALWAYS start responses with one of the specified tags
        4. Format data in a clear list format as shown above
        5. ALWAYS ask "Would you like me to record this [transaction/customer/vendor]?" after showing details
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
        data_str = "\n\nHere is your COMPLETE DATA for querying. All amounts are in numbers only (no currency symbols):\n"
        
        if intent_type == "TRANSACTION":
            data_str += "ID | DATE       | DESCRIPTION                     | AMOUNT  | CATEGORY          | TYPE    | STATUS | CUSTOMER/VENDOR\n"
            data_str += "---|------------|--------------------------------|---------|-------------------|---------|--------|-----------------\n"
            
            for i, tx in enumerate(data, 1):
                date = tx.get('date', 'Unknown date')
                if isinstance(date, datetime):
                    date = date.strftime('%Y-%m-%d')
                desc = tx.get('description', 'No description')
                
                # Handle amount formatting
                amount = '0.00'
                if 'paid_amount' in tx and tx['paid_amount']:
                    amount_str = str(tx['paid_amount'])
                    
                    # Handle format: ₹EXPENSE/500 or ₹INCOME/500
                    if '/' in amount_str:
                        # Extract the number after the last slash
                        amount_str = amount_str.split('/')[-1]
                    
                    # Remove any remaining non-numeric characters except decimal point
                    amount_str = ''.join(c for c in amount_str if c.isdigit() or c == '.')
                    
                    try:
                        # Convert to float and format to 2 decimal places
                        amount = f"{float(amount_str):.2f}" if amount_str else '0.00'
                    except (ValueError, TypeError):
                        amount = '0.00'
                
                category = tx.get('category', 'Uncategorized')
                tx_type = tx.get('transaction_type', 'UNKNOWN')
                status = tx.get('status', 'PAID')
                party = tx.get('customer', '') if tx_type == 'INCOME' else tx.get('vendor', '')
                
                # Format in a table-like structure
                data_str += f"{i:2d} | {date} | {desc[:30]:30} | {amount:>7} | {category[:15]:15} | {tx_type:7} | {status:6} | {party[:15]}\n"
            
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
        data_str += "\nWhen analyzing this data for time periods and amounts:\n"
        data_str += "1. 'Today' refers to transactions/records on current date\n"
        data_str += "2. 'This month' refers to the current calendar month\n"
        data_str += "3. 'This year' refers to the current calendar year\n"
        data_str += "4. All amounts are in numbers only (no currency symbols)\n"
        data_str += "5. For transaction queries, calculate and show the total amount\n"
        data_str += "6. For expense/income queries, show the total for each category\n"
        
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
        
        print("Extracting transaction data from response using gemini")
        extracted_data = {
            'date': datetime.now().strftime('%Y-%m-%d'),  # Always use current date
            'description': 'No description',
            'category': 'Uncategorized',
            'transaction_type': 'EXPENSE',  # Default to expense
            'amount': None,
            'customer': None,
            'vendor': None,
            'payment_method': 'Cash',  # Default payment method
            'reference_number': None,
            'notes': None
        }
        
        # Patterns to extract data from response
        patterns = {
            'date': ['Date:', 'Date :', 'DATE:'],
            'description': ['Description:', 'Description :', 'DESC:'],
            'category': ['Category:', 'Category :', 'CAT:'],
            'transaction_type': ['Type:', 'Type :', 'Transaction Type:'],
            'amount': ['Amount:', 'Amount :', 'AMT:', 'Paid Amount:'],
            'customer': ['Customer:', 'Customer :', 'Client:'],
            'vendor': ['Vendor:', 'Vendor :', 'Supplier:', 'Paid to:'],
            'payment_method': ['Payment Method:', 'Payment :', 'Method:'],
            'reference_number': ['Reference:', 'Ref No:', 'Reference Number:'],
            'notes': ['Notes:', 'Note:', 'Comments:']
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
        
        # Convert amount string to float
        if extracted_data['amount']:
            extracted_data['amount'] = safe_float_convert(extracted_data['amount'])
        
        # Set default amount if not provided
        if extracted_data['amount'] is None:
            extracted_data['amount'] = 0.0
            
        # Remove placeholder text from fields
        for field in ['payment_method', 'reference_number', 'notes']:
            if extracted_data[field] and ('[' in extracted_data[field] and ']' in extracted_data[field]):
                # Check if this is just a placeholder
                if extracted_data[field].startswith('[') and extracted_data[field].endswith(']'):
                    extracted_data[field] = None  # Replace placeholder with None
                    
        # Default payment_method to 'Cash' if not specified
        if not extracted_data['payment_method']:
            extracted_data['payment_method'] = 'Cash'
            
        # Ensure party is correctly assigned based on transaction type
        # For EXPENSE transactions, the vendor receives the payment
        # For INCOME transactions, the customer provides the payment
        if extracted_data['transaction_type'] == 'EXPENSE' and not extracted_data['vendor'] and extracted_data['customer']:
            extracted_data['vendor'] = extracted_data['customer']
            
        if extracted_data['transaction_type'] == 'INCOME' and not extracted_data['customer'] and extracted_data['vendor']:
            extracted_data['customer'] = extracted_data['vendor']
        
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


    def generate_actionable_insights(self, transactions: List[Dict], customers: List[Dict], vendors: List[Dict]) -> str:
        """Generate text-based summary with actionable insights"""
        if not GEMINI_AVAILABLE or not self.model:
            return "Financial insights unavailable at the moment. Please try again later."
        
        try:
            prompt = f"""
            Analyze this business data and provide a concise, actionable summary in this exact format:

            ## Financial Health Snapshot
            [Brief 2-line overview of financial position]

            ## Spending Analysis
            - Top 3 expense categories: [Category1] ([%]), [Category2] ([%]), [Category3] ([%])
            - Unusual spending pattern: [Identify any anomalies]
            - Immediate cost-saving opportunity: [Specific recommendation]

            ## Customer Management
            - Highest receivable: [Customer Name] (₹[Amount])
            - Overdue alerts: [Number] customers with ₹[Total Amount] overdue
            - Priority action: [Specific collection strategy]

            ## Vendor Relationships
            - Top vendor by payments: [Vendor Name] (₹[Amount])
            - Negotiation opportunity: [Vendor Name] ([Reason])
            - Payment optimization: [Specific suggestion]

            ## Immediate Next Steps
            1. [Actionable step 1]
            2. [Actionable step 2]
            3. [Actionable step 3]

            Use bullet points, keep amounts in ₹, and focus on concrete actions. Data:

            Transactions (Last 30 days):
            {json.dumps(transactions[:20], indent=2)}

            Customers:
            {json.dumps(customers[:10], indent=2)}

            Vendors:
            {json.dumps(vendors[:10], indent=2)}
            """
            
            response = self.model.generate_content(prompt)
            return response.text
            
        except Exception as e:
            logger.error(f"Insight generation failed: {str(e)}")
            return "Could not generate insights. Please check your data and try again."
