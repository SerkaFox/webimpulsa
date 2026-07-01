"""WhatsApp template registry and sending adapter for WebImpulsa CRM.

Templates must be approved in Meta Business Manager before use.
The adapter currently stubs all sends; wire up real credentials by:

  1. Set WI_WA_ACCESS_TOKEN and WI_WA_PHONE_NUMBER_ID in .env
  2. Replace the _send_template() TODO body with the real API call
     (same pattern as core/wa_send.py — just copy send_template() from there)

All 10 templates below correspond to the names submitted to Meta.
"""
import logging
import os

logger = logging.getLogger(__name__)

# ── Template registry ─────────────────────────────────────────────────────────

TEMPLATES = {
    'login_code_webimpulsa': {
        'lang':        'es',
        'description': 'Código PIN de acceso al portal del cliente',
        'body_params': [
            '{{1}} = código PIN (6 dígitos)',
            '{{2}} = nombre o referencia del proyecto',
        ],
        'example':     'Tu código de acceso al portal WebImpulsa es *847291*. '
                       'Proyecto: Landing page restaurante. Válido 72 horas.',
    },
    'magic_link_webimpulsa': {
        'lang':        'es',
        'description': 'Enlace de acceso directo al portal del cliente',
        'body_params': [
            '{{1}} = nombre del cliente',
            '{{2}} = URL del portal (enlace completo)',
        ],
        'example':     'Hola María 👋 Aquí tienes el enlace a tu portal de proyecto '
                       'en WebImpulsa: https://webimpulsa.es/p/abc123/',
    },
    'proposal_ready_webimpulsa': {
        'lang':        'es',
        'description': 'Notificación de propuesta lista para revisar',
        'body_params': [
            '{{1}} = nombre del cliente',
            '{{2}} = tipo de proyecto',
            '{{3}} = URL del portal',
        ],
        'example':     'Hola Juan, tu propuesta para *Web con reservas* está lista. '
                       'Revísala aquí: https://webimpulsa.es/p/abc123/',
    },
    'proposal_accepted_webimpulsa': {
        'lang':        'es',
        'description': 'Confirmación de aceptación de propuesta',
        'body_params': [
            '{{1}} = nombre del cliente',
            '{{2}} = tipo de proyecto',
        ],
        'example':     '¡Perfecto, María! Confirmamos que has aceptado la propuesta '
                       'para tu *Landing page*. Nos ponemos en marcha 🚀',
    },
    'request_project_materials': {
        'lang':        'es',
        'description': 'Solicitud de materiales del proyecto al cliente',
        'body_params': [
            '{{1}} = nombre del cliente',
            '{{2}} = URL del portal para subir materiales',
        ],
        'example':     'Hola Carlos, para comenzar tu proyecto necesitamos algunos '
                       'materiales (logo, fotos, textos). Súbelos aquí: '
                       'https://webimpulsa.es/p/abc123/',
    },
    'materials_received_webimpulsa': {
        'lang':        'es',
        'description': 'Confirmación de recepción de materiales',
        'body_params': [
            '{{1}} = nombre del cliente',
            '{{2}} = número de archivos recibidos',
        ],
        'example':     'Hola Ana, hemos recibido tus *3 archivos* correctamente. '
                       'Comenzamos a trabajar en tu proyecto esta semana.',
    },
    'project_status_update': {
        'lang':        'es',
        'description': 'Actualización de estado del proyecto',
        'body_params': [
            '{{1}} = nombre del cliente',
            '{{2}} = resumen del avance',
            '{{3}} = URL del portal',
        ],
        'example':     'Hola Sergio, novedad en tu proyecto: *Maqueta inicial lista*. '
                       'Puedes verla en tu portal: https://webimpulsa.es/p/abc123/',
    },
    'review_required_webimpulsa': {
        'lang':        'es',
        'description': 'Solicitud de revisión y aprobación al cliente',
        'body_params': [
            '{{1}} = nombre del cliente',
            '{{2}} = URL del portal',
        ],
        'example':     'Hola Laura, tu web está casi lista ✅ Necesitamos tu '
                       'revisión y aprobación antes de publicar: '
                       'https://webimpulsa.es/p/abc123/',
    },
    'payment_reminder_webimpulsa': {
        'lang':        'es',
        'description': 'Recordatorio de pago pendiente',
        'body_params': [
            '{{1}} = nombre del cliente',
            '{{2}} = importe pendiente',
            '{{3}} = concepto',
        ],
        'example':     'Hola Pedro, te recordamos el pago pendiente de *590€* '
                       'correspondiente a: Web profesional (50% inicio).',
    },
    'project_completed_webimpulsa': {
        'lang':        'es',
        'description': 'Notificación de proyecto completado y publicado',
        'body_params': [
            '{{1}} = nombre del cliente',
            '{{2}} = URL de la web publicada',
        ],
        'example':     '🎉 ¡Hola Rosa! Tu proyecto está publicado y en línea. '
                       'Visita tu nueva web: https://tunegocio.es',
    },
}


def get_template(name: str) -> dict | None:
    return TEMPLATES.get(name)


# ── WhatsApp send adapter ─────────────────────────────────────────────────────

class WaAdapter:
    """Thin adapter over Meta WhatsApp Cloud API.

    Currently logs all sends without making real API calls.
    To activate: set WI_WA_ACCESS_TOKEN + WI_WA_PHONE_NUMBER_ID in .env
    and replace _send_template() / _send_text() with the real implementation
    from core/wa_send.py.
    """

    def __init__(self):
        self._token    = os.getenv('WI_WA_ACCESS_TOKEN', '')
        self._phone_id = os.getenv('WI_WA_PHONE_NUMBER_ID', '')
        self._version  = os.getenv('WI_WA_GRAPH_VERSION', 'v19.0')
        self._ready    = bool(self._token and self._phone_id)

    # ── public API ────────────────────────────────────────────────────────────

    def send_template(self, to: str, template_name: str, body_params: list) -> dict:
        """Send a WhatsApp template message.  Returns {'ok': bool, 'wamid': str}."""
        if not self._ready:
            logger.info('[WA-STUB] send_template → %s  tpl=%s  params=%s',
                        to, template_name, body_params)
            return {'ok': False, 'stub': True, 'wamid': ''}

        # TODO: replace with real call once credentials are confirmed
        # Example implementation (same pattern as core/wa_send.py):
        #
        # import requests
        # url = f'https://graph.facebook.com/{self._version}/{self._phone_id}/messages'
        # payload = {
        #     'messaging_product': 'whatsapp',
        #     'to': to,
        #     'type': 'template',
        #     'template': {
        #         'name': template_name,
        #         'language': {'code': TEMPLATES[template_name]['lang']},
        #         'components': [{
        #             'type': 'body',
        #             'parameters': [{'type': 'text', 'text': p} for p in body_params],
        #         }],
        #     },
        # }
        # r = requests.post(url, json=payload,
        #                   headers={'Authorization': f'Bearer {self._token}'}, timeout=10)
        # r.raise_for_status()
        # data = r.json()
        # wamid = (data.get('messages') or [{}])[0].get('id', '')
        # return {'ok': True, 'wamid': wamid}

        logger.warning('[WA] send_template called but TODO body not implemented yet')
        return {'ok': False, 'stub': True, 'wamid': ''}

    def send_text(self, to: str, text: str) -> dict:
        """Send a free-form text message (only valid within 24h window)."""
        if not self._ready:
            logger.info('[WA-STUB] send_text → %s  text=%s…', to, text[:60])
            return {'ok': False, 'stub': True, 'wamid': ''}

        # TODO: mirror core/wa_send.send_text() here
        logger.warning('[WA] send_text called but TODO body not implemented yet')
        return {'ok': False, 'stub': True, 'wamid': ''}

    # ── convenience helpers ───────────────────────────────────────────────────

    def send_portal_link(self, phone: str, client_name: str, portal_url: str) -> dict:
        """Send magic_link_webimpulsa template."""
        return self.send_template(phone, 'magic_link_webimpulsa',
                                  [client_name, portal_url])

    def send_pin_code(self, phone: str, pin: str, project_ref: str) -> dict:
        """Send login_code_webimpulsa template."""
        return self.send_template(phone, 'login_code_webimpulsa',
                                  [pin, project_ref])

    def send_request_materials(self, phone: str, client_name: str, portal_url: str) -> dict:
        """Send request_project_materials template."""
        return self.send_template(phone, 'request_project_materials',
                                  [client_name, portal_url])

    def send_materials_received(self, phone: str, client_name: str, count: int) -> dict:
        """Send materials_received_webimpulsa template."""
        return self.send_template(phone, 'materials_received_webimpulsa',
                                  [client_name, str(count)])


# Shared instance — import this in views/services
wa = WaAdapter()


# ── Compose helper (plain text fallback for manual copy/paste) ────────────────

def compose_portal_message(client_name: str, portal_url: str, pin: str | None = None) -> str:
    """Return a WhatsApp message body to copy-paste if templates aren't ready."""
    lines = [
        f'Hola {client_name} 👋',
        '',
        'Aquí tienes el enlace a tu portal de proyecto en *WebImpulsa*:',
        f'🔗 {portal_url}',
    ]
    if pin:
        lines += ['', f'Tu código de acceso: *{pin}*', '(válido 72 horas)']
    lines += ['', '¿Tienes alguna duda? Escríbenos 😊']
    return '\n'.join(lines)


def compose_materials_request(client_name: str, portal_url: str) -> str:
    """Return a WhatsApp message to request project materials."""
    return (
        f'Hola {client_name} 👋\n\n'
        'Para avanzar con tu proyecto necesitamos algunos materiales:\n\n'
        '📸 Fotos del negocio o productos\n'
        '🎨 Logo (si tienes)\n'
        '📝 Textos / descripción de servicios\n'
        '📄 Cualquier referencia o documento útil\n\n'
        f'Puedes subirlos directamente aquí:\n🔗 {portal_url}\n\n'
        '¡Sin prisa, cuando puedas! 😊'
    )
