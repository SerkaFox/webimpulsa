"""Tareas de hoy para Tania — reemplaza la idea de una lista estática de
pasos por sugerencias que dependen del estado real de sus prospectos: quién
tiene un presupuesto aceptado pero no ha pagado del todo, quién ya es cliente
pero nunca confirmó el chequeo personal, y cuántas empresas nuevas lleva
añadidas hoy frente al objetivo diario. Se muestra en el modal "Instrucciones
de hoy" de map_internal.html, con enlace directo a la ficha de cada empresa.
"""
from django.db.models import Sum
from django.utils import timezone

from .models import BusinessProspect, ChequeoAudit

DAILY_NEW_CLIENTS_GOAL = 3
MAX_ITEMS_PER_TYPE = 5


def build_daily_tasks():
    from crm.models import PaymentRecord, Proposal

    unpaid = []
    accepted_proposals = (
        Proposal.objects.filter(status=Proposal.ST_ACCEPTED).order_by('-issued_at')
    )
    seen_leads = set()
    for proposal in accepted_proposals:
        if proposal.lead_id in seen_leads:
            continue
        seen_leads.add(proposal.lead_id)
        prospect = BusinessProspect.objects.filter(converted_client_id=proposal.lead_id).first()
        if not prospect:
            continue
        paid = PaymentRecord.objects.filter(
            lead_id=proposal.lead_id, status=PaymentRecord.ST_RECEIVED,
        ).aggregate(total=Sum('amount'))['total'] or 0
        owed = proposal.total_with_iva - paid
        if owed > 0:
            unpaid.append({'prospect_id': prospect.pk, 'name': prospect.name, 'owed': owed})
        if len(unpaid) >= MAX_ITEMS_PER_TYPE:
            break

    won_qs = BusinessProspect.objects.filter(sales_status=BusinessProspect.SALES_WON)
    confirmed_ids = set(
        ChequeoAudit.objects.filter(
            mode=ChequeoAudit.MODE_PERSONAL,
            stage=ChequeoAudit.STAGE_CONFIRMADO,
            prospect_id__in=won_qs.values_list('pk', flat=True),
        ).values_list('prospect_id', flat=True)
    )
    no_personal_chequeo = [
        {'prospect_id': p.pk, 'name': p.name}
        for p in won_qs.exclude(pk__in=confirmed_ids)[:MAX_ITEMS_PER_TYPE]
    ]

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    added_today = BusinessProspect.objects.filter(created_at__gte=today_start).count()

    return {
        'unpaid': unpaid,
        'no_personal_chequeo': no_personal_chequeo,
        'new_clients_goal': {
            'goal': DAILY_NEW_CLIENTS_GOAL,
            'added_today': added_today,
            'remaining': max(0, DAILY_NEW_CLIENTS_GOAL - added_today),
        },
    }
