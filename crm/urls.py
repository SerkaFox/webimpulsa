from django.urls import path
from . import views

urlpatterns = [
    # Public API — calculator lead capture
    path('wi/crm/leads/',       views.create_lead,  name='crm_create_lead'),
    # Internal admin panel
    path('wi/crm/',             views.leads_list,   name='crm_leads_list'),
    path('wi/crm/<int:pk>/',    views.lead_detail,  name='crm_lead_detail'),
]
