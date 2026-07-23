from django.urls import path

from . import views_public

urlpatterns = [
    path('chequeo-digital/api/questionnaire/<str:sector>/', views_public.questionnaire_json,
         name='chequeo_questionnaire_json'),
    path('chequeo-digital/api/submit/', views_public.submit_public_audit, name='chequeo_submit_public'),
    path('chequeo-digital/e/<str:token>/', views_public.personal_audit, name='chequeo_personal_audit'),
    path('chequeo-digital/e/<str:token>/api/submit/', views_public.submit_personal_audit,
         name='chequeo_submit_personal'),
]
