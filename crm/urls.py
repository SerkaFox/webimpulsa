from django.urls import path
from . import views
from . import views_dossier
from . import views_portal
from .views_portal import portal_send_message
from . import views_proposal

urlpatterns = [
    # ── Public API ─────────────────────────────────────────────────────────
    path('wi/crm/leads/',              views.create_lead,       name='crm_create_lead'),

    # ── Internal admin panel ───────────────────────────────────────────────
    path('wi/crm/',                    views.leads_list,        name='crm_leads_list'),
    path('wi/crm/<int:pk>/',           views.lead_detail,       name='crm_lead_detail'),

    # ── CRM AJAX endpoints ─────────────────────────────────────────────────
    path('wi/crm/<int:pk>/access/',    views.lead_generate_access, name='crm_generate_access'),
    path('wi/crm/<int:pk>/comm/',      views.lead_log_comm,        name='crm_log_comm'),
    path('wi/crm/<int:pk>/materials/', views.lead_materials,       name='crm_materials'),

    # ── Activity endpoints ─────────────────────────────────────────────────
    path('wi/crm/<int:pk>/milestone/',           views.lead_add_milestone,    name='crm_add_milestone'),
    path('wi/crm/<int:pk>/milestone/<int:mid>/', views.lead_update_milestone, name='crm_update_milestone'),
    path('wi/crm/<int:pk>/worklog/',             views.lead_add_worklog,      name='crm_add_worklog'),
    path('wi/crm/<int:pk>/payment/',             views.lead_add_payment,      name='crm_add_payment'),
    path('wi/crm/<int:pk>/evidence/',            views.lead_add_evidence,     name='crm_add_evidence'),

    # ── Protected file serving ─────────────────────────────────────────────
    path('wi/crm/payment/<int:pk>/invoice/', views.serve_invoice,  name='crm_serve_invoice'),
    path('wi/crm/evidence/<int:pk>/file/',   views.serve_evidence, name='crm_serve_evidence'),

    # ── Dossier and exports ────────────────────────────────────────────────
    path('wi/crm/<int:pk>/dossier/',         views_dossier.dossier_zip,      name='crm_dossier_zip'),
    path('wi/crm/<int:pk>/dossier/preview/', views_dossier.dossier_preview,  name='crm_dossier_preview'),
    path('wi/crm/export/',                   views_dossier.export_dashboard, name='crm_export_dashboard'),

    # ── Proposal ───────────────────────────────────────────────────────────
    path('wi/crm/<int:pk>/proposal/',        views_proposal.proposal_for_lead, name='crm_proposal_for_lead'),
    path('wi/crm/proposal/<int:pid>/',       views_proposal.proposal_editor,   name='crm_proposal_editor'),
    path('wi/crm/proposal/<int:pid>/save/',  views_proposal.proposal_save,     name='crm_proposal_save'),
    path('wi/crm/proposal/<int:pid>/send/',  views_proposal.proposal_send,     name='crm_proposal_send'),
    path('wi/crm/proposal/<int:pid>/print/', views_proposal.proposal_print,    name='crm_proposal_print'),

    # ── Client portal (public, token-authenticated) ────────────────────────
    path('p/<str:token>/',                    views_portal.portal,                 name='crm_portal'),
    path('p/<str:token>/upload/',             views_portal.portal_upload,          name='crm_portal_upload'),
    path('p/<str:token>/file/<int:pk>/',      views_portal.portal_file,            name='crm_portal_file'),
    path('p/<str:token>/proposal/accept/',    views_portal.portal_accept_proposal, name='crm_portal_accept_proposal'),
    path('p/<str:token>/message/',            portal_send_message,                 name='crm_portal_message'),
]
