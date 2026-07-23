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
    path('panel/prospeccion/mapa/api/prospects/add-from-place/', views_panel.add_prospect_from_place,
         name='prospeccion_add_from_place'),
    path('panel/prospeccion/mapa/api/import-csv/', views_panel.import_csv_view, name='prospeccion_import_csv'),
    path('panel/prospeccion/mapa/api/search/', views_panel.places_search, name='prospeccion_places_search'),
    path('panel/prospeccion/mapa/api/parse-maps-link/', views_panel.parse_maps_link, name='prospeccion_parse_maps_link'),
    path('panel/prospeccion/<int:pk>/', views_panel.prospect_detail, name='prospeccion_detail'),
    path('panel/prospeccion/<int:pk>/update/', views_panel.prospect_update, name='prospeccion_update'),
    path('panel/prospeccion/<int:pk>/convert/', views_panel.convert_to_lead, name='prospeccion_convert'),
    path('panel/prospeccion/<int:pk>/draft-proposal/', views_panel.draft_proposal, name='prospeccion_draft_proposal'),
    path('panel/prospeccion/<int:pk>/pdf/', views_panel.prospect_pdf, name='prospeccion_pdf'),

    path('panel/prospeccion/<int:pk>/preliminar/draft/', views_panel.preliminar_save_draft,
         name='prospeccion_preliminar_draft'),
    path('panel/prospeccion/<int:pk>/preliminar/complete/', views_panel.preliminar_complete,
         name='prospeccion_preliminar_complete'),

    path('panel/prospeccion/<int:pk>/contacts/', views_panel.contact_create, name='prospeccion_contact_create'),
    path('panel/prospeccion/<int:pk>/contacts/<int:contact_id>/update/', views_panel.contact_update,
         name='prospeccion_contact_update'),
    path('panel/prospeccion/<int:pk>/contacts/<int:contact_id>/delete/', views_panel.contact_delete,
         name='prospeccion_contact_delete'),
    path('panel/prospeccion/<int:pk>/contacts/<int:contact_id>/consent/', views_panel.contact_consent,
         name='prospeccion_contact_consent'),

    path('panel/prospeccion/<int:pk>/publish-consent/', views_panel.publish_consent_update,
         name='prospeccion_publish_consent'),
    path('panel/prospeccion/<int:pk>/publish-confirm/', views_panel.publish_confirm,
         name='prospeccion_publish_confirm'),

    path('mapa-digital/', views_public.public_map, name='mapa_digital'),
    path('mapa-digital/api/prospects/', views_public.public_map_api, name='mapa_digital_api'),
]
