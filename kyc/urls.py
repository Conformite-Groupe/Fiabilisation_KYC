from django.urls import path, include

from accounts.views import login_kyc, logout_user
from . import views
from .views import accueil, profile, ChangePasswordView, user_statistics_view
from django.contrib.auth import views as auth_views

from kyc.views import register


app_name = "kyc"
urlpatterns = [
    path('login_kyc/', login_kyc, name="login_kyc"),
    path('logout',logout_user, name='logout'),
    path('modify/', profile, name="modify"),
    path('password_resete/done/', auth_views.PasswordResetDoneView.as_view(template_name='password_reset_done.html'),
         name="password_resete_done"),
    path('resete/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name="password_reset_confirm.html"), name='password_resete_confirm'),
    path('resete/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='password_reset_complete.html'), name='password_resete_complete'),
    path("password_reset", views.password_reset_request, name="password_reset"),
    path('modify-pw/', ChangePasswordView.as_view(), name='modify-pw'),
    path("user_statistics/", user_statistics_view, name="user_statistics"),
    path('quality_control/', views.quality_control_view, name='quality_control'),
    path('quality_control/delete/<int:pk>/', views.delete_quality_rule, name='delete_quality_rule'),
    path('quality_control/edit/<int:pk>/', views.edit_quality_rule, name='edit_quality_rule'),
    path('quality_control/audits/', views.quality_control_audits, name='quality_control_audits'),
    path('quality_control/audits/excel/', views.export_audits_excel, name='export_audits_excel'),
    path('quality_control/audits/pdf/', views.export_audits_pdf, name='export_audits_pdf'),
    path('quality_control/export_rules_pdf/', views.export_rules_pdf, name='export_rules_pdf'),
    path('quality_control/export_failures/<int:rule_id>/', views.export_rule_failures, name='export_rule_failures'),
    path('document-extraction/', views.document_extraction, name='document_extraction'),
    path('document-extraction/start-match/', views.start_document_extraction_match_job, name='start_document_extraction_match_job'),
    path('document-extraction/match-job/<int:job_id>/status/', views.document_extraction_match_job_status, name='document_extraction_match_job_status'),
    path('document-extraction/export-matches/', views.export_document_extraction_matches, name='export_document_extraction_matches'),
]
