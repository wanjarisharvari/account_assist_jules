# Counto - AI-Powered Accounting Copilot

Counto is an AI-powered accounting copilot that helps businesses manage their finances through natural language and document uploads—no forms, no manual data entry, and no accounting knowledge required.

## Features

- **Natural Language Processing**: Speak or type your financial queries and get instant answers
- **Document Processing**: Upload receipts and invoices to automatically extract and categorize transactions
- **Financial Insights**: Get insights into your spending patterns and financial health
- **Multi-Account Support**: Connect and manage multiple bank accounts and credit cards
- **Conversational Interface**: Interact with your financial data using natural language

## Prerequisites

- Python 3.10+
- PostgreSQL (recommended) or SQLite
- Gemini API Key

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/counto.git
   cd counto
   ```

2. Create and activate a virtual environment:
   ```bash
   conda create -n counto python=3.10
   conda activate counto
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the project root and add your environment variables:
   ```
   # General Django Settings
   DJANGO_SECRET_KEY='your_strong_secret_key_here'
   DJANGO_DEBUG=True # Set to False in production
   ALLOWED_HOSTS=localhost,127.0.0.1

   # Database Credentials (PostgreSQL example)
   DB_NAME='Counto'
   DB_USER='postgres'
   DB_PASSWORD='your_db_password'
   DB_HOST='localhost'
   DB_PORT='5432'

   # Google Gemini API
   GEMINI_API_KEY='your_gemini_api_key_here'

   # Google Sheets API
   # Path to your Google Sheets service account JSON credentials file.
   # IMPORTANT: Ensure this credentials file is NOT committed to version control and is listed in .gitignore.
   GOOGLE_SHEETS_CREDENTIALS_FILE='path/to/your/google-sheets-credentials.json'
   GOOGLE_SHEETS_SPREADSHEET_ID='your_spreadsheet_id_here'
   # Optional: Specific ranges if deviating from defaults in settings
   # GOOGLE_SHEETS_TRANSACTIONS_RANGE='Transactions!A2:K'
   # GOOGLE_SHEETS_CUSTOMERS_RANGE='Customers!A2:I'
   # GOOGLE_SHEETS_VENDORS_RANGE='Vendors!A2:I'
   ```

5. Apply migrations:
   ```bash
   python manage.py migrate
   ```

6. Create a superuser:
   ```bash
   python manage.py createsuperuser
   ```

7. (Optional) Create sample data for a user:
   ```bash
   python manage.py create_counto_sample_data your_username
   ```
   Replace `your_username` with the username of the superuser you created or another existing user. This command populates the database with sample customers, vendors, and transactions for testing purposes.

## Running the Development Server

```bash
python manage.py runserver
```

Access the admin interface at http://localhost:8000/admin/ and the API at http://localhost:8000/api/

## API Endpoints

- `GET /api/transactions/` - List all transactions
- `POST /api/transactions/` - Create a new transaction
- `GET /api/transactions/summary/` - Get transaction summary
- `GET /api/analytics-data/` - Retrieves data for the analytics dashboard (supports `?period=` query parameter).
- `GET /api/documents/` - List all documents
- `POST /api/documents/` - Upload a new document
- `POST /api/conversations/` - Send a message to the AI assistant
- `GET /api/accounts/` - List all accounts
- `GET /api/dashboard/` - Get dashboard data
- `POST /api/query/` - Query financial data using natural language

## Frontend

For the frontend, you can use any modern JavaScript framework (React, Vue, Angular) to consume the API. Here's a simple example using fetch:

```javascript
// Example: Fetching transactions
const response = await fetch('http://localhost:8000/api/transactions/', {
  headers: {
    'Authorization': 'Bearer YOUR_ACCESS_TOKEN',
    'Content-Type': 'application/json'
  }
});
const data = await response.json();
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
