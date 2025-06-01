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
        
        logger.info(f"Determined intent type: {intent_type}")
        
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
            user_facing_response_text = response_text # Default for queries or if JSON parsing fails

            if not is_query and detected_intent != "UNKNOWN":
                try:
                    # Isolate JSON block and confirmation question
                    json_start_index = response_text.find('{')
                    json_end_index = response_text.rfind('}')
                    
                    if json_start_index != -1 and json_end_index != -1 and json_end_index > json_start_index:
                        json_string = response_text[json_start_index : json_end_index+1]
                        confirmation_question = response_text[json_end_index+1:].strip()

                        if not confirmation_question: # If Gemini didn't append the question
                             confirmation_question = f"Would you like me to record this {detected_intent.lower()}?"

                        user_facing_response_text = confirmation_question # This is what user sees

                        logger.info(f"Attempting to parse JSON: {json_string}")
                        if detected_intent == "TRANSACTION":
                            extracted_data = self._extract_transaction_data(json_string)
                        elif detected_intent == "CUSTOMER":
                            extracted_data = self._extract_customer_data(json_string)
                        elif detected_intent == "VENDOR":
                            extracted_data = self._extract_vendor_data(json_string)

                        if not extracted_data: # If JSON parsing failed in _extract methods
                            user_facing_response_text = "I found some data, but had trouble understanding all of it. Could you clarify?"
                            # Keep detected_intent so UI might still know it's a data entry task.
                    else:
                        logger.warning(f"Could not find valid JSON block in response for {tag}: {response_text}")
                        user_facing_response_text = "I found some data, but had trouble formatting it. Could you try phrasing that differently?"
                        # Reset detected_intent if we can't parse JSON, so it's treated as general response.
                        # detected_intent = "UNKNOWN" # Or handle appropriately
                except Exception as e:
                    logger.error(f"Error processing data entry response: {e}. Response: {response_text}")
                    user_facing_response_text = "I had some trouble processing that request. Please try again."
                    extracted_data = {} # Clear any partial data
                    # detected_intent = "UNKNOWN" # Or handle appropriately
            elif detected_intent == "UNKNOWN" and not is_query :
                 # This case is if Gemini returns UNKNOWN but it wasn't identified as a query.
                 # Could be a general statement not matching any data entry or query patterns.
                 # The original response_text (after stripping any tag) is probably best here.
                 pass


            # If after all processing, detected_intent is UNKNOWN and it's not a query,
            # it might be a general statement that doesn't fit other categories.
            # Fallback to a general accounting query handler or a polite "I can't help with that".
            if detected_intent == "UNKNOWN" and not is_likely_query: # is_likely_query checks original user_message
                logger.info(f"Handling as general unknown statement: {user_message}")
                # This part might need to be refined based on desired behavior for truly unhandled statements.
                # For now, we let user_facing_response_text be what Gemini returned (after tag stripping).
                # If response_text was a failed JSON parse, it might be an error message.
                # If it was from the initial "UNKNOWN" block, it would be Gemini's direct answer.
                # This path is a bit convoluted now. Let's ensure user_facing_response_text is reasonable.
                if not user_facing_response_text.strip() or user_facing_response_text == response_text : # if it hasn't been set to a confirmation Q
                     general_prompt = f"""You are a knowledgeable accounting assistant. Please respond to the following query in a clear and concise manner.
    Current date: {current_date}
    Query: {user_message}
    Response:"""
                     try:
                        gen_response = self.model.generate_content(general_prompt)
                        user_facing_response_text = gen_response.text.strip()
                        logger.info(f"Processed as general query with Gemini: {user_facing_response_text}")
                     except Exception as e:
                        logger.error(f"Error processing fallback general query: {str(e)}")
                        user_facing_response_text = "I'm sorry, I encountered an error processing your request. Please try again."


            logger.info(f"Final response to user: {user_facing_response_text}")
            logger.info(f"Extracted data: {extracted_data}")
            return user_facing_response_text, extracted_data, detected_intent, is_query
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
        When users mention expenses or income, respond with "DATA_ENTRY_TRANSACTION:" at the start, followed by a valid JSON string, and then the confirmation question.

        Example User Input: "I spent 500 on groceries for my business from 'Big Bazaar' using UPI, ref 123."
        Example AI Response:
        DATA_ENTRY_TRANSACTION: {
          "date": "{current_date}",
          "description": "groceries for my business",
          "category": "Groceries",
          "amount": 500.00,
          "transaction_type": "Expense",
          "payment_method": "UPI",
          "reference_number": "123",
          "party_name": "Big Bazaar"
        }
        Would you like me to record this transaction?

        Example User Input: "Received 2000 for freelance work from John Doe via bank transfer."
        Example AI Response:
        DATA_ENTRY_TRANSACTION: {
          "date": "{current_date}",
          "description": "freelance work",
          "category": "Income",
          "amount": 2000.00,
          "transaction_type": "Income",
          "payment_method": "Bank Transfer",
          "reference_number": null,
          "party_name": "John Doe"
        }
        Would you like me to record this transaction?

        JSON fields for TRANSACTIONS:
        - "date": String, "YYYY-MM-DD" format (use {current_date})
        - "description": String, what was purchased or income source.
        - "category": String, e.g., Food, Rent, Salary, Business.
        - "amount": Float, numeric value of the transaction.
        - "transaction_type": String, either "Expense" or "Income".
        - "payment_method": String, e.g., Cash, Card, UPI, Bank Transfer.
        - "reference_number": String or null, optional.
        - "party_name": String or null, the name of the customer (for Income) or vendor (for Expense).
        """
        
        customer_prompt = """
        FUNCTION 2: CUSTOMER DATA EXTRACTION
        When users mention adding or updating customer information, respond with "DATA_ENTRY_CUSTOMER:" at the start, followed by a valid JSON string, and then the confirmation question.

        Example User Input: "Add a new customer ABC Corp, email contact@abccorp.com, phone 1234567890, GST ID ABC123XYZ, address 1 Main St"
        Example AI Response:
        DATA_ENTRY_CUSTOMER: {
          "name": "ABC Corp",
          "email": "contact@abccorp.com",
          "phone": "1234567890",
          "gst_number": "ABC123XYZ",
          "address": "1 Main St"
        }
        Would you like me to record this customer?

        JSON fields for CUSTOMERS:
        - "name": String, Customer's name.
        - "email": String or null, Customer's email.
        - "phone": String or null, Customer's phone number.
        - "gst_number": String or null, Customer's GST number.
        - "address": String or null, Customer's address.
        """
        
        vendor_prompt = """
        FUNCTION 3: VENDOR DATA EXTRACTION
        When users mention adding or updating vendor information, respond with "DATA_ENTRY_VENDOR:" at the start, followed by a valid JSON string, and then the confirmation question.

        Example User Input: "New vendor: XYZ Supplies, email is support@xyz.com, phone 9876543210."
        Example AI Response:
        DATA_ENTRY_VENDOR: {
          "name": "XYZ Supplies",
          "email": "support@xyz.com",
          "phone": "9876543210",
          "gst_number": null,
          "address": null
        }
        Would you like me to record this vendor?

        JSON fields for VENDORS:
        - "name": String, Vendor's name.
        - "email": String or null, Vendor's email.
        - "phone": String or null, Vendor's phone number.
        - "gst_number": String or null, Vendor's GST number.
        - "address": String or null, Vendor's address.
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
        1. ALWAYS treat user mentions as real data they want to record in the app.
        2. NEVER explain how accounting works - users are using you as a financial recording tool.
        3. ALWAYS start responses with one of the specified DATA_ENTRY or QUERY tags.
        4. For DATA_ENTRY tasks, the response MUST be the TAG, followed by a COLON, a SPACE, then a VALID JSON string containing the extracted data, and NOTHING ELSE before the JSON.
        5. AFTER the JSON string for DATA_ENTRY tasks, ALWAYS ask the confirmation question: "Would you like me to record this [transaction/customer/vendor]?" on a new line.
        6. Ensure the JSON is correctly formatted (keys and strings in double quotes, numbers as numbers, null for missing optional values).
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
    
    def _extract_transaction_data(self, json_string: str) -> Dict[str, Any]:
        """Extract transaction data from a JSON string"""
        try:
            data = json.loads(json_string)
            # Basic validation or mapping if needed, e.g., ensuring 'amount' is float
            if 'amount' in data and isinstance(data['amount'], (str, int, float)):
                try:
                    data['amount'] = float(data['amount'])
                except ValueError:
                    logger.warning(f"Could not convert amount '{data['amount']}' to float. Setting to 0.0.")
                    data['amount'] = 0.0
            elif 'amount' not in data: # Ensure amount field exists
                 data['amount'] = 0.0
            
            # Map party_name to customer/vendor fields
            party_name = data.pop('party_name', None) # Use pop to remove party_name if it exists
            if party_name:
                if data.get('transaction_type') == 'Income': # Match prompt's "Income"
                    data['customer'] = party_name
                    data['vendor'] = None
                elif data.get('transaction_type') == 'Expense': # Match prompt's "Expense"
                    data['vendor'] = party_name
                    data['customer'] = None
            
            # Ensure date is in YYYY-MM-DD from whatever Gemini might send based on current_date format 'Month D, YYYY'
            # The prompt tells Gemini to use YYYY-MM-DD for the 'date' field in JSON, so direct parsing should be fine.
            # If Gemini deviates, this would be the place to re-parse data.get('date').
            # For now, trust Gemini follows the new JSON spec in the prompt.

            return data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON for transaction data: {e}. JSON string: {json_string}")
            return {}
    
    def _extract_customer_data(self, json_string: str) -> Dict[str, Any]:
        """Extract customer data from a JSON string"""
        try:
            data = json.loads(json_string)
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON for customer data: {e}. JSON string: {json_string}")
            return {}
    
    def _extract_vendor_data(self, json_string: str) -> Dict[str, Any]:
        """Extract vendor data from a JSON string"""
        try:
            data = json.loads(json_string)
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON for vendor data: {e}. JSON string: {json_string}")
            return {}
    
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
