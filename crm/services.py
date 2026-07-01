"""CRM services — lead creation and calculator data extraction.

Designed for future extension:
  proposal_from_lead(lead)      → PDF/DOCX proposal generation
  client_portal_token(lead)     → signed URL for client portal
  invoice_from_lead(lead)       → invoice generation
  extranjeria_export(queryset)  → Extranjería CSV/XML export
"""
from .models import Lead

_DISCOUNT = 0.15
_RUSH_MULT = 1.25


def extract_calc_data(payload: dict) -> dict:
    """Parse calculator fields from the API payload into clean Lead kwargs."""
    calc = payload.get('calc') or {}

    base        = int(calc.get('base') or 0)
    extras_price = int(calc.get('extras_price') or 0)
    rush        = bool(calc.get('rush', False))

    subtotal = base + extras_price
    if rush:
        subtotal = round(subtotal * _RUSH_MULT)
    discount = round(subtotal * _DISCOUNT)
    total    = subtotal - discount

    return {
        'package':             str(calc.get('package') or '').strip()[:100],
        'package_base_price':  base,
        'extras':              [str(e) for e in (calc.get('extras') or [])],
        'extras_price':        extras_price,
        'rush':                rush,
        'maintenance_plan':    str(calc.get('maint_name') or '').strip()[:50],
        'maintenance_price':   int(calc.get('maint') or 0),
        'estimated_price':     total,
        'discount_pct':        15,
    }


def lead_from_payload(payload: dict) -> 'Lead':
    """Create and persist a Lead from a calculator submission payload.

    Expected payload structure::

        {
            "name":     str,      # required
            "contact":  str,      # required — phone or email
            "biz_type": str,      # optional
            "source":   str,      # optional, default "calculator"
            "calc": {
                "package":      str,
                "base":         int,
                "extras":       [str, ...],
                "extras_price": int,
                "rush":         bool,
                "maint":        int,
                "maint_name":   str
            }
        }
    """
    name     = str(payload.get('name')     or '').strip()[:200]
    contact  = str(payload.get('contact')  or '').strip()
    biz_type = str(payload.get('biz_type') or '').strip()[:100]
    source   = str(payload.get('source')   or Lead.SRC_CALCULATOR)

    email = contact if '@' in contact else ''
    phone = contact if '@' not in contact else ''

    return Lead.objects.create(
        name=name,
        email=email,
        phone=phone,
        biz_type=biz_type,
        source=source,
        raw_data=payload,
        **extract_calc_data(payload),
    )
