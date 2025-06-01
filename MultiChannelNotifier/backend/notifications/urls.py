from django.urls import path
from . import views

urlpatterns = [
    # Immediate notifications
    path('send/', views.send_notification, name='send_notification'),
    path('schedule/', views.schedule_notification, name='schedule_notification'),
    path('<uuid:notification_id>/cancel/', views.cancel_notification, name='cancel_notification'),
    path('<uuid:notification_id>/status/', views.notification_status, name='notification_status'),
    
    # Bulk notifications
    path('bulk/send/', views.send_bulk_notification, name='send_bulk_notification'),
    path('bulk/', views.BulkNotificationListView.as_view(), name='bulk_notification_list'),
    path('bulk/<uuid:bulk_id>/', views.BulkNotificationDetailView.as_view(), name='bulk_notification_detail'),
    path('bulk/<uuid:bulk_id>/cancel/', views.cancel_bulk_notification, name='cancel_bulk_notification'),
    
    # Listing and management
    path('', views.NotificationListView.as_view(), name='notification_list'),
    path('providers/', views.ProviderListView.as_view(), name='provider_list'),
    path('dashboard/stats/', views.dashboard_stats, name='dashboard_stats'),
]
