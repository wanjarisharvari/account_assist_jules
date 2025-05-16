"""
URL configuration for counto_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from counto_app import views
# from rest_framework.routers import DefaultRouter
# from rest_framework_simplejwt.views import (
#     TokenObtainPairView,
#     TokenRefreshView,
# )
# from accounting.views import (
#     TransactionViewSet, DocumentViewSet, 
#     ConversationViewSet, AccountViewSet,
#     DashboardView, QueryView
# )

# router = DefaultRouter()
# router.register(r'transactions', TransactionViewSet)
# router.register(r'documents', DocumentViewSet)
# router.register(r'conversations', ConversationViewSet)
# router.register(r'accounts', AccountViewSet)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('counto_app.urls')),
    path('', include('counto_app.urls')),  # Include app URLs at root
    # path('', views.home, name='home'),  # Add home view as the root URL
    # path('api/dashboard/', DashboardView.as_view(), name='dashboard'),
    # path('api/query/', QueryView.as_view(), name='query'),
    # path('api/auth/', include('rest_framework.urls')),
    # path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    # path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
