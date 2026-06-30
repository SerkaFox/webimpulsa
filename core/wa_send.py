import os
import json
import logging
import requests

logger = logging.getLogger(__name__)

GRAPH_VER = os.getenv("WI_WA_GRAPH_VERSION", "v19.0")
PHONE_ID  = os.getenv("WI_WA_PHONE_NUMBER_ID", "")
TOKEN     = os.getenv("WI_WA_ACCESS_TOKEN", "")


def _clean(phone: str) -> str:
    return "".join(ch for ch in str(phone or "") if ch.isdigit())


def send_template(to: str, template_name: str, lang: str, components: list) -> dict:
    """Send an approved WhatsApp template message (no 24-hour restriction)."""
    if not TOKEN or not PHONE_ID:
        logger.warning("WA not configured — skipping template send to %s", to)
        return {}

    url = f"https://graph.facebook.com/{GRAPH_VER}/{PHONE_ID}/messages"
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
        data=json.dumps({
            "messaging_product": "whatsapp",
            "to": _clean(to),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": lang},
                "components": components,
            },
        }, ensure_ascii=False).encode("utf-8"),
        timeout=20,
    )
    logger.info("WA template → %s [%s]: %s", to, r.status_code, r.text[:300])
    r.raise_for_status()
    return r.json()


def send_text(to: str, text: str) -> dict:
    if not TOKEN or not PHONE_ID:
        logger.warning("WA not configured — skipping send to %s", to)
        return {}

    url = f"https://graph.facebook.com/{GRAPH_VER}/{PHONE_ID}/messages"
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
        data=json.dumps({
            "messaging_product": "whatsapp",
            "to": _clean(to),
            "type": "text",
            "text": {"body": str(text)},
        }, ensure_ascii=False).encode("utf-8"),
        timeout=20,
    )
    logger.info("WA send → %s [%s]: %s", to, r.status_code, r.text[:300])
    r.raise_for_status()
    return r.json()
