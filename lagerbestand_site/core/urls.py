from django.urls import path

from . import views

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('profiles/', views.ProfileSelectView.as_view(), name='profile_select'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('profile/', views.ProfileView.as_view(), name='profile'),

    path('articles/', views.ArticleListView.as_view(), name='article_list'),
    path('article/new/', views.ArticleCreateView.as_view(), name='article_create'),
    path('article/<int:pk>/edit/', views.ArticleUpdateView.as_view(), name='article_update'),
    path('article/<int:pk>/delete/', views.ArticleDeleteView.as_view(), name='article_delete'),
    path('article/<int:pk>/', views.ArticleHistoryView.as_view(), name='article_history'),
    path('article/<int:article_id>/movement/', views.MovementCreateView.as_view(), name='movement_create'),

    path('import/', views.CSVImportView.as_view(), name='import_csv'),
    path('export/articles/', views.export_articles, name='export_articles'),

    path('orders/', views.OrderListView.as_view(), name='order_list'),
    path('orders/analysis/', views.OrderAnalysisView.as_view(), name='order_analysis'),
    path('orders/new/', views.OrderEditView.as_view(), name='order_create'),
    path('orders/<int:pk>/', views.OrderDetailView.as_view(), name='order_detail'),
    path('orders/<int:pk>/edit/', views.OrderEditView.as_view(), name='order_edit'),
    path('orders/<int:pk>/delete/', views.OrderDeleteView.as_view(), name='order_delete'),

    path('settings/categories/', views.CategorySettingsView.as_view(), name='settings_categories'),
    path('settings/endings/', views.EndingSettingsView.as_view(), name='settings_endings'),
    path('settings/endings/<int:pk>/', views.EndingSettingsView.as_view(), name='settings_endings_edit'),
    path('settings/api-imports/', views.ApiImportView.as_view(), name='settings_api_imports'),
    path('settings/api-imports/easybill-live/', views.EasybillLiveImportView.as_view(), name='settings_api_imports_easybill_live'),
    path('settings/backup/', views.BackupImportView.as_view(), name='settings_backup'),
    path('settings/backup/export/', views.BackupExportView.as_view(), name='settings_backup_export'),

    path('messages/', views.MessageListView.as_view(), name='messages'),
    path('messages/new/', views.MessageCreateView.as_view(), name='message_create'),
    path('logs/', views.ActivityLogListView.as_view(), name='activity_logs'),

    path('page/<slug:slug>/', views.StaticTemplateView.as_view(), name='static_page'),
]
