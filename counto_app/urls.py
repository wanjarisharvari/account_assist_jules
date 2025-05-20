from django.urls import path
from .views import (ConversationView, MessageView, home, 
                    login_view, logout_view, register_view, dashboard)

urlpatterns = [
    # Web UI routes
    path('', home, name='home'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('register/', register_view, name='register'),
    path('dashboard/', dashboard, name='dashboard'),
    
    # API routes
    path('conversations/', ConversationView.as_view(), name='conversations'),
    path('conversations/<int:conversation_id>/messages/', MessageView.as_view(), name='conversation_messages'),
    path('messages/', MessageView.as_view(), name='messages'),
    #path('transactions/confirm/', TransactionConfirmView.as_view(), name='confirm_transaction'),
]