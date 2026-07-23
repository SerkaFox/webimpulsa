"""PDF del informe de chequeo digital — mismo patrón que crm/pdf.py:
contexto -> render_to_string -> weasyprint.HTML(...).write_pdf()."""
import base64
import io
import logging

from django.template.loader import render_to_string

from .quiz_config import CATEGORY_LABELS, QUESTIONS

logger = logging.getLogger(__name__)


def _qr_data_uri(url):
    try:
        import qrcode
    except ImportError:
        logger.warning('qrcode no instalado — PDF sin código QR')
        return ''
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def generate_audit_pdf(audit) -> bytes | None:
    """PDF de un ChequeoAudit concreto: empresa, fecha, preliminar/confirmado,
    puntuación 0-100, categorías, puntos fuertes, hasta 3 recomendaciones, QR
    al resultado y aviso de que es orientativo."""
    try:
        from weasyprint import HTML
    except ImportError:
        logger.error('weasyprint no instalado — PDF omitido')
        return None

    by_id = {q['id']: q for q in QUESTIONS}
    good = [by_id[qid]['good'] for qid in (audit.good_ids or []) if qid in by_id]
    recommendations = [by_id[qid]['fix'] for qid in (audit.fix_ids or []) if qid in by_id][:3]

    company_name = audit.prospect.name if audit.prospect_id else 'Autodiagnóstico'
    if audit.prospect_id:
        result_url = f'https://webimpulsa.es/chequeo-digital/e/{audit.prospect.public_token}/'
    else:
        result_url = 'https://webimpulsa.es/chequeo-digital/'

    category_scores = audit.category_scores or {}
    categories = [
        {'label': label, 'score': category_scores.get(key, 0)}
        for key, label in CATEGORY_LABELS.items()
    ]

    try:
        ctx = {
            'audit': audit,
            'company_name': company_name,
            'categories': categories,
            'good': good,
            'recommendations': recommendations,
            'qr_data_uri': _qr_data_uri(result_url),
            'result_url': result_url,
        }
        html_str = render_to_string('prospeccion/audit_pdf.html', ctx)
        pdf_bytes = HTML(string=html_str, base_url='https://webimpulsa.es').write_pdf()
        logger.info('PDF generado: audit #%s (%d bytes)', audit.pk, len(pdf_bytes))
        return pdf_bytes
    except Exception as exc:
        logger.error('Fallo generando PDF del audit #%s: %s', audit.pk, exc, exc_info=True)
        return None
