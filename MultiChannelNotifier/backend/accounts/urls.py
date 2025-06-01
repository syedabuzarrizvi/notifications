from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout, name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('profile/', views.MerchantProfileView.as_view(), name='profile'),
    path('settings/', views.MerchantSettingsView.as_view(), name='settings'),
    path('api-key/', views.api_key, name='api_key'),
    path('api-key/regenerate/', views.regenerate_api_key, name='regenerate_api_key'),
]
