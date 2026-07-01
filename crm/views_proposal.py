"""Proposal views for WebImpulsa CRM — all protected by HTTP Basic Auth.

URL scheme:
  GET   /wi/crm/<pk>/proposal/          create draft or open latest, redirect to editor
  GET   /wi/crm/proposal/<pid>/         proposal editor with live A4 preview
  POST  /wi/crm/proposal/<pid>/save/    AJAX save draft (JSON)
  POST  /wi/crm/proposal/<pid>/send/    mark as sent + redirect to lead detail
  GET   /wi/crm/proposal/<pid>/print/   standalone printable A4
"""
import json
import logging

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import Lead, Proposal
from .services import (
    accept_proposal, compose_proposal_wa_message, create_proposal_from_lead,
    mark_proposal_sent, proposal_to_template_input, log_communication,
)
from .views import _crm_auth

logger = logging.getLogger(__name__)

_PORTAL_BASE_URL = __import__('os').getenv('WI_BASE_URL', 'https://webimpulsa.es')


def _safe_json(obj) -> str:
    """Serialize to JSON, safe for embedding in <script> tags."""
    return json.dumps(obj, ensure_ascii=True, default=str).replace('</', '<\\/')


def _proposal_context(proposal):
    """Build the shared context passed to proposal templates."""
    lead = proposal.lead
    active_access = lead.access_tokens.filter(is_active=True).order_by('-created_at').first()

    portal_url = ''
    wa_msg = ''
    if active_access and active_access.is_valid:
        portal_url = f'{_PORTAL_BASE_URL}/p/{active_access.token}/'
        wa_msg = compose_proposal_wa_message(proposal, portal_url)

    tmpl_input = proposal_to_template_input(proposal)

    return {
        'proposal':              proposal,
        'lead':                  lead,
        'active_access':         active_access,
        'portal_url':            portal_url,
        'wa_msg':                wa_msg,
        'wa_msg_json':           _safe_json(wa_msg),
        'template_input_json':   _safe_json(tmpl_input),
        'extras_json':           _safe_json(proposal.extras or []),
        'scope_json':            _safe_json(proposal.scope or []),
        'out_of_scope_json':     _safe_json(proposal.out_of_scope or []),
        'phases_json':           _safe_json(proposal.phases or []),
        'conditions_json':       _safe_json(proposal.conditions or []),
        'proposal_number_json':  _safe_json(proposal.number),
    }


# ── GET /wi/crm/<pk>/proposal/ — create draft or open latest ─────────────────

@_crm_auth
def proposal_for_lead(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    proposal = (lead.proposals
                .exclude(status=Proposal.ST_ACCEPTED)
                .order_by('-created_at')
                .first())
    if proposal is None:
        proposal = create_proposal_from_lead(lead)
    return redirect(f'/wi/crm/proposal/{proposal.pk}/')


# ── GET /wi/crm/proposal/<pid>/ — editor ─────────────────────────────────────

@_crm_auth
@require_GET
def proposal_editor(request, pid):
    proposal = get_object_or_404(Proposal, pk=pid)
    ctx = _proposal_context(proposal)
    ctx['statuses'] = Proposal.STATUS_CHOICES
    return render(request, 'crm/proposal_editor.html', ctx)


# ── POST /wi/crm/proposal/<pid>/save/ — AJAX save ────────────────────────────

@_crm_auth
@csrf_exempt
@require_POST
def proposal_save(request, pid):
    proposal = get_object_or_404(Proposal, pk=pid)

    if not proposal.is_editable:
        return JsonResponse({'ok': False, 'error': 'La propuesta no es editable en este estado.'}, status=400)

    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    _STR = {
        'client_name', 'client_email', 'client_phone', 'client_biz_type',
        'client_nif', 'client_address', 'client_city',
        'project_name', 'project_goal', 'biz_description', 'selected_features',
        'timeline', 'start_date', 'payment_method', 'payment_custom',
        'package', 'maintenance_plan', 'notes',
    }
    _INT = {'package_base_price', 'discount_pct', 'maintenance_price', 'valid_days'}

    for field in _STR:
        if field in data:
            setattr(proposal, field, str(data[field] or ''))

    for field in _INT:
        if field in data:
            try:
                setattr(proposal, field, max(0, int(data[field] or 0)))
            except (TypeError, ValueError):
                pass

    if 'rush' in data:
        proposal.rush = bool(data['rush'])

    if 'extras' in data and isinstance(data['extras'], list):
        proposal.extras = [
            {'name': str(e.get('name', '')), 'price': int(e.get('price', 0) or 0)}
            for e in data['extras']
            if e.get('name')
        ]
        proposal.extras_price = sum(e['price'] for e in proposal.extras)

    for lst in ('scope', 'out_of_scope', 'phases', 'conditions'):
        if lst in data and isinstance(data[lst], list):
            setattr(proposal, lst, [str(v) for v in data[lst] if str(v).strip()])

    if 'company_data' in data and isinstance(data['company_data'], dict):
        proposal.company_data = data['company_data']

    proposal.compute_totals()
    proposal.save()

    return JsonResponse({
        'ok':             True,
        'taxable_base':   proposal.taxable_base,
        'iva_amount':     proposal.iva_amount,
        'total_with_iva': proposal.total_with_iva,
        'status':         proposal.status,
    })


# ── POST /wi/crm/proposal/<pid>/send/ — mark as sent ─────────────────────────

@_crm_auth
@csrf_exempt
@require_POST
def proposal_send(request, pid):
    proposal = get_object_or_404(Proposal, pk=pid)
    if proposal.status not in (Proposal.ST_DRAFT, Proposal.ST_SENT):
        return JsonResponse({'ok': False, 'error': 'Estado inválido para enviar.'}, status=400)
    mark_proposal_sent(proposal)
    return JsonResponse({'ok': True, 'redirect': f'/wi/crm/proposal/{pid}/'})


# ── GET /wi/crm/proposal/<pid>/print/ — standalone A4 ────────────────────────

@_crm_auth
@require_GET
def proposal_print(request, pid):
    proposal = get_object_or_404(Proposal, pk=pid)
    ctx = _proposal_context(proposal)
    return render(request, 'crm/proposal_print.html', ctx)
