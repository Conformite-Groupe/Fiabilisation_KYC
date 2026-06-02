import kyc as kyc
from django.conf.urls.static import static
from django.contrib import admin, auth
from kyc import views
from kyc.views import accueil, change_user_password, edit_user, perso, profile, ChangePasswordView, profil, perso_stock, \
    agent_detail, agent, agent_stock, notes, historique, register, reset_user_password, reset_user_password_b, \
    user_list, user_statistics_view, non_anom, statistiques, non_rens, ppe, devise, non_resid, scoring, \
    non_anom_ppe, sans_classe, devise_pm, non_resid_pm, taux_evolution_view, \
    taux_evolution_view_stock, sans_classe_s, export_devise_pp, export_non_resid_pm, export_non_resid_pp, \
    export_devise_pm
from Fiabilisation_kyc import settings
from django.urls import path, include
from accounts.views import login_kyc, logout_user, force_password_change
from django.contrib.auth import views as auth_views


from django.views.generic import TemplateView


urlpatterns = [

                  path('', accueil, name='accueil'),
                  path('register/', register, name="register"),
                  path('accueil/', accueil, name='accueil'),
                  path('perso/', perso, name='perso'),
                  path("notation/", notes, name="notation"),
                  path("historique/", historique, name="historique"),
                  path('perso_stock/', perso_stock, name='perso_stock'),
                  path('agent/', agent, name='agent'),
                  path('non_anom/', non_anom, name='non_anom'),
                  path('non_rens/', non_rens, name='non_rens'),
                  path('statistiques/', statistiques, name='statistiques'),

                  path('ppe/', ppe, name='ppe'),
                  path('anom_ppe/', non_anom_ppe, name='anom_ppe'),
                  path('devise/', devise, name='devise'),
                  path('export_devise_pp/', export_devise_pp, name='export_devise_pp'),

                  path('export_devise_pm/', export_devise_pm, name='export_devise_pm'),
                  path('devise_pm/', devise_pm, name='devise_pm'),
                  path('non_resid/', non_resid, name='non_resid'),

                  path('export_non_resid_pp/', export_non_resid_pp, name='export_non_resid_pp'),
                  path('export_non_resid_pm/', export_non_resid_pm, name='export_non_resid_pm'),


                  path('evolution_filiale_stock/', taux_evolution_view_stock, name='evolution_filiale_stock'),
                  path('evolution_filiale/',taux_evolution_view , name='evolution_filiale'),
                  path('non_resid_pm/', non_resid_pm, name='non_resid_pm'),
                  path('scoring/', scoring, name='scoring'),

                  path('sans_class_s/', sans_classe_s, name='sans_classe_s'),
                  path('sans_classe/', sans_classe, name='sans_classe'),
                  path('non_rens/', views.non_rens, name='non_rens'),
                  path('non_rens_pm/', views.non_rens_pm, name='non_rens_pm'),
                  path('daterev_ppe/', views.daterev_ppe, name='daterev_ppe'),
                  path('export_csv_anom_ppe/', views.export_csv_anom_ppe, name='export_csv_anom_ppe'),
                  path('export_ppe/', views.export_ppe, name='export_ppe'),
                  path('export_csv_scoring_ppe/', views.export_csv_scoring_ppe, name='export_csv_scoring_ppe'),
                  path('export_csv_pm/', views.export_csv_pm, name='export_csv_pm'),

                  path('export_csv_scoring_clients/', views.export_csv_scoring_clients, name='export_csv_scoring_clients'),
                  path('clients_scorer/', views.clients_scorer, name='clients_scorer'),
                  path('evolution_taux/', views.evolution_taux, name='evolution_taux'),
                  path('export_sans_classe/', views.export_sans_classe, name='export_sans_classe'),

                  path('export_sans_classe_s/', views.export_sans_classe_s, name='export_sans_classe_s'),
                  path('export_scoring/', views.export_csv_scoring, name='export_scoring'),

                  path('export_csv_pp/', views.export_csv_pp, name='export_csv_pp'),
                  path('export_csv_anom/', views.export_csv_anom, name='export_csv_anom'),
                  path('agent_stock/', agent_stock, name='agent_stock'),
                  path('export_agents_excel/', views.export_agents_excel, name='export_agents_excel'),
                  path('export_agents_excel_s/', views.export_agents_excel_s, name='export_agents_excel_s'),

                  path('modify', profile, name="modify"),
                  path('user_list/', user_list, name='user_list'),
                  path('users/reset-password/<int:user_id>/', reset_user_password, name='reset_user_password'),

                  path('users/edit/<int:user_id>/', edit_user, name='edit_user'),
                  path('users/change-password/<int:user_id>/', change_user_password, name='change_user_password'),
                  path('login_kyc/', login_kyc, name="login_kyc"),
                  path('change-password/', force_password_change, name='force_password_change'),
                  path('import/', views.import_page, name='import_page'),
                  path('import/log/<str:filename>/', views.import_log_download, name='import_log_download'),
                  path('document-extraction/', views.document_extraction, name='document_extraction'),
                  path('document-extraction/start-match/', views.start_document_extraction_match_job, name='start_document_extraction_match_job'),
                  path('document-extraction/match-job/<int:job_id>/status/', views.document_extraction_match_job_status, name='document_extraction_match_job_status'),
                  path('document-extraction/export-matches/', views.export_document_extraction_matches, name='export_document_extraction_matches'),

                  path('logout/', logout_user, name="logout"),
    path('admin/', admin.site.urls),
    path('modify-pw/', ChangePasswordView.as_view(), name='modify-pw'),
        #path('modify-pw/<int:user_id>/', reset_user_password_b, name='modify-pw'),

    path("perso/profil/", profil, name="profil"),
      path("user_statistics/", user_statistics_view, name="user_statistics"),
    path('resete/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
                      template_name="password_reset_confirm.html"), name='password_resete_confirm'),
    path('resete/done/',  auth_views.PasswordResetCompleteView.as_view(
                      template_name='password_reset_complete.html'), name='password_resete_complete'),
    path("password_resete", views.password_reset_request, name="password_resete"),

path('bulk-upload/', views.bulk_user_upload, name='bulk_user_upload'),
path('download-template/', views.download_excel_template, name='download_csv_template'),
    path('trade/', include('kyc.urls')),

    path('accounts/', include('django.contrib.auth.urls'))
         ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
