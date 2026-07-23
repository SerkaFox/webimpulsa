from django.urls import path

from . import views_panel, views_public

urlpatterns = [
    path('chequeo-digital/api/questionnaire/<str:sector>/', views_public.questionnaire_json,
         name='chequeo_questionnaire_json'),
    path('chequeo-digital/api/submit/', views_public.submit_public_audit, name='chequeo_submit_public'),
    path('chequeo-digital/e/<str:token>/', views_public.personal_audit, name='chequeo_personal_audit'),
    path('chequeo-digital/e/<str:token>/api/submit/', views_public.submit_personal_audit,
         name='chequeo_submit_personal'),

    path('panel/prospeccion/', views_panel.dashboard, name='prospeccion_dashboard'),
    path('panel/prospeccion/mapa/', views_panel.internal_map, name='prospeccion_map'),
    path('panel/prospeccion/mapa/api/prospects/', views_panel.prospects_bbox_api, name='prospeccion_bbox_api'),
    path('panel/prospeccion/mapa/api/prospects/add/', views_panel.add_prospect, name='prospeccion_add'),
    path('panel/prospeccion/mapa/api/import-csv/', views_panel.import_csv_view, name='prospeccion_import_csv'),
    path('panel/prospeccion/<int:pk>/', views_panel.prospect_detail, name='prospeccion_detail'),
    path('panel/prospeccion/<int:pk>/update/', views_panel.prospect_update, name='prospeccion_update'),
    path('panel/prospeccion/<int:pk>/convert/', views_panel.convert_to_lead, name='prospeccion_convert'),
    path('panel/prospeccion/<int:pk>/draft-proposal/', views_panel.draft_proposal, name='prospeccion_draft_proposal'),
    path('panel/prospeccion/<int:pk>/pdf/', views_panel.prospect_pdf, name='prospeccion_pdf'),

    path('mapa-digital/', views_public.public_map, name='mapa_digital'),
    path('mapa-digital/api/prospects/', views_public.public_map_api, name='mapa_digital_api'),
]
