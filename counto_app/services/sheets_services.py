# import os
# import json
# from typing import List, Dict, Any, Optional
# from google.oauth2 import service_account
# from googleapiclient.discovery import build
# from datetime import datetime, timedelta
# from django.conf import settings

# class GoogleSheetsService:
#     def __init__(self):
#         # Set up credentials and API client
#         credentials_path = settings.GOOGLE_SHEETS_CREDENTIALS_FILE
#         self.spreadsheet_id = settings.GOOGLE_SHEETS_SPREADSHEET_ID
#         self.range_name = settings.GOOGLE_SHEETS_RANGE_NAME
        
#         # Check if credentials file exists
#         if not os.path.exists(credentials_path):
#             raise FileNotFoundError(f"Google Sheets credentials file not found at {credentials_path}")
        
#         # Create credentials from the service account file
#         self.credentials = service_account.Credentials.from_service_account_file(
#             credentials_path, 
#             scopes=['https://www.googleapis.com/auth/spreadsheets']
#         )
        
#         # Build the service
#         self.service = build('sheets', 'v4', credentials=self.credentials)
#         self.sheet = self.service.spreadsheets()
        
#         # Ensure the sheet exists
#         self._ensure_sheet_exists()
        
#     def _ensure_sheet_exists(self):
#         """Ensure that the sheet named in range_name exists"""
#         try:
#             # Parse the sheet name from range_name (e.g., 'Transactions!A2:H' -> 'Transactions')
#             sheet_name = self.range_name.split('!')[0] if '!' in self.range_name else 'Transactions'
            
#             # Get the spreadsheet info
#             spreadsheet = self.sheet.get(spreadsheetId=self.spreadsheet_id).execute()
#             sheets = spreadsheet.get('sheets', [])
            
#             # Check if our sheet exists
#             sheet_exists = False
#             for sheet in sheets:
#                 if sheet['properties']['title'] == sheet_name:
#                     sheet_exists = True
#                     break
            
#             # If the sheet doesn't exist, create it
#             if not sheet_exists:
#                 print(f"Sheet '{sheet_name}' not found. Creating it.")
#                 body = {
#                     'requests': [{
#                         'addSheet': {
#                             'properties': {
#                                 'title': sheet_name
#                             }
#                         }
#                     }]
#                 }
#                 self.sheet.batchUpdate(spreadsheetId=self.spreadsheet_id, body=body).execute()
                
#                 # Add headers to the new sheet
#                 headers = [
#                     'Date', 'Description', 'Category', 'Amount', 'Transaction Type', 
#                     'Payment Method', 'Reference Number', 'Party'
#                 ]
#                 self.sheet.values().update(
#                     spreadsheetId=self.spreadsheet_id,
#                     range=f"{sheet_name}!A1:H1",
#                     valueInputOption='RAW',
#                     body={'values': [headers]}
#                 ).execute()
#         except Exception as e:
#             print(f"Error ensuring sheet exists: {e}")
    
#     def get_all_transactions(self) -> List[Dict[str, Any]]:
#         """Retrieve all transactions from the Google Sheet"""
#         result = self.sheet.values().get(
#             spreadsheetId=self.spreadsheet_id,
#             range=self.range_name
#         ).execute()
        
#         values = result.get('values', [])
        
#         # If no data, return empty list
#         if not values:
#             return []
        
#         # Column headers (assuming these match your schema)
#         headers = ['date', 'description', 'category', 'amount', 'transaction_type', 
#                   'payment_method', 'reference_number', 'party']
        
#         # Convert to list of dictionaries
#         transactions = []
#         for row in values:
#             # Pad row with empty strings if it's shorter than headers
#             padded_row = row + [''] * (len(headers) - len(row))
#             transaction = dict(zip(headers, padded_row))
            
#             # Convert date string to date object if possible
#             try:
#                 date_str = transaction['date']
#                 # Try different date formats
#                 for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
#                     try:
#                         transaction['date'] = datetime.strptime(date_str, fmt).date()
#                         break
#                     except ValueError:
#                         continue
#             except:
#                 # Keep as string if conversion fails
#                 pass
                
#             transactions.append(transaction)
            
#         return transactions
    
#     def add_transaction(self, transaction_data: Dict[str, Any]) -> bool:
#         """Add a new transaction to the Google Sheet"""
#         # Format data for Google Sheets
#         row = [
#             transaction_data.get('date', ''),
#             transaction_data.get('description', ''),
#             transaction_data.get('category', ''),
#             transaction_data.get('amount', ''),
#             transaction_data.get('transaction_type', ''),
#             transaction_data.get('payment_method', ''),
#             transaction_data.get('reference_number', ''),
#             transaction_data.get('party', '')
#         ]
        
#         # Convert date to string if it's a date object
#         if isinstance(row[0], datetime) or hasattr(row[0], 'strftime'):
#             row[0] = row[0].strftime('%Y-%m-%d')
            
#         # Format amount as string
#         if row[3] and not isinstance(row[3], str):
#             row[3] = str(row[3])
            
#         # Append row to the sheet
#         body = {
#             'values': [row]
#         }
        
#         try:
#             # Parse the sheet name from range_name
#             sheet_name = self.range_name.split('!')[0] if '!' in self.range_name else 'Transactions'
            
#             # Use a safer range format
#             safe_range = f"{sheet_name}!A:H"
            
#             # This will add the new row at the end of the existing data
#             result = self.sheet.values().append(
#                 spreadsheetId=self.spreadsheet_id,
#                 range=safe_range,
#                 valueInputOption='USER_ENTERED',
#                 insertDataOption='INSERT_ROWS',
#                 body=body
#             ).execute()
            
#             return True
#         except Exception as e:
#             print(f"Error adding transaction to Google Sheets: {e}")
#             return False
    
    # def query_transactions(self, query_params: Dict[str, Any]) -> List[Dict[str, Any]]:
    #     """
    #     Query transactions based on various parameters
        
    #     Example query_params:
    #     {
    #         'category': 'Marketing',
    #         'start_date': '2023-01-01',
    #         'end_date': '2023-12-31',
    #         'min_amount': 100,
    #         'max_amount': 1000,
    #         'time_period': 'last_week'  # New parameter for time-based queries
    #     }
    #     """
    #     # Get all transactions
    #     all_transactions = self.get_all_transactions()
    #     filtered_transactions = []
        
    #     # Process time-based parameters
    #     start_date = None
    #     end_date = None
    #     today = datetime.now().date()
        
    #     # Handle time period queries like "last week", "this month", etc.
    #     if 'time_period' in query_params:
    #         time_period = query_params['time_period'].lower()
            
    #         # Handle various time periods
    #         if time_period in ['today', 'this_day']:
    #             start_date = today
    #             end_date = today
    #         elif time_period in ['yesterday']:
    #             start_date = today - timedelta(days=1)
    #             end_date = today - timedelta(days=1)
    #         elif time_period in ['this_week', 'current_week']:
    #             # Start of current week (Monday)
    #             start_date = today - timedelta(days=today.weekday())
    #             end_date = today
    #         elif time_period in ['last_week', 'previous_week']:
    #             # Start of last week (Monday)
    #             start_date = today - timedelta(days=today.weekday() + 7)
    #             end_date = today - timedelta(days=today.weekday() + 1)
    #         elif time_period in ['this_month', 'current_month']:
    #             # Start of current month
    #             start_date = today.replace(day=1)
    #             end_date = today
    #         elif time_period in ['last_month', 'previous_month']:
    #             # Last month
    #             if today.month == 1:  # January
    #                 start_date = today.replace(year=today.year-1, month=12, day=1)
    #                 end_date = today.replace(year=today.year-1, month=12, day=31)
    #             else:
    #                 start_date = today.replace(month=today.month-1, day=1)
    #                 # End of last month
    #                 if today.month == 3:  # March, handle February
    #                     if (today.year % 4 == 0 and today.year % 100 != 0) or (today.year % 400 == 0):  # Leap year
    #                         end_date = today.replace(month=2, day=29)
    #                     else:
    #                         end_date = today.replace(month=2, day=28)
    #                 else:
    #                     # Last day of the previous month
    #                     last_day = (today.replace(day=1) - timedelta(days=1)).day
    #                     end_date = today.replace(month=today.month-1, day=last_day)
    #         elif time_period in ['this_year', 'current_year']:
    #             # Start of current year
    #             start_date = today.replace(month=1, day=1)
    #             end_date = today
    #         elif time_period in ['last_year', 'previous_year']:
    #             # Last year
    #             start_date = today.replace(year=today.year-1, month=1, day=1)
    #             end_date = today.replace(year=today.year-1, month=12, day=31)
    #         elif time_period in ['last_30_days', 'past_30_days', 'month']:
    #             start_date = today - timedelta(days=30)
    #             end_date = today
    #         elif time_period in ['last_90_days', 'past_90_days', 'quarter']:
    #             start_date = today - timedelta(days=90)
    #             end_date = today
    #         elif time_period in ['last_180_days', 'past_180_days', 'half_year']:
    #             start_date = today - timedelta(days=180)
    #             end_date = today
    #         elif time_period in ['last_365_days', 'past_365_days', 'year']:
    #             start_date = today - timedelta(days=365)
    #             end_date = today
        
    #     # Override with explicit start/end dates if provided
    #     if 'start_date' in query_params:
    #         try:
    #             start_date = datetime.strptime(query_params['start_date'], '%Y-%m-%d').date()
    #         except Exception as e:
    #             print(f"Error parsing start_date: {e}")
                
    #     if 'end_date' in query_params:
    #         try:
    #             end_date = datetime.strptime(query_params['end_date'], '%Y-%m-%d').date()
    #         except Exception as e:
    #             print(f"Error parsing end_date: {e}")
        
    #     # Filter transactions based on query parameters
    #     for transaction in all_transactions:
    #         include = True
            
    #         # Filter by category
    #         if 'category' in query_params and transaction.get('category'):
    #             if query_params['category'].lower() not in transaction['category'].lower():
    #                 include = False
                    
    #         # Filter by description
    #         if 'description' in query_params and transaction.get('description'):
    #             if query_params['description'].lower() not in transaction['description'].lower():
    #                 include = False
            
    #         # Filter by amount range
    #         if 'min_amount' in query_params and transaction.get('amount'):
    #             try:
    #                 amount = float(str(transaction['amount']).replace('$', '').replace(',', ''))
    #                 if amount < float(query_params['min_amount']):
    #                     include = False
    #             except Exception as e:
    #                 print(f"Error parsing min_amount: {e}")
                    
    #         if 'max_amount' in query_params and transaction.get('amount'):
    #             try:
    #                 amount = float(str(transaction['amount']).replace('$', '').replace(',', ''))
    #                 if amount > float(query_params['max_amount']):
    #                     include = False
    #             except Exception as e:
    #                 print(f"Error parsing max_amount: {e}")
            
    #         # Filter by date range
    #         if start_date and isinstance(transaction.get('date'), datetime):
    #             if transaction['date'].date() < start_date:
    #                 include = False
    #         elif start_date and isinstance(transaction.get('date'), str):
    #             # Try to parse the date string
    #             try:
    #                 for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
    #                     try:
    #                         date_obj = datetime.strptime(transaction['date'], fmt).date()
    #                         if date_obj < start_date:
    #                             include = False
    #                         break
    #                     except ValueError:
    #                         continue
    #             except Exception as e:
    #                 print(f"Error parsing transaction date for start_date filtering: {e}")
                    
    #         if end_date and isinstance(transaction.get('date'), datetime):
    #             if transaction['date'].date() > end_date:
    #                 include = False
    #         elif end_date and isinstance(transaction.get('date'), str):
    #             # Try to parse the date string
    #             try:
    #                 for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
    #                     try:
    #                         date_obj = datetime.strptime(transaction['date'], fmt).date()
    #                         if date_obj > end_date:
    #                             include = False
    #                         break
    #                     except ValueError:
    #                         continue
    #             except Exception as e:
    #                 print(f"Error parsing transaction date for end_date filtering: {e}")
                    
    #         # Filter by transaction type
    #         if 'transaction_type' in query_params and transaction.get('transaction_type'):
    #             if query_params['transaction_type'].upper() != transaction['transaction_type'].upper():
    #                 include = False
                    
    #         # Filter by payment method
    #         if 'payment_method' in query_params and transaction.get('payment_method'):
    #             if query_params['payment_method'].lower() not in transaction['payment_method'].lower():
    #                 include = False
                    
    #         # Filter by party
    #         if 'party' in query_params and transaction.get('party'):
    #             if query_params['party'].lower() not in transaction['party'].lower():
    #                 include = False
            
    #         if include:
    #             filtered_transactions.append(transaction)
                
    #     return filtered_transactions

import os
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
            'Date', 'Description', 'Category', 'Expected Amount', 'Paid Amount', 'Transaction Type',
            'Status', 'Customer', 'Vendor', 'Payment Method', 'Reference Number'
        ])
        self._ensure_sheet_exists('Customers', [
            'Name', 'Email', 'Phone', 'GST Number', 'Address', 'Created At'
        ])
        self._ensure_sheet_exists('Vendors', [
            'Name', 'Email', 'Phone', 'GST Number', 'Address', 'Created At'
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
        
        # Column headers for customers
        headers = ['name', 'email', 'phone', 'gst_number', 'address', 'created_at']
        
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
        
        # Column headers for vendors
        headers = ['name', 'email', 'phone', 'gst_number', 'address', 'created_at']
        
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
            # Format the data as a row
            row = [
                transaction_data.get('date', ''),
                transaction_data.get('description', ''),
                transaction_data.get('category', ''),
                transaction_data.get('expected_amount', ''),
                transaction_data.get('paid_amount', ''),
                transaction_data.get('transaction_type', ''),
                transaction_data.get('status', ''),
                transaction_data.get('customer', ''),
                transaction_data.get('vendor', ''),
                transaction_data.get('payment_method', ''),
                transaction_data.get('reference_number', '')
            ]
            
            # Append the row to the sheet
            result = self.sheet.values().append(
                spreadsheetId=self.spreadsheet_id,
                range='Transactions!A1',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [row]}
            ).execute()
            
            logger.info(f"Added new transaction: {transaction_data}")
            return True
        except Exception as e:
            logger.error(f"Error adding transaction: {e}")
            return False
    
    def add_customer(self, customer_data: Dict[str, Any]) -> bool:
        """Add a new customer to the Google Sheet"""
        try:
            # Format the data as a row
            row = [
                customer_data.get('name', ''),
                customer_data.get('email', ''),
                customer_data.get('phone', ''),
                customer_data.get('gst_number', ''),
                customer_data.get('address', ''),
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # created_at
            ]
            
            # Append the row to the sheet
            result = self.sheet.values().append(
                spreadsheetId=self.spreadsheet_id,
                range='Customers!A1',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [row]}
            ).execute()
            
            logger.info(f"Added new customer: {customer_data}")
            return True
        except Exception as e:
            logger.error(f"Error adding customer: {e}")
            return False
    
    def add_vendor(self, vendor_data: Dict[str, Any]) -> bool:
        """Add a new vendor to the Google Sheet"""
        try:
            # Format the data as a row
            row = [
                vendor_data.get('name', ''),
                vendor_data.get('email', ''),
                vendor_data.get('phone', ''),
                vendor_data.get('gst_number', ''),
                vendor_data.get('address', ''),
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # created_at
            ]
            
            # Append the row to the sheet
            result = self.sheet.values().append(
                spreadsheetId=self.spreadsheet_id,
                range='Vendors!A1',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [row]}
            ).execute()
            
            logger.info(f"Added new vendor: {vendor_data}")
            return True
        except Exception as e:
            logger.error(f"Error adding vendor: {e}")
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
        """Search customers based on query parameters"""
        customers = self.get_all_customers()
        
        # Filter customers based on query parameters
        filtered_customers = []
        for customer in customers:
            match = True
            
            for key, value in query_params.items():
                if key in customer and str(customer[key]).lower() != str(value).lower():
                    match = False
                    break
            
            if match:
                filtered_customers.append(customer)
        
        return filtered_customers
    
    def search_vendors(self, query_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search vendors based on query parameters"""
        vendors = self.get_all_vendors()
        
        # Filter vendors based on query parameters
        filtered_vendors = []
        for vendor in vendors:
            match = True
            
            for key, value in query_params.items():
                if key in vendor and str(vendor[key]).lower() != str(value).lower():
                    match = False
                    break
            
            if match:
                filtered_vendors.append(vendor)
        
        return filtered_vendors