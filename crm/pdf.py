"""Server-side PDF generation for commercial proposals."""
import logging

from django.template.loader import render_to_string

from .proposal_content import PROJECT_SCOPES, DEFAULT_SCOPE, DEADLINES, PHASES, CONDITIONS, OUT_OF_SCOPE

logger = logging.getLogger(__name__)


def generate_proposal_pdf(proposal) -> bytes | None:
    """Generate a PDF from an existing Proposal object. Returns bytes or None."""
    try:
        from weasyprint import HTML
    except ImportError:
        logger.error('weasyprint not installed — PDF skipped')
        return None

    try:
        c = proposal.company_data or {}
        subtotal_before_discount = (
            proposal.package_base_price + proposal.extras_price + proposal.rush_amount
        )
        ctx = {
            'proposal':    proposal,
            'company': {
                'trade_name': c.get('trade_name', 'WebImpulsa'),
                'legal_name': c.get('legal_name', ''),
                'nif':        c.get('nif', ''),
                'email':      c.get('email', 'info@webimpulsa.es'),
                'phone':      c.get('phone', '+34 613 708 322'),
                'website':    c.get('website', 'https://webimpulsa.es'),
                'address':    c.get('address', ''),
                'city':       c.get('city', ''),
            },
            'scope':       proposal.scope or PROJECT_SCOPES.get(proposal.package, DEFAULT_SCOPE),
            'out_of_scope': proposal.out_of_scope or OUT_OF_SCOPE,
            'phases':      proposal.phases or PHASES,
            'conditions':  proposal.conditions or CONDITIONS,
            'deadline':    proposal.timeline or DEADLINES.get(proposal.package, 'Según alcance'),
            'subtotal_before_discount': subtotal_before_discount,
            'half_payment': round(proposal.taxable_base / 2),
        }
        html_str = render_to_string('crm/proposal_pdf.html', ctx)
        pdf_bytes = HTML(string=html_str, base_url='https://webimpulsa.es').write_pdf()
        logger.info('PDF generated: proposal %s (%d bytes)', proposal.number, len(pdf_bytes))
        return pdf_bytes

    except Exception as exc:
        logger.error('PDF generation failed for proposal %s: %s', proposal.number, exc, exc_info=True)
        return None


def generate_lead_pdf(lead) -> bytes | None:
    """Convenience wrapper: create proposal from lead, then generate PDF."""
    from .services import create_proposal_from_lead
    proposal = create_proposal_from_lead(lead)
    return generate_proposal_pdf(proposal)
