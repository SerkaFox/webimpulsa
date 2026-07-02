"""Dossier and export views for WebImpulsa CRM — all protected by HTTP Basic Auth.

URL scheme:
  GET  /wi/crm/<pk>/dossier/            single-lead ZIP dossier
  GET  /wi/crm/<pk>/dossier/preview/    same content as HTML preview (no download)
  GET  /wi/crm/export/                  dashboard page (HTML, printable) with date filter
  GET  /wi/crm/export/leads.csv         CSV of all leads in period
"""
import csv
import io
import json
import logging
import mimetypes
import os
import zipfile
from datetime import date

from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import (
    CommunicationLog, EvidenceFile, Lead, PaymentRecord,
    ProjectMaterial, ProjectMilestone, Proposal, WorkLog,
)
from .proposal_content import WI_COMPANY
from .views import _crm_auth

logger = logging.getLogger(__name__)


def _gather_lead_data(lead):
    """Collect all data for a lead into a single dict for dossier generation."""
    proposals  = list(lead.proposals.all())
    comm_log   = list(lead.comm_log.all())
    materials  = list(lead.materials.all())
    milestones = list(lead.milestones.all())
    work_logs  = list(lead.work_logs.all())
    payments   = list(lead.payments.all())
    evidence   = list(lead.evidence.all())

    total_hours  = sum(float(w.hours) for w in work_logs)
    total_income = sum(p.amount for p in payments if p.status == PaymentRecord.ST_RECEIVED)

    # Build unified timeline
    events = []
    events.append({'date': lead.created_at.date(), 'type': 'lead', 'title': 'Lead creado', 'detail': f'Fuente: {lead.get_source_display()} · Paquete: {lead.package or "—"}'})
    for p in proposals:
        events.append({'date': p.created_at.date(), 'type': 'proposal', 'title': f'Propuesta creada: {p.number}', 'detail': f'Estado inicial: borrador · Total: {p.total_with_iva}€'})
        if p.status in (Proposal.ST_SENT, Proposal.ST_VIEWED, Proposal.ST_ACCEPTED):
            events.append({'date': p.updated_at.date(), 'type': 'proposal', 'title': f'Propuesta enviada al cliente: {p.number}', 'detail': ''})
        if p.accepted_at:
            events.append({'date': p.accepted_at.date(), 'type': 'accepted', 'title': f'Propuesta aceptada: {p.number}', 'detail': f'Por: {p.accepted_by_name} (NIF: {p.accepted_nif or "—"})'})
    for c in sorted(comm_log, key=lambda x: x.created_at):
        events.append({'date': c.created_at.date(), 'type': 'comm', 'title': f'Comunicación ({c.get_channel_display()}): {c.content[:80]}', 'detail': c.get_direction_display()})
    for m in milestones:
        if m.due_date:
            events.append({'date': m.due_date, 'type': 'milestone', 'title': f'Hito: {m.title}', 'detail': f'Estado: {m.get_status_display()}'})
        if m.completed_date:
            events.append({'date': m.completed_date, 'type': 'milestone_done', 'title': f'Hito completado: {m.title}', 'detail': ''})
    for w in work_logs:
        events.append({'date': w.date, 'type': 'work', 'title': f'Trabajo realizado: {w.description[:80]}', 'detail': f'{w.hours}h · {w.get_category_display()}'})
    for pay in payments:
        events.append({'date': pay.payment_date, 'type': 'payment', 'title': f'Pago: {pay.concept} ({pay.amount}€)', 'detail': f'{pay.get_method_display()} · Ref: {pay.reference or "—"}'})
    for mat in sorted(materials, key=lambda x: x.created_at):
        events.append({'date': mat.created_at.date(), 'type': 'material', 'title': f'Material subido: {mat.original_filename}', 'detail': f'{mat.size_display} · {mat.get_source_display()}'})
    for ev in evidence:
        events.append({'date': ev.created_at.date(), 'type': 'evidence', 'title': f'Evidencia: {ev.title}', 'detail': ev.get_category_display()})

    events.sort(key=lambda e: e['date'])

    return {
        'lead': lead, 'proposals': proposals, 'comm_log': comm_log,
        'materials': materials, 'milestones': milestones, 'work_logs': work_logs,
        'payments': payments, 'evidence': evidence, 'events': events,
        'total_hours': total_hours, 'total_income': total_income,
        'company': WI_COMPANY, 'generated_at': timezone.now(),
    }


def _build_zip(lead, data):
    """Build in-memory ZIP with all dossier files."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # README
        zf.writestr('README.txt', _readme(lead, data))

        # Main HTML dossier (open in browser → Ctrl+P to save as PDF)
        html = render_to_string('crm/dossier.html', data)
        zf.writestr(f'dossier_{lead.pk:04d}_{date.today().strftime("%Y%m%d")}.html', html)

        # CSV data files
        zf.writestr('timeline.csv',          _csv_timeline(data['events']))
        zf.writestr('datos.json',            _json_lead(lead, data['proposals']))
        zf.writestr('comunicaciones.csv',    _csv_comms(data['comm_log']))
        zf.writestr('materiales.csv',        _csv_materials(data['materials']))
        zf.writestr('trabajo_realizado.csv', _csv_worklog(data['work_logs']))
        zf.writestr('hitos.csv',             _csv_milestones(data['milestones']))
        zf.writestr('pagos_facturacion.csv', _csv_payments(data['payments']))
        zf.writestr('evidencias.csv',        _csv_evidence(data['evidence']))

        # Attached files
        for pay in data['payments']:
            try:
                if pay.invoice_file and pay.invoice_file.name and os.path.exists(pay.invoice_file.path):
                    fname = f'archivos/facturas/{pay.pk:04d}_{os.path.basename(pay.invoice_file.name)}'
                    zf.write(pay.invoice_file.path, fname)
            except Exception:
                pass

        for ev in data['evidence']:
            try:
                if ev.file and ev.file.name and os.path.exists(ev.file.path):
                    fname = f'archivos/evidencias/{ev.pk:04d}_{os.path.basename(ev.file.name)}'
                    zf.write(ev.file.path, fname)
            except Exception:
                pass

        for mat in data['materials']:
            try:
                if mat.file and os.path.exists(mat.file.path):
                    fname = f'archivos/materiales_cliente/{mat.pk:04d}_{mat.original_filename}'
                    zf.write(mat.file.path, fname)
            except Exception:
                pass

    buf.seek(0)
    return buf


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _csv_buf(headers, rows):
    buf = io.StringIO()
    buf.write('﻿')  # UTF-8 BOM for Excel
    w = csv.writer(buf)
    w.writerow(headers)
    w.writerows(rows)
    return buf.getvalue()

def _csv_timeline(events):
    return _csv_buf(
        ['Fecha', 'Tipo', 'Evento', 'Detalle'],
        [[str(e['date']), e['type'], e['title'], e['detail']] for e in events]
    )

def _json_lead(lead, proposals):
    data = {
        'lead': {
            'id': lead.pk, 'name': lead.name, 'email': lead.email,
            'phone': lead.phone, 'biz_type': lead.biz_type,
            'package': lead.package, 'estimated_price': lead.estimated_price,
            'source': lead.source, 'status': lead.status,
            'created_at': str(lead.created_at.date()),
        },
        'proposals': [
            {
                'number': p.number, 'status': p.status,
                'total_with_iva': p.total_with_iva,
                'issued_at': str(p.issued_at),
                'accepted_at': str(p.accepted_at.date()) if p.accepted_at else None,
                'accepted_by': p.accepted_by_name, 'accepted_nif': p.accepted_nif,
            } for p in proposals
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)

def _csv_comms(comm_log):
    return _csv_buf(
        ['Fecha', 'Dirección', 'Canal', 'Contenido', 'Estado'],
        [[str(c.created_at.date()), c.direction, c.channel, c.content, c.status] for c in comm_log]
    )

def _csv_materials(materials):
    return _csv_buf(
        ['Fecha', 'Archivo', 'Tipo', 'Tamaño', 'Fuente', 'Notas'],
        [[str(m.created_at.date()), m.original_filename, m.file_type, m.size_display, m.source, m.notes] for m in materials]
    )

def _csv_worklog(work_logs):
    return _csv_buf(
        ['Fecha', 'Horas', 'Categoría', 'Descripción', 'URL entregable', 'Notas'],
        [[str(w.date), str(w.hours), w.category, w.description, w.deliverable_url, w.notes] for w in work_logs]
    )

def _csv_milestones(milestones):
    return _csv_buf(
        ['Título', 'Estado', 'Fecha prevista', 'Fecha completado', 'Notas'],
        [[m.title, m.status, str(m.due_date or ''), str(m.completed_date or ''), m.notes] for m in milestones]
    )

def _csv_payments(payments):
    return _csv_buf(
        ['Fecha', 'Concepto', 'Importe €', 'Método', 'Referencia', 'Estado', 'Notas'],
        [[str(p.payment_date), p.concept, str(p.amount), p.method, p.reference, p.status, p.notes] for p in payments]
    )

def _csv_evidence(evidence):
    return _csv_buf(
        ['Fecha', 'Categoría', 'Título', 'URL', 'Archivo adjunto', 'Notas'],
        [[str(e.created_at.date()), e.category, e.title, e.url, e.file.name if e.file else '', e.notes] for e in evidence]
    )

def _readme(lead, data):
    lines = [
        'DOSSIER DE ACTIVIDAD PROFESIONAL — WebImpulsa',
        '=' * 50,
        f'Cliente: {lead.name}',
        f'Proyecto: {lead.package or "—"}',
        f'Generado: {date.today().strftime("%d/%m/%Y")}',
        '',
        'ARCHIVOS INCLUIDOS EN ESTE DOSSIER:',
        '',
        'dossier_*.html    — Informe completo (abrir en navegador → Ctrl+P para PDF)',
        'timeline.csv       — Línea temporal cronológica completa',
        'datos.json         — Datos del cliente y propuestas (JSON)',
        'comunicaciones.csv — Registro de comunicaciones',
        'materiales.csv     — Materiales aportados por el cliente',
        'trabajo_realizado.csv — Registro de trabajo realizado',
        'hitos.csv          — Hitos del proyecto',
        'pagos_facturacion.csv — Registros de pago e ingresos',
        'evidencias.csv     — Evidencias y entregables',
        'archivos/          — Archivos adjuntos (facturas, evidencias, materiales)',
        '',
        'AVISO LEGAL:',
        'Este dossier es un documento de evidencia de actividad profesional',
        'para uso interno. No constituye certificado oficial ni documento',
        'contable con validez fiscal. Consultar con gestor/asesor.',
        '',
        f'Total horas registradas: {data["total_hours"]:.1f}h',
        f'Total ingresos registrados: {data["total_income"]}€',
    ]
    return '\n'.join(lines)


# ── Views ─────────────────────────────────────────────────────────────────────

@_crm_auth
@require_GET
def dossier_zip(request, pk):
    """GET /wi/crm/<pk>/dossier/ — download ZIP dossier for a single lead."""
    lead = get_object_or_404(Lead, pk=pk)
    data = _gather_lead_data(lead)
    buf  = _build_zip(lead, data)
    fname = f'dossier_webimpulsa_{lead.pk:04d}_{date.today().strftime("%Y%m%d")}.zip'
    resp = HttpResponse(buf.read(), content_type='application/zip')
    resp['Content-Disposition'] = f'attachment; filename="{fname}"'
    return resp


@_crm_auth
@require_GET
def dossier_preview(request, pk):
    """GET /wi/crm/<pk>/dossier/preview/ — HTML dossier preview (no download)."""
    lead = get_object_or_404(Lead, pk=pk)
    data = _gather_lead_data(lead)
    return render(request, 'crm/dossier.html', data)


@_crm_auth
@require_GET
def export_dashboard(request):
    """GET /wi/crm/export/ — printable activity dashboard with date filter."""
    date_from = request.GET.get('from', '')
    date_to   = request.GET.get('to', '')

    qs = Lead.objects.all().prefetch_related('proposals', 'payments')
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    leads = list(qs)
    total_income = 0
    accepted_count = 0
    for lead in leads:
        for p in lead.payments.all():
            if p.status == PaymentRecord.ST_RECEIVED:
                total_income += p.amount
        if any(pr.status == Proposal.ST_ACCEPTED for pr in lead.proposals.all()):
            accepted_count += 1

    if request.GET.get('format') == 'csv':
        return _leads_csv_response(leads)

    return render(request, 'crm/export_dashboard.html', {
        'leads':          leads,
        'date_from':      date_from,
        'date_to':        date_to,
        'total_income':   total_income,
        'accepted_count': accepted_count,
        'company':        WI_COMPANY,
        'generated_at':   timezone.now(),
    })


def _leads_csv_response(leads):
    buf = io.StringIO()
    buf.write('﻿')
    w = csv.writer(buf)
    w.writerow(['ID', 'Fecha', 'Cliente', 'Email', 'Teléfono', 'Negocio',
                'Paquete', 'Precio estimado €', 'Estado', 'Fuente',
                'Propuesta', 'Total propuesta €', 'Ingresos registrados €'])
    for lead in leads:
        prop = lead.proposals.filter(status=Proposal.ST_ACCEPTED).first() or lead.proposals.order_by('-created_at').first()
        income = sum(p.amount for p in lead.payments.filter(status=PaymentRecord.ST_RECEIVED))
        w.writerow([
            lead.pk, str(lead.created_at.date()), lead.name,
            lead.email, lead.phone, lead.biz_type, lead.package,
            lead.estimated_price, lead.status, lead.source,
            prop.number if prop else '',
            prop.total_with_iva if prop else '',
            income,
        ])
    resp = HttpResponse(buf.getvalue(), content_type='text/csv; charset=utf-8')
    resp['Content-Disposition'] = f'attachment; filename="leads_{date.today().strftime("%Y%m%d")}.csv"'
    return resp
