"""Cliente para el bridge de WhatsApp no oficial que ya corre en producción
para el proyecto `anna` (whatsapp-web.js, servicio systemd
brimoon-whatsapp-bridge, ver /home/seradmin/anna/whatsapp_bridge). No es la
API oficial de Meta, así que no tiene la restricción de "primer mensaje debe
ser una plantilla aprobada" — puede mandar texto libre a cualquier número.
Calca el patrón de `anna/whatsapp_bot/bridge.py` (stdlib urllib, sin
dependencias nuevas) para no introducir `requests` solo para esto.
"""
import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)


class WhatsAppBridgeError(Exception):
    pass


def _clean_phone(phone):
    return ''.join(ch for ch in str(phone or '') if ch.isdigit())


def send_text(to_phone: str, body: str, *, timeout: int = 20) -> dict:
    """Manda un mensaje de texto a `to_phone` desde la sesión configurada
    (WHATSAPP_BRIDGE_SESSION). Lanza WhatsAppBridgeError si el bridge no está
    configurado, no responde o la sesión no está lista — quien llama decide
    si eso debe bloquear la petición HTTP al usuario o solo loguearse."""
    base_url = getattr(settings, 'WHATSAPP_BRIDGE_URL', '').rstrip('/')
    if not base_url:
        raise WhatsAppBridgeError('WHATSAPP_BRIDGE_URL no está configurada.')

    digits = _clean_phone(to_phone)
    if not digits:
        raise WhatsAppBridgeError('Número de teléfono vacío o inválido.')

    payload = {
        'session': getattr(settings, 'WHATSAPP_BRIDGE_SESSION', 'aura_demo'),
        'to': digits,
        'body': str(body),
    }
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    token = getattr(settings, 'WHATSAPP_BRIDGE_TOKEN', '')
    if token:
        headers['Authorization'] = f'Bearer {token}'

    request = Request(
        f'{base_url}/messages',
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method='POST',
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode('utf-8')
    except HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise WhatsAppBridgeError(f'Bridge HTTP {exc.code}: {detail}') from exc
    except URLError as exc:
        raise WhatsAppBridgeError(f'Bridge no disponible: {exc.reason}') from exc

    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise WhatsAppBridgeError('El bridge devolvió una respuesta no válida.') from exc
