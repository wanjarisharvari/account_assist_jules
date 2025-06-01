from django.urls import path
from .views import (
    ConversationView, MessageView, home, login_view, logout_view, 
    register_view, dashboard, analytics, CustomerView, VendorView, TransactionView,
    AnalyticsDataView, upload_document, financial_summary, document_list_view, serve_document_view
)

urlpatterns = [
    # Web UI routes
    path('', home, name='home'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('register/', register_view, name='register'),
    path('dashboard/', dashboard, name='dashboard'),
    path('analytics/', analytics, name='analytics'),
    path('upload-document/', upload_document, name='upload'),
    path('summary/', financial_summary, name='financial_summary'),
    path('documents/', document_list_view, name='document_list'),
    path('documents/<int:document_id>/serve/', serve_document_view, name='serve_document'),
    
    # API routes
    path('conversations/', ConversationView.as_view(), name='conversations'),
    path('conversations/<int:conversation_id>/messages/', MessageView.as_view(), name='conversation_messages'),
    path('messages/', MessageView.as_view(), name='messages'),
    #path('transactions/confirm/', TransactionConfirmView.as_view(), name='confirm_transaction'),
    
    # Customer management
    path('api/customers/', CustomerView.as_view(), name='customer-list'),
    path('api/customers/<int:customer_id>/', CustomerView.as_view(), name='customer-detail'),
    
    # Vendor management
    path('api/vendors/', VendorView.as_view(), name='vendor-list'),
    path('api/vendors/<int:vendor_id>/', VendorView.as_view(), name='vendor-detail'),
    
    # Transaction management
    path('api/transactions/', TransactionView.as_view(), name='transaction-list'),
    path('api/transactions/<int:transaction_id>/', TransactionView.as_view(), name='transaction-detail'),
    
    # Analytics data API
    path('api/analytics-data/', AnalyticsDataView.as_view(), name='analytics-data'),
]