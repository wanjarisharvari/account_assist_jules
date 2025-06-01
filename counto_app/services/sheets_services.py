from datetime import datetime
from typing import Dict, Any, List, Tuple
from django.conf import settings
from google.oauth2 import service_account
from googleapiclient.discovery import build
import logging

logger = logging.getLogger(__name__)

class GoogleSheetsService:
    def __init__(self):
        # Set up credentials and API client
        credentials_path = settings.GOOGLE_SHEETS_CREDENTIALS_FILE
        self.spreadsheet_id = settings.GOOGLE_SHEETS_SPREADSHEET_ID
        self.transactions_range = settings.GOOGLE_SHEETS_TRANSACTIONS_RANGE
        self.customers_range = getattr(settings, 'GOOGLE_SHEETS_CUSTOMERS_RANGE', 'Customers!A2:F')
        self.vendors_range = getattr(settings, 'GOOGLE_SHEETS_VENDORS_RANGE', 'Vendors!A2:F')
        
        # Check if credentials file exists
        if not os.path.exists(credentials_path):
            raise FileNotFoundError(f"Google Sheets credentials file not found at {credentials_path}")
        
        # Create credentials from the service account file
        self.credentials = service_account.Credentials.from_service_account_file(
            credentials_path, 
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        
        # Build the service
        self.service = build('sheets', 'v4', credentials=self.credentials)
        self.sheet = self.service.spreadsheets()
        
        # Ensure all required sheets exist
        self._ensure_sheet_exists('Transactions', [
            'Date', 'Description', 'Category', 'Amount', 'Transaction Type',
            'Customer', 'Vendor', 'Payment Method', 'Reference Number', 'Notes'
        ])
        self._ensure_sheet_exists('Customers', [
            'Name', 'Email', 'Phone', 'GST Number', 'Address', 'Total Receivable', 'Total Received', 'Outstanding Balance', 'Created At'
        ])
        self._ensure_sheet_exists('Vendors', [
            'Name', 'Email', 'Phone', 'GST Number', 'Address', 'Total Payable', 'Total Paid', 'Outstanding Balance', 'Created At'
        ])
        
    def _ensure_sheet_exists(self, sheet_name: str, headers: List[str]):
        """Ensure that the specified sheet exists with the correct headers"""
        try:
            # Get the spreadsheet info
            spreadsheet = self.sheet.get(spreadsheetId=self.spreadsheet_id).execute()
            sheets = spreadsheet.get('sheets', [])
            
            # Check if our sheet exists
            sheet_exists = False
            for sheet in sheets:
                if sheet['properties']['title'] == sheet_name:
                    sheet_exists = True
                    break
            
            # If the sheet doesn't exist, create it
            if not sheet_exists:
                logger.info(f"Sheet '{sheet_name}' not found. Creating it.")
                body = {
                    'requests': [{
                        'addSheet': {
                            'properties': {
                                'title': sheet_name
                            }
                        }
                    }]
                }
                self.sheet.batchUpdate(spreadsheetId=self.spreadsheet_id, body=body).execute()
                
                # Add headers to the new sheet
                self.sheet.values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{sheet_name}!A1:{chr(65 + len(headers) - 1)}1",
                    valueInputOption='RAW',
                    body={'values': [headers]}
                ).execute()
                
                logger.info(f"Created sheet '{sheet_name}' with headers: {headers}")
        except Exception as e:
            logger.error(f"Error ensuring sheet '{sheet_name}' exists: {e}")
    
    def get_all_transactions(self) -> List[Dict[str, Any]]:
        """Retrieve all transactions from the Google Sheet"""
        result = self.sheet.values().get(
            spreadsheetId=self.spreadsheet_id,
            range=self.transactions_range
        ).execute()
        
        values = result.get('values', [])
        
        # If no data, return empty list
        if not values:
            return []
        
        # Column headers for transactions
        headers = [
            'date', 'description', 'category', 'expected_amount', 'paid_amount', 
            'transaction_type', 'status', 'customer', 'vendor', 'payment_method', 
            'reference_number'
        ]
        
        # Convert to list of dictionaries
        transactions = []
        for row in values:
            # Pad row with empty strings if it's shorter than headers
            padded_row = row + [''] * (len(headers) - len(row))
            transaction = dict(zip(headers, padded_row))
            transactions.append(transaction)
        
        return transactions
    
    def get_all_customers(self) -> List[Dict[str, Any]]:
        """Retrieve all customers from the Google Sheet"""
        result = self.sheet.values().get(
            spreadsheetId=self.spreadsheet_id,
            range=self.customers_range
        ).execute()
        
        values = result.get('values', [])
        
        # If no data, return empty list
        if not values:
            return []
        
        # Column headers for customers with financial fields
        headers = [
            'name', 'email', 'phone', 'gst_number', 'address', 
            'total_receivable', 'total_received', 'outstanding_balance', 'created_at'
        ]
        
        # Convert to list of dictionaries
        customers = []
        for row in values:
            # Pad row with empty strings if it's shorter than headers
            padded_row = row + [''] * (len(headers) - len(row))
            customer = dict(zip(headers, padded_row))
            customers.append(customer)
        
        return customers
    
    def get_all_vendors(self) -> List[Dict[str, Any]]:
        """Retrieve all vendors from the Google Sheet"""
        result = self.sheet.values().get(
            spreadsheetId=self.spreadsheet_id,
            range=self.vendors_range
        ).execute()
        
        values = result.get('values', [])
        
        # If no data, return empty list
        if not values:
            return []
        
        # Column headers for vendors with financial fields
        headers = [
            'name', 'email', 'phone', 'gst_number', 'address', 
            'total_payable', 'total_paid', 'outstanding_balance', 'created_at'
        ]
        
        # Convert to list of dictionaries
        vendors = []
        for row in values:
            # Pad row with empty strings if it's shorter than headers
            padded_row = row + [''] * (len(headers) - len(row))
            vendor = dict(zip(headers, padded_row))
            vendors.append(vendor)
        
        return vendors
    
    def add_transaction(self, transaction_data: Dict[str, Any]) -> bool:
        """Add a new transaction to the Google Sheet"""
        try:
            # Format the data as a row with proper type conversion
            row = [
                # Convert date to string if it's a date/datetime object
                transaction_data.get('date').strftime('%Y-%m-%d') 
                if hasattr(transaction_data.get('date'), 'strftime')
                else str(transaction_data.get('date', '')),
                str(transaction_data.get('description', '')),
                str(transaction_data.get('category', '')),
                # Convert amount to float, then to string
                float(transaction_data.get('amount', 0)) if transaction_data.get('amount') is not None else '',
                str(transaction_data.get('transaction_type', '')),
                str(transaction_data.get('customer', '')),
                str(transaction_data.get('vendor', '')),
                str(transaction_data.get('payment_method', '')),
                str(transaction_data.get('reference_number', '')),
                str(transaction_data.get('notes', ''))
            ]
            
            # Append the row to the sheet with USER_ENTERED to handle different data types properly
            result = self.sheet.values().append(
                spreadsheetId=self.spreadsheet_id,
                range='Transactions!A1',
                valueInputOption='USER_ENTERED',  # Changed from RAW to USER_ENTERED
                insertDataOption='INSERT_ROWS',
                body={'values': [row]}
            ).execute()
            
            logger.info(f"Added new transaction: {transaction_data}")
            return True
        except Exception as e:
            logger.error(f"Error adding transaction: {e}", exc_info=True)
            return False
    
    def add_customer(self, customer_data: Dict[str, Any], update_existing: bool = True) -> bool:
        """
        Add or update a customer in the Google Sheet
        
        Args:
            customer_data: Dictionary containing customer data
            update_existing: If True, updates existing customer if found by name
        """
        try:
            # Get financial data from the Customer model if available
            name = customer_data.get('name', '').strip()
            if not name:
                logger.error("Cannot add customer: Name is required")
                return False
                
            total_receivable = float(customer_data.get('total_receivable', 0.0) or 0.0)
            total_received = float(customer_data.get('total_received', 0.0) or 0.0)
            outstanding_balance = float(customer_data.get('outstanding_balance', total_receivable - total_received) or 0.0)
            
            # Check if customer already exists
            if update_existing:
                existing_customers = self.search_customers({'name': name})
                if existing_customers:
                    # Update existing customer
                    customer_range = f"Customers!A{existing_customers[0]['_row']}:I{existing_customers[0]['_row']}"
                    
                    # Format the updated data as a row
                    row = [
                        name,
                        customer_data.get('email', ''),
                        customer_data.get('phone', ''),
                        customer_data.get('gst_number', ''),
                        customer_data.get('address', ''),
                        total_receivable,
                        total_received,
                        outstanding_balance,
                        existing_customers[0].get('created_at') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    ]
                    
                    # Update the row in the sheet
                    self.sheet.values().update(
                        spreadsheetId=self.spreadsheet_id,
                        range=customer_range,
                        valueInputOption='USER_ENTERED',
                        body={'values': [row]}
                    ).execute()
                    
                    logger.info(f"Updated existing customer: {name}")
                    return True
            
            # If we get here, either we're not updating or customer doesn't exist
            # Format the data as a new row
            row = [
                name,
                customer_data.get('email', ''),
                customer_data.get('phone', ''),
                customer_data.get('gst_number', ''),
                customer_data.get('address', ''),
                total_receivable,
                total_received,
                outstanding_balance,
                customer_data.get('created_at') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ]
            
            # Append the row to the sheet
            self.sheet.values().append(
                spreadsheetId=self.spreadsheet_id,
                range='Customers!A1',
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body={'values': [row]}
            ).execute()
            
            logger.info(f"Added new customer: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding/updating customer {customer_data.get('name', '')}: {e}", exc_info=True)
            return False
    
    def add_vendor(self, vendor_data: Dict[str, Any], update_existing: bool = True) -> bool:
        """
        Add or update a vendor in the Google Sheet
        
        Args:
            vendor_data: Dictionary containing vendor data
            update_existing: If True, updates existing vendor if found by name
        """
        try:
            # Get financial data from the Vendor model if available
            name = vendor_data.get('name', '').strip()
            if not name:
                logger.error("Cannot add vendor: Name is required")
                return False
                
            total_payable = float(vendor_data.get('total_payable', 0.0) or 0.0)
            total_paid = float(vendor_data.get('total_paid', 0.0) or 0.0)
            outstanding_balance = float(vendor_data.get('outstanding_balance', total_payable - total_paid) or 0.0)
            
            # Check if vendor already exists
            if update_existing:
                existing_vendors = self.search_vendors({'name': name})
                if existing_vendors:
                    # Update existing vendor
                    vendor_range = f"Vendors!A{existing_vendors[0]['_row']}:I{existing_vendors[0]['_row']}"
                    
                    # Format the updated data as a row
                    row = [
                        name,
                        vendor_data.get('email', ''),
                        vendor_data.get('phone', ''),
                        vendor_data.get('gst_number', ''),
                        vendor_data.get('address', ''),
                        total_payable,
                        total_paid,
                        outstanding_balance,
                        existing_vendors[0].get('created_at') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    ]
                    
                    # Update the row in the sheet
                    self.sheet.values().update(
                        spreadsheetId=self.spreadsheet_id,
                        range=vendor_range,
                        valueInputOption='USER_ENTERED',
                        body={'values': [row]}
                    ).execute()
                    
                    logger.info(f"Updated existing vendor: {name}")
                    return True
            
            # If we get here, either we're not updating or vendor doesn't exist
            # Format the data as a new row
            row = [
                name,
                vendor_data.get('email', ''),
                vendor_data.get('phone', ''),
                vendor_data.get('gst_number', ''),
                vendor_data.get('address', ''),
                total_payable,
                total_paid,
                outstanding_balance,
                vendor_data.get('created_at') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ]
            
            # Append the row to the sheet
            self.sheet.values().append(
                spreadsheetId=self.spreadsheet_id,
                range='Vendors!A1',
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body={'values': [row]}
            ).execute()
            
            logger.info(f"Added new vendor: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding/updating vendor {vendor_data.get('name', '')}: {e}", exc_info=True)
            return False
    
    def search_transactions(self, query_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search transactions based on query parameters"""
        transactions = self.get_all_transactions()
        
        # Filter transactions based on query parameters
        filtered_transactions = []
        for transaction in transactions:
            match = True
            
            for key, value in query_params.items():
                if key in transaction and str(transaction[key]).lower() != str(value).lower():
                    match = False
                    break
            
            if match:
                filtered_transactions.append(transaction)
        
        return filtered_transactions
    
    def search_customers(self, query_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Search customers based on query parameters
        
        Returns:
            List of customer dictionaries with an additional '_row' field indicating the row number in the sheet
        """
        try:
            # Get all customers with their row numbers
            result = self.sheet.values().get(
                spreadsheetId=self.spreadsheet_id,
                range='Customers!A2:I'  # Include all customer data columns
            ).execute()
            
            values = result.get('values', [])
            
            # If no data, return empty list
            if not values:
                return []
                
            # Get headers from the first row
            headers = [
                'name', 'email', 'phone', 'gst_number', 'address', 
                'total_receivable', 'total_received', 'outstanding_balance', 'created_at'
            ]
            
            # Convert to list of dictionaries with row numbers
            customers = []
            for i, row in enumerate(values, start=2):  # Start from row 2 (1-based index + 1 for header)
                # Pad row with empty strings if it's shorter than headers
                padded_row = row + [''] * (len(headers) - len(row))
                customer = dict(zip(headers, padded_row))
                customer['_row'] = i  # Add row number for updates
                
                # Convert numeric fields
                for field in ['total_receivable', 'total_received', 'outstanding_balance']:
                    try:
                        customer[field] = float(customer[field] or 0)
                    except (ValueError, TypeError):
                        customer[field] = 0.0
                
                customers.append(customer)
            
            # Filter based on query parameters
            filtered_customers = []
            for customer in customers:
                match = True
                
                for key, value in query_params.items():
                    if key == '_row':
                        continue  # Skip internal _row field
                        
                    if key in customer and str(customer[key]).lower() != str(value).lower():
                        match = False
                        break
                
                if match:
                    filtered_customers.append(customer)
            
            return filtered_customers
            
        except Exception as e:
            logger.error(f"Error searching customers: {e}", exc_info=True)
            return []
    
    def search_vendors(self, query_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Search vendors based on query parameters
        
        Returns:
            List of vendor dictionaries with an additional '_row' field indicating the row number in the sheet
        """
        try:
            # Get all vendors with their row numbers
            result = self.sheet.values().get(
                spreadsheetId=self.spreadsheet_id,
                range='Vendors!A2:I'  # Include all vendor data columns
            ).execute()
            
            values = result.get('values', [])
            
            # If no data, return empty list
            if not values:
                return []
                
            # Get headers from the first row
            headers = [
                'name', 'email', 'phone', 'gst_number', 'address', 
                'total_payable', 'total_paid', 'outstanding_balance', 'created_at'
            ]
            
            # Convert to list of dictionaries with row numbers
            vendors = []
            for i, row in enumerate(values, start=2):  # Start from row 2 (1-based index + 1 for header)
                # Pad row with empty strings if it's shorter than headers
                padded_row = row + [''] * (len(headers) - len(row))
                vendor = dict(zip(headers, padded_row))
                vendor['_row'] = i  # Add row number for updates
                
                # Convert numeric fields
                for field in ['total_payable', 'total_paid', 'outstanding_balance']:
                    try:
                        vendor[field] = float(vendor[field] or 0)
                    except (ValueError, TypeError):
                        vendor[field] = 0.0
                
                vendors.append(vendor)
            
            # Filter based on query parameters
            filtered_vendors = []
            for vendor in vendors:
                match = True
                
                for key, value in query_params.items():
                    if key == '_row':
                        continue  # Skip internal _row field
                        
                    if key in vendor and str(vendor[key]).lower() != str(value).lower():
                        match = False
                        break
                
                if match:
                    filtered_vendors.append(vendor)
            
            return filtered_vendors
            
        except Exception as e:
            logger.error(f"Error searching vendors: {e}", exc_info=True)
            return []