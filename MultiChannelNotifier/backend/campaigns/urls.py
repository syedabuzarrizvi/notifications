from django.urls import path
from . import views

urlpatterns = [
    # Campaign CRUD
    path('', views.CampaignListCreateView.as_view(), name='campaign_list_create'),
    path('<uuid:pk>/', views.CampaignDetailView.as_view(), name='campaign_detail'),
    
    # Campaign actions
    path('<uuid:campaign_id>/launch/', views.launch_campaign, name='launch_campaign'),
    path('<uuid:campaign_id>/pause/', views.pause_campaign, name='pause_campaign'),
    path('<uuid:campaign_id>/resume/', views.resume_campaign, name='resume_campaign'),
    path('<uuid:campaign_id>/cancel/', views.cancel_campaign, name='cancel_campaign'),
    path('<uuid:campaign_id>/duplicate/', views.duplicate_campaign, name='duplicate_campaign'),
    
    # Campaign recipients
    path('<uuid:campaign_id>/recipients/', views.CampaignRecipientsView.as_view(), name='campaign_recipients'),
    
    # Audience segments
    path('segments/', views.AudienceSegmentListCreateView.as_view(), name='audience_segment_list_create'),
    path('segments/<uuid:pk>/', views.AudienceSegmentDetailView.as_view(), name='audience_segment_detail'),
    
    # Statistics
    path('stats/', views.campaign_stats, name='campaign_stats'),
]
