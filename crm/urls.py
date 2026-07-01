from django.urls import path
from . import views
from . import views_portal

urlpatterns = [
    # ── Public API ─────────────────────────────────────────────────────────
    path('wi/crm/leads/',              views.create_lead,       name='crm_create_lead'),

    # ── Internal admin panel ───────────────────────────────────────────────
    path('wi/crm/',                    views.leads_list,        name='crm_leads_list'),
    path('wi/crm/<int:pk>/',           views.lead_detail,       name='crm_lead_detail'),

    # ── CRM action endpoints (AJAX) ────────────────────────────────────────
    path('wi/crm/<int:pk>/access/',    views.lead_generate_access, name='crm_generate_access'),
    path('wi/crm/<int:pk>/comm/',      views.lead_log_comm,        name='crm_log_comm'),
    path('wi/crm/<int:pk>/materials/', views.lead_materials,       name='crm_materials'),

    # ── Client portal (public, token-authenticated) ────────────────────────
    path('p/<str:token>/',             views_portal.portal,         name='crm_portal'),
    path('p/<str:token>/upload/',      views_portal.portal_upload,  name='crm_portal_upload'),
    path('p/<str:token>/file/<int:pk>/', views_portal.portal_file,  name='crm_portal_file'),
]
