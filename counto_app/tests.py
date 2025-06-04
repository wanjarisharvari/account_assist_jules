import json
from django.test import TestCase
from django.contrib.auth.models import User
from .models import Conversation, PendingTransaction, Transaction # Customer, Vendor not directly used in these tests
from .services.gemini_services import GeminiService
from decimal import Decimal
from django.utils import timezone

class TestGeminiServiceCategorization(TestCase):
    """
    Tests for category extraction and placeholder handling in GeminiService._extract_transaction_data.
    """
    @classmethod
    def setUpTestData(cls):
        cls.gemini_service = GeminiService()

    def _create_input_json_string(self, category_value="DEFAULT_CAT_VAL", description="Test transaction", amount=100.0, transaction_type="Expense", party_name="Test Party", date_val="2023-10-26"):
        """
        Helper to create a JSON string input for _extract_transaction_data.
        'party_name' is used here as this is the expected input key in the JSON.
        """
        payload = {
            "date": date_val, # _extract_transaction_data expects a string date
            "description": description,
            "amount": amount,
            "transaction_type": transaction_type,
            "payment_method": "Card",
            "reference_number": "123",
            "party_name": party_name # Input JSON from Gemini contains 'party_name'
        }
        if category_value != "DEFAULT_CAT_VAL": # Marker to control category key presence
            payload["category"] = category_value
        # If category_value is "DEFAULT_CAT_VAL", 'category' key is omitted from payload.
        return json.dumps(payload)

    def test_placeholder_categories_are_set_to_none(self):
        """Test that each placeholder category (exact match) is converted to None."""
        for placeholder in GeminiService.PLACEHOLDER_CATEGORIES:
            with self.subTest(placeholder=placeholder):
                json_string = self._create_input_json_string(category_value=placeholder)
                extracted_data = self.gemini_service._extract_transaction_data(json_string)
                self.assertIsNone(extracted_data.get('category'),
                                  f"Placeholder '{placeholder}' should result in None category.")

    def test_case_insensitive_placeholder_categories(self):
        """Test case-insensitivity for common placeholder categories."""
        # These are common patterns; the important part is that they exist in PLACEHOLDER_CATEGORIES (case-insensitively)
        common_placeholders_for_case_test = ["Unknown", "Other", "N/A", "[Please specify category]", "Miscellaneous", ""]

        for base_placeholder_str in common_placeholders_for_case_test:
            # Find if any version of this placeholder exists in the official list to make the test meaningful
            actual_defined_placeholder = next((p for p in GeminiService.PLACEHOLDER_CATEGORIES if p.lower() == base_placeholder_str.lower()), None)

            if actual_defined_placeholder is not None: # Only test if such a placeholder (case-insensitive) is defined
                variations_to_test = [base_placeholder_str.lower(), base_placeholder_str.upper(), base_placeholder_str.title()]
                if base_placeholder_str not in variations_to_test: # ensure original form (if different) is tested
                    variations_to_test.append(base_placeholder_str)

                for variation in variations_to_test:
                    # Test only if this variation itself is considered a placeholder by the service's logic
                    # The service logic converts both input and placeholder list to lowercase for comparison.
                    is_variation_a_placeholder = variation.lower().strip() in [p.lower() for p in GeminiService.PLACEHOLDER_CATEGORIES]
                    if not is_variation_a_placeholder:
                        continue

                    with self.subTest(variation=variation, base=base_placeholder_str):
                        json_string = self._create_input_json_string(category_value=variation)
                        extracted_data = self.gemini_service._extract_transaction_data(json_string)
                        self.assertIsNone(extracted_data.get('category'),
                                          f"Case variation '{variation}' for base '{base_placeholder_str}' should result in None.")
            else:
                # Optional: log if a common placeholder used for testing isn't in the service list
                # print(f"Info: Common test placeholder '{base_placeholder_str}' not found in GeminiService.PLACEHOLDER_CATEGORIES for case-insensitivity test.")
                pass


    def test_valid_category_is_preserved(self):
        """Test that a valid category string remains unchanged."""
        valid_category = "Groceries"
        json_string = self._create_input_json_string(category_value=valid_category)
        extracted_data = self.gemini_service._extract_transaction_data(json_string)
        self.assertEqual(extracted_data.get('category'), valid_category)

    def test_category_key_missing(self):
        """Test when the 'category' key is entirely missing from the JSON."""
        json_string = self._create_input_json_string() # "DEFAULT_CAT_VAL" ensures key is missing
        extracted_data = self.gemini_service._extract_transaction_data(json_string)
        self.assertIsNone(extracted_data.get('category'))

    def test_category_value_is_json_null(self):
        """Test when the 'category' value is explicitly null in JSON."""
        json_string = self._create_input_json_string(category_value=None) # json.dumps converts None to null
        extracted_data = self.gemini_service._extract_transaction_data(json_string)
        self.assertIsNone(extracted_data.get('category'))

    def test_empty_string_category_becomes_none(self):
        """An empty string for category is a placeholder, should become None."""
        json_string = self._create_input_json_string(category_value="")
        extracted_data = self.gemini_service._extract_transaction_data(json_string)
        self.assertIsNone(extracted_data.get('category'))

    def test_category_field_not_string_type_becomes_none(self):
        """Test that non-string category types (int, bool, list, dict) become None."""
        non_string_types = [123, True, ["Not", "Allowed"], {"cat": "Invalid"}]
        for non_string_type in non_string_types:
            with self.subTest(type_val=str(type(non_string_type))):
                json_string = self._create_input_json_string(category_value=non_string_type)
                extracted_data = self.gemini_service._extract_transaction_data(json_string)
                self.assertIsNone(extracted_data.get('category'), f"{type(non_string_type)} category should be converted to None.")


class TestTransactionCategorySaving(TestCase):
    """
    Tests the model saving flow for transactions with placeholder and valid categories.
    """
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='testuser_catsave', password='password')
        cls.conversation = Conversation.objects.create(user=cls.user)

    def test_placeholder_category_flow_results_in_none_in_transaction(self):
        """
        Simulates: GeminiService processes placeholder -> category becomes None in extracted_data.
        PendingTransaction is created with category=None.
        Transaction is then created from PendingTransaction, also with category=None.
        """
        # 1. Simulate output of GeminiService._extract_transaction_data for a placeholder
        # The 'category' is already None at this stage.
        # 'vendor' field is present because input JSON had 'party_name' and 'transaction_type' was 'Expense'.
        extracted_data_after_gemini = {
            'date': timezone.now().strftime('%Y-%m-%d'), # String date, as _extract_transaction_data doesn't convert
            'description': 'Transaction with placeholder category',
            'category': None,  # Key aspect: category is already None
            'amount': Decimal('123.45'),
            'transaction_type': 'EXPENSE',
            'payment_method': 'Cash',
            'reference_number': 'ref123',
            'vendor': 'Placeholder Vendor Name' # Output of _extract_transaction_data
        }

        # 2. Create PendingTransaction (simulating MessageView._handle_transaction_data)
        # Note: MessageView uses extracted_data.get('date') which is a string, then parses it.
        # For this test, we'll use a date object for PendingTransaction.date as per model.
        pending_tx_date = timezone.now().date()
        pending_tx = PendingTransaction.objects.create(
            user=self.user,
            conversation=self.conversation,
            date=pending_tx_date,
            description=extracted_data_after_gemini['description'],
            category=extracted_data_after_gemini['category'], # Should be None
            amount=extracted_data_after_gemini['amount'],
            transaction_type=extracted_data_after_gemini['transaction_type'],
            payment_method=extracted_data_after_gemini['payment_method'],
            reference_number=extracted_data_after_gemini['reference_number'],
            party=extracted_data_after_gemini['vendor'] # PendingTransaction.party gets the vendor/customer name string
        )
        retrieved_pending_tx = PendingTransaction.objects.get(id=pending_tx.id)
        self.assertIsNone(retrieved_pending_tx.category, "PendingTransaction category should be None.")

        # 3. Simulate TransactionConfirmView.post creating Transaction
        final_tx = Transaction.objects.create(
            user=self.user,
            date=retrieved_pending_tx.date,
            description=retrieved_pending_tx.description,
            category=retrieved_pending_tx.category, # This will be None
            transaction_type=retrieved_pending_tx.transaction_type,
            amount=retrieved_pending_tx.amount,
            payment_method=retrieved_pending_tx.payment_method,
            reference_number=retrieved_pending_tx.reference_number
            # vendor/customer FK linking would happen here in full view; omitted for category focus
        )
        retrieved_final_tx = Transaction.objects.get(id=final_tx.id)
        self.assertIsNone(retrieved_final_tx.category, "Final Transaction category should be None.")

    def test_valid_category_flow_is_preserved_in_transaction(self):
        """
        Simulates: GeminiService extracts valid category -> category preserved.
        PendingTransaction saves it. Transaction saves it.
        """
        valid_category = "Utilities"
        extracted_data_after_gemini = {
            'date': timezone.now().strftime('%Y-%m-%d'),
            'description': 'Transaction with valid category',
            'category': valid_category,
            'amount': Decimal('75.00'),
            'transaction_type': 'EXPENSE',
            'payment_method': 'Online',
            'reference_number': 'ref456',
            'vendor': 'Utility Co Name'
        }

        pending_tx_date = timezone.now().date()
        pending_tx = PendingTransaction.objects.create(
            user=self.user,
            conversation=self.conversation,
            date=pending_tx_date,
            description=extracted_data_after_gemini['description'],
            category=extracted_data_after_gemini['category'], # Should be "Utilities"
            amount=extracted_data_after_gemini['amount'],
            transaction_type=extracted_data_after_gemini['transaction_type'],
            payment_method=extracted_data_after_gemini['payment_method'],
            reference_number=extracted_data_after_gemini['reference_number'],
            party=extracted_data_after_gemini['vendor']
        )
        retrieved_pending_tx = PendingTransaction.objects.get(id=pending_tx.id)
        self.assertEqual(retrieved_pending_tx.category, valid_category)

        final_tx = Transaction.objects.create(
            user=self.user,
            date=retrieved_pending_tx.date,
            description=retrieved_pending_tx.description,
            category=retrieved_pending_tx.category, # Should be "Utilities"
            transaction_type=retrieved_pending_tx.transaction_type,
            amount=retrieved_pending_tx.amount,
            payment_method=retrieved_pending_tx.payment_method,
            reference_number=retrieved_pending_tx.reference_number
        )
        retrieved_final_tx = Transaction.objects.get(id=final_tx.id)
        self.assertEqual(retrieved_final_tx.category, valid_category)
