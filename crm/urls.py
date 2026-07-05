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

    # ── Admin chat (mirrors client portal chat) ─────────────────────────────
    path('wi/crm/<int:pk>/chat/messages/',      views.lead_chat_messages, name='crm_chat_messages'),
    path('wi/crm/<int:pk>/chat/send/',          views.lead_chat_send,     name='crm_chat_send'),
    path('wi/crm/<int:pk>/chat/<int:mid>/react/',  views.lead_chat_react,  name='crm_chat_react'),
    path('wi/crm/<int:pk>/chat/<int:mid>/delete/', views.lead_chat_delete, name='crm_chat_delete'),

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
    path('p/<str:token>/manifest.json',       views_portal.portal_manifest,        name='crm_portal_manifest'),
    path('p/<str:token>/sw.js',               views_portal.portal_sw,              name='crm_portal_sw'),
    path('p/<str:token>/upload/',             views_portal.portal_upload,          name='crm_portal_upload'),
    path('p/<str:token>/file/<int:pk>/',      views_portal.portal_file,            name='crm_portal_file'),
    path('p/<str:token>/proposal/accept/',    views_portal.portal_accept_proposal, name='crm_portal_accept_proposal'),
    path('p/<str:token>/message/',            portal_send_message,                 name='crm_portal_message'),
    path('p/<str:token>/messages/',           views_portal.portal_messages,        name='crm_portal_messages'),
    path('p/<str:token>/message/<int:pk>/react/',  views_portal.portal_react_message,  name='crm_portal_react_message'),
    path('p/<str:token>/message/<int:pk>/delete/', views_portal.portal_delete_message, name='crm_portal_delete_message'),
    path('p/<str:token>/pay/',                views_portal.portal_pay,               name='crm_portal_pay'),
    path('p/<str:token>/pay/notify/',         views_portal.portal_client_paid,       name='crm_portal_client_paid'),
    path('p/<str:token>/pay/stripe/',         views_portal.portal_pay_stripe_start,   name='crm_portal_pay_stripe_start'),
    path('p/<str:token>/pay/stripe/success/', views_portal.portal_pay_stripe_success, name='crm_portal_pay_stripe_success'),
    path('wi/crm/payment/<int:pk>/confirm/',  views.payment_confirm,                 name='crm_payment_confirm'),
]
