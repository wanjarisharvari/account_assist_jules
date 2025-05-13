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
- OpenAI API key

## Installation

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
   DEBUG=True
   SECRET_KEY='your-secret-key-here'
   OPENAI_API_KEY='your-openai-api-key-here'
   ALLOWED_HOSTS=localhost,127.0.0.1
   ```

5. Apply migrations:
   ```bash
   python manage.py migrate
   ```

6. Create a superuser:
   ```bash
   python manage.py createsuperuser
   ```

## Running the Development Server

```bash
python manage.py runserver
```

Access the admin interface at http://localhost:8000/admin/ and the API at http://localhost:8000/api/

## API Endpoints

- `GET /api/transactions/` - List all transactions
- `POST /api/transactions/` - Create a new transaction
- `GET /api/transactions/summary/` - Get transaction summary
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
