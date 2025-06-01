from django.urls import path
from . import views

urlpatterns = [
    # Template CRUD
    path('', views.TemplateListCreateView.as_view(), name='template_list_create'),
    path('<uuid:pk>/', views.TemplateDetailView.as_view(), name='template_detail'),
    
    # Template actions
    path('<uuid:template_id>/render/', views.render_template, name='render_template'),
    path('<uuid:template_id>/duplicate/', views.duplicate_template, name='duplicate_template'),
    path('<uuid:template_id>/test/', views.test_template, name='test_template'),
    
    # Template versions
    path('<uuid:template_id>/versions/', views.TemplateVersionListView.as_view(), name='template_versions'),
    path('<uuid:template_id>/versions/<int:version_number>/revert/', views.revert_template_version, name='revert_template_version'),
    
    # Template previews
    path('<uuid:template_id>/previews/', views.TemplatePreviewListCreateView.as_view(), name='template_previews'),
    
    # Template tags
    path('tags/', views.TemplateTagListCreateView.as_view(), name='template_tag_list_create'),
    path('tags/<uuid:pk>/', views.TemplateTagDetailView.as_view(), name='template_tag_detail'),
    
    # Statistics
    path('stats/', views.template_stats, name='template_stats'),
]
