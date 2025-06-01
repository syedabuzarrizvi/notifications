from django.urls import path
from . import views

urlpatterns = [
    # Recipient lists
    path('lists/', views.RecipientListCreateView.as_view(), name='recipient_list_create'),
    path('lists/<uuid:pk>/', views.RecipientListDetailView.as_view(), name='recipient_list_detail'),
    path('lists/<uuid:list_id>/members/', views.RecipientListMembersView.as_view(), name='recipient_list_members'),
    path('lists/<uuid:list_id>/add/', views.add_recipients_to_list, name='add_recipients_to_list'),
    path('lists/<uuid:list_id>/remove/', views.remove_recipients_from_list, name='remove_recipients_from_list'),
    
    # Recipients
    path('', views.RecipientListCreateView.as_view(), name='recipient_list_create'),
    path('<uuid:pk>/', views.RecipientDetailView.as_view(), name='recipient_detail'),
    
    # Bulk operations
    path('import/', views.BulkRecipientImportView.as_view(), name='bulk_recipient_import'),
    path('imports/', views.RecipientImportListView.as_view(), name='recipient_import_list'),
    path('export/', views.export_recipients, name='export_recipients'),
    path('search/', views.search_recipients, name='search_recipients'),
    
    # Tags
    path('tags/', views.RecipientTagListCreateView.as_view(), name='recipient_tag_list_create'),
    path('tags/<uuid:pk>/', views.RecipientTagDetailView.as_view(), name='recipient_tag_detail'),
    
    # Statistics
    path('stats/', views.recipient_stats, name='recipient_stats'),
]
