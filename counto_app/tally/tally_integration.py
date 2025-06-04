import requests
import json
from datetime import datetime
from decimal import Decimal
from django.conf import settings
from counto_app.models import Customer, Vendor, Transaction, Invoice, Bill


class TallyIntegrationService:
    """Service class to handle Tally API integration"""
    
    def __init__(self):
        self.base_url = "https://api.excel2tally.in/api/User"
        self.auth_key = getattr(settings, 'TALLY_AUTH_KEY', "test_710457394afd4230ad2679336b2b5c64")
        self.company_name = getattr(settings, 'TALLY_COMPANY_NAME', "Counto")
        self.version = getattr(settings, 'TALLY_VERSION', "3")
        
    def _get_headers(self, template_key):
        """Get common headers for Tally API requests"""
        return {
            'X-Auth-Key': self.auth_key,
            'Template-Key': str(template_key),
            'CompanyName': self.company_name,
            'version': self.version,
            'AddAutoMaster': '1',
            'Automasterids': '1,2'
        }
    
    def _make_request(self, endpoint, template_key, data):
        """Make API request to Tally"""
        url = f"{self.base_url}/{endpoint}"
        headers = self._get_headers(template_key)
        
        try:
            response = requests.post(
                url,
                headers=headers,
                json=data
            )
            response.raise_for_status()
            return {'success': True, 'data': response.json()}
        except requests.exceptions.RequestException as e:
            return {'success': False, 'error': str(e)}
    
    def sync_customer_to_ledger(self, customer):
        """Sync customer to Tally as a ledger master"""
        # Convert to Decimal for consistent numeric operations
        total_receivable = Decimal(str(customer.total_receivable))
        total_received = Decimal(str(customer.total_received))
        opening_balance = total_receivable - total_received
        opening_absolute = abs(opening_balance)
        
        data = {
            "body": [{
                "Ledger Name": customer.name,
                "Group Name": "Sundry Debtors",
                "Credit Period": 30,
                "Address Line 1": customer.address[:50] if customer.address else "",
                "Address Line 2": "",
                "Address Line 3": "",
                "Address Line 4": "",
                "Country": "India",
                "State": "Maharashtra",  # You might want to make this dynamic
                "Pincode": "",
                "Contact Person": customer.name,
                "Phone No": customer.phone or "",
                "Mobile No": customer.phone or "",
                "Email": customer.email or "",
                "GSTIN": customer.gst_number or "",
                "GST Reg Type": "Regular" if customer.gst_number else "",
                "Opening Balance": float(opening_absolute),  # Convert to float only at the end
                "Dr / Cr": "Dr" if opening_balance > 0 else "Cr",
            }]
        }
        
        return self._make_request('LedgerMaster', 16, data)
    
    def sync_vendor_to_ledger(self, vendor):
        """Sync vendor to Tally as a ledger master"""
        # Convert to Decimal for consistent numeric operations
        total_payable = Decimal(str(vendor.total_payable))
        total_paid = Decimal(str(vendor.total_paid))
        opening_balance = total_payable - total_paid
        opening_absolute = abs(opening_balance)
        
        data = {
            "body": [{
                "Ledger Name": vendor.name,
                "Group Name": "Sundry Creditors",
                "Credit Period": 30,
                "Address Line 1": vendor.address[:50] if vendor.address else "",
                "Address Line 2": "",
                "Address Line 3": "",
                "Address Line 4": "",
                "Country": "India",
                "State": "Maharashtra",  # You might want to make this dynamic
                "Pincode": "",
                "Contact Person": vendor.name,
                "Phone No": vendor.phone or "",
                "Mobile No": vendor.phone or "",
                "Email": vendor.email or "",
                "GSTIN": vendor.gst_number or "",
                "GST Reg Type": "Regular" if vendor.gst_number else "",
                "Opening Balance": float(opening_absolute),  # Convert to float only at the end
                "Dr / Cr": "Cr" if opening_balance > 0 else "Dr",
            }]
        }
        
        return self._make_request('LedgerMaster', 16, data)
    
    def sync_sales_transaction(self, transaction, invoice=None):
        """Sync sales transaction to Tally"""
        if transaction.transaction_type != 'INCOME':
            return {'success': False, 'error': 'Transaction is not a sales transaction'}
        
        data = {
            "body": [{
                "Date": transaction.date.strftime("%d-%m-%Y"),
                "Voucher No": f"SALE/{transaction.id}",
                "Voucher Type": "Sales",
                # "IS Invoice": "Yes" if invoice else "No",
                # "Bill Wise Details": invoice.invoice_number if invoice else f"TXN-{transaction.id}",
                "Debit / Party Ledger": transaction.customer.name if transaction.customer else "Cash",
                # "Address 1": transaction.customer.address[:50] if transaction.customer and transaction.customer.address else "",
                # "State": "Maharashtra",  # Make dynamic as needed
                # "Place of Supply": "Maharashtra",
                # "Country": "India",
                # "GSTIN": transaction.customer.gst_number if transaction.customer else "",
                # "GST Registration Type": "Regular" if transaction.customer and transaction.customer.gst_number else "",
                "Credit Ledger 1": "Sales",
                "Credit Ledger 1 Amount": float(Decimal(str(transaction.amount))),  # Ensure proper Decimal conversion
                "Ledger 1 Description": transaction.description,
                "Payment Method": transaction.payment_method or "Cash",
                "Reference Number": transaction.reference_number or "",
                "Narration": transaction.notes or transaction.description,
            }]
        }
        
        return self._make_request('SalesWithoutInventory', 2, data)
    
    def sync_purchase_transaction(self, transaction, bill=None):
        """Sync purchase transaction to Tally"""
        if transaction.transaction_type != 'EXPENSE':
            return {'success': False, 'error': 'Transaction is not a purchase transaction'}
        
        data = {
            "body": [{
                "Date": transaction.date.strftime("%d-%m-%Y"),
                "Voucher No": f"PUR/{transaction.id}",
                "Voucher Type": "Purchase",
                # "IS Invoice": "Yes" if bill else "No",
                # "Supplier Inv No": bill.bill_number if bill else f"TXN-{transaction.id}",
                # "Supplier Inv Date": transaction.date.strftime("%d-%m-%Y"),
                "Credit / Party Ledger": transaction.vendor.name if transaction.vendor else "Cash",
                # "Address 1": transaction.vendor.address[:50] if transaction.vendor and transaction.vendor.address else "",
                # "State": "Maharashtra",  # Make dynamic as needed
                # "Place of Supply": "Maharashtra",
                # "GSTIN": transaction.vendor.gst_number if transaction.vendor else "",
                # "GST Registration Type": "Regular" if transaction.vendor and transaction.vendor.gst_number else "",
                "Debit Ledger 1": "Purchase",
                "Debit Ledger 1 Amount": float(Decimal(str(transaction.amount))),  # Ensure proper Decimal conversion
                "Ledger 1 Description": transaction.description,
                "Payment Method": transaction.payment_method or "Cash",
                "Reference Number": transaction.reference_number or "",
                "Narration": transaction.notes or transaction.description,
            }]
        }
        
        return self._make_request('PurchaseWithoutInventory', 8, data)
    
    def sync_journal_entry(self, transaction):
        """Sync general transaction as journal entry"""
        voucher_type = "Receipt" if transaction.transaction_type == 'INCOME' else "Payment"
        
        # Convert amount to Decimal to ensure consistent numeric operations
        amount = Decimal(str(transaction.amount))
        
        # Create journal entries
        entries = []
        
        if transaction.transaction_type == 'INCOME':
            # Debit Cash/Bank Account
            entries.append({
                "Date": transaction.date.strftime("%d-%m-%Y"),
                "Voucher Number": f"JV-{transaction.id}",
                "Voucher Type": "Journal",
                "Ledger Name": transaction.payment_method or "Cash",
                "Debit / Credit": "Dr",
                "Amount": float(amount),  # Convert to float only at the end
                "Narration": transaction.description
            })
            
            # Credit Income Account
            entries.append({
                "Date": transaction.date.strftime("%d-%m-%Y"),
                "Voucher Number": f"JV-{transaction.id}",
                "Voucher Type": "Journal",
                "Ledger Name": "Other Income",
                "Debit / Credit": "Cr",
                "Amount": float(amount),  # Convert to float only at the end
                "Narration": transaction.description
            })
        else:
            # Credit Cash/Bank Account
            entries.append({
                "Date": transaction.date.strftime("%d-%m-%Y"),
                "Voucher Number": f"JV-{transaction.id}",
                "Voucher Type": "Journal",
                "Ledger Name": transaction.payment_method or "Cash",
                "Debit / Credit": "Cr",
                "Amount": float(amount),  # Convert to float only at the end
                "Narration": transaction.description
            })
            
            # Debit Expense Account
            entries.append({
                "Date": transaction.date.strftime("%d-%m-%Y"),
                "Voucher Number": f"JV-{transaction.id}",
                "Voucher Type": "Journal",
                "Ledger Name": "Other Expenses",
                "Debit / Credit": "Dr",
                "Amount": float(amount),  # Convert to float only at the end
                "Narration": transaction.description
            })
        
        data = {"body": entries}
        return self._make_request('JournalTemplate', 18, data)
    
    def bulk_sync_customers(self, customers):
        """Sync multiple customers to Tally"""
        results = []
        for customer in customers:
            result = self.sync_customer_to_ledger(customer)
            results.append({
                'customer_id': customer.id,
                'customer_name': customer.name,
                'result': result
            })
        return results
    
    def bulk_sync_vendors(self, vendors):
        """Sync multiple vendors to Tally"""
        results = []
        for vendor in vendors:
            result = self.sync_vendor_to_ledger(vendor)
            results.append({
                'vendor_id': vendor.id,
                'vendor_name': vendor.name,
                'result': result
            })
        return results
    
    def bulk_sync_transactions(self, transactions):
        """Sync multiple transactions to Tally"""
        results = []
        for transaction in transactions:
            if transaction.customer and transaction.transaction_type == 'INCOME':
                # Try to find related invoice
                invoice = transaction.customer.invoices.filter(
                    amount_due=transaction.amount,
                    date=transaction.date
                ).first()
                result = self.sync_sales_transaction(transaction, invoice)
            elif transaction.vendor and transaction.transaction_type == 'EXPENSE':
                # Try to find related bill
                bill = transaction.vendor.bills.filter(
                    amount_due=transaction.amount,
                    date=transaction.date
                ).first()
                result = self.sync_purchase_transaction(transaction, bill)
            else:
                result = self.sync_journal_entry(transaction)
            
            results.append({
                'transaction_id': transaction.id,
                'transaction_type': transaction.transaction_type,
                'amount': float(transaction.amount),
                'result': result
            })
        return results


# Utility functions for easy access
def sync_single_customer(customer_id):
    """Helper function to sync a single customer"""
    try:
        customer = Customer.objects.get(id=customer_id)
        service = TallyIntegrationService()
        return service.sync_customer_to_ledger(customer)
    except Customer.DoesNotExist:
        return {'success': False, 'error': 'Customer not found'}

def sync_single_vendor(vendor_id):
    """Helper function to sync a single vendor"""
    try:
        vendor = Vendor.objects.get(id=vendor_id)
        service = TallyIntegrationService()
        return service.sync_vendor_to_ledger(vendor)
    except Vendor.DoesNotExist:
        return {'success': False, 'error': 'Vendor not found'}

def sync_single_transaction(transaction_id):
    """Helper function to sync a single transaction"""
    try:
        transaction = Transaction.objects.get(id=transaction_id)
        service = TallyIntegrationService()
        
        if transaction.customer and transaction.transaction_type == 'INCOME':
            invoice = transaction.customer.invoices.filter(
                amount_due=transaction.amount,
                date=transaction.date
            ).first()
            return service.sync_sales_transaction(transaction, invoice)
        elif transaction.vendor and transaction.transaction_type == 'EXPENSE':
            bill = transaction.vendor.bills.filter(
                amount_due=transaction.amount,
                date=transaction.date
            ).first()
            return service.sync_purchase_transaction(transaction, bill)
        else:
            return service.sync_journal_entry(transaction)
    except Transaction.DoesNotExist:
        return {'success': False, 'error': 'Transaction not found'}