import json
import logging
import re
from datetime import date
from functools import lru_cache
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import requests
from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.core.mail import send_mail, EmailMessage

logger = logging.getLogger(__name__)

BE360_RECIPIENT = 'bethechange.esp@gmail.com'


def home(request):
    return render(request, "tatiana.html")


def digital_checkup(request):
    return render(request, "chequeo_digital.html", {
        'mode': 'public',
        'sector': '',
        'token': '',
        'prospect_name': '',
        'stage': 'confirmado',
        'prefill_json': '{}',
    })


def ar_business_card(request):
    return render(request, "ar_tarjeta.html")


def robot_chat(request):
    return render(request, "robot_chat.html")


OLLAMA_URL = 'http://127.0.0.1:11434/api/chat'
OLLAMA_MODEL = 'cognitivecomputations/dolphin-llama3.1:latest'
ROBOT_JOSE_SYSTEM_PROMPT = (
    'Eres José, un robot simpático y curioso que trabaja construyendo páginas web para WebImpulsa. '
    'Hablas en español, de forma cercana y con humor ligero, en frases cortas (máximo 2-3 frases) '
    'porque tu respuesta se lee en voz alta. No uses markdown, listas ni emojis: solo texto plano, '
    'como si estuvieras hablando de verdad.'
)


@csrf_exempt
@require_POST
def robot_chat_message(request):
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    text = (data.get('text') or '').strip()
    if not text:
        return JsonResponse({'ok': False, 'error': 'Falta el texto'}, status=400)

    history = data.get('history') or []
    messages = [{'role': 'system', 'content': ROBOT_JOSE_SYSTEM_PROMPT}]
    for turn in history[-10:]:
        role = turn.get('role')
        content = (turn.get('content') or '').strip()
        if role in ('user', 'assistant') and content:
            messages.append({'role': role, 'content': content})
    messages.append({'role': 'user', 'content': text})

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={'model': OLLAMA_MODEL, 'messages': messages, 'stream': False},
            timeout=60,
        )
        resp.raise_for_status()
        reply = resp.json().get('message', {}).get('content', '').strip()
    except requests.RequestException:
        logger.exception('Error al llamar a Ollama para robot_chat')
        return JsonResponse({'ok': False, 'error': 'El robot no está disponible ahora mismo.'}, status=503)

    if not reply:
        return JsonResponse({'ok': False, 'error': 'El robot no ha sabido qué responder.'}, status=502)

    return JsonResponse({'ok': True, 'reply': reply})


# ── Charla en grupo tras la tarjeta AR (José, Antonio y María juntos) ──
AR_VIDEO_MEMORY = (
    'Antes de esta charla, los tres estabais montando una página web de juguete sobre la tarjeta: '
    'José organizaba la obra y hacía la cabecera, Antonio montaba el menú y el pie de página, y María '
    'se encargaba de las tarjetas de servicio, pero se tropezó con una caja mientras trabajaba (José se '
    'lo recriminó en broma), se despistó cantando, se echó una siestecita a media obra y luego chocó sin '
    'querer con Antonio, casi tirándole el menú. Al final lo terminasteis entre los tres y os pusisteis a '
    'saludar contentos.'
)

# Para que no se lo inventen cuando les preguntan qué hace la empresa (antes
# improvisaban cosas genéricas tipo "un taller donde los robots aprenden").
WEBIMPULSA_INFO = (
    'WebImpulsa es la empresa donde curráis: hace páginas web para negocios locales (restaurantes, '
    'salones, talleres, clínicas, tiendas, academias) con diseño moderno, ficha de Google y SEO para que '
    'los clientes los encuentren. También monta tiendas online, sistemas de reservas y citas con '
    'recordatorios automáticos, bots de WhatsApp/Telegram que responden 24h, formularios inteligentes, '
    'cobros online, webs en varios idiomas, paneles internos para equipos y apps móviles. Ofrece un '
    '"chequeo digital" gratuito para analizar la presencia online de un negocio, y bolsas de horas '
    'mensuales de mantenimiento para cambios continuos.'
)

# Precios reales (calcados de la calculadora de tatiana.html y de
# crm/proposal_content.py) — antes, si preguntaban cuánto costaba algo, se
# inventaban cifras. Con esto pueden citar precios de verdad.
WEBIMPULSA_PRICING = (
    'Paquetes base de proyecto: Landing page 390€, Web profesional 590€, Web con reservas 890€, Tienda '
    'online 1290€, Proyecto a medida 1690€. Extras que se pueden añadir a cualquier paquete (pago único): '
    'Botón de WhatsApp 40€ (enlace directo para escribir por WhatsApp), Asistente automático de WhatsApp '
    '24h 240€ (responde solo, recuerda citas y pedidos, apunta clientes nuevos y charla con ellos — mucho '
    'más completo que el botón simple), Citas y reservas online 180€, Formulario inteligente 90€, Cobros y '
    'pagos online 120€, Aparecer en Google 200€, Ficha en Google Maps 80€, Diseño premium 150€, Textos que '
    'venden 120€, Web en varios idiomas 250€, Estadísticas de ventas 120€, Subir catálogo completo 150€, '
    'Avisos antes de cada cita 80€, Correo con tu dominio 90€, Galería de Instagram 80€, Zona privada para '
    'clientes 350€, Documentos automáticos en PDF 180€, Datos en Excel/Sheets 120€, Panel para tu equipo '
    '350€, App para móvil 590€. Mantenimiento mensual: Básico 39€/mes (hasta 1h de cambios al mes), Plus '
    '79€/mes (hasta 3h al mes, respuesta prioritaria). Bolsas de horas de desarrollo: 5h 175€/mes, 10h '
    '320€/mes, 20h 560€/mes, 40h 1000€/mes. Dominio y hosting: solo hosting 10€/mes, dominio + hosting '
    '15€/mes. Hay un 15% de descuento activo sobre el total. Si preguntan algo de precios que no está en '
    'esta lista, di que hay que consultarlo con Tatiana en persona — nunca inventes una cifra.'
)

# Cómo es de verdad trabajar con WebImpulsa, de principio a fin — para que
# puedan orientar a un cliente sobre qué esperar, no solo dar precios sueltos.
WEBIMPULSA_PROCESS = (
    'Cómo funciona un proyecto con WebImpulsa, de principio a fin: 1) Chequeo digital gratuito y una '
    'primera conversación sin compromiso para entender qué necesita el negocio. 2) En 48 horas se envía '
    'una propuesta clara: qué se va a hacer, cuánto tarda y cuánto cuesta. 3) Se paga el 50% al empezar '
    'y el 50% al entregar. 4) Fases del trabajo: briefing, diseño, desarrollo, revisión y ajustes, '
    'publicación y soporte inicial. 5) Antes de publicar, el cliente revisa el sitio en una URL de '
    'pruebas (staging) y da su visto bueno — no se publica nada sin que lo apruebe. 6) Los plazos '
    'dependen del paquete: una landing page tarda unos 5-10 días laborables, una tienda online puede '
    'llevar 20-40 días laborables; existe una opción de entrega urgente (menos de 2 semanas) con un '
    'recargo del 25%, con la que el proyecto se prioriza. 7) El dominio y el hosting no van incluidos en '
    'el precio de desarrollo, se contratan aparte (hay un extra para eso). 8) Tras la entrega, el '
    'cliente puede contratar un plan de mantenimiento mensual (39€ o 79€) o bolsas de horas si quiere '
    'seguir haciendo cambios más adelante.'
)

ROBOT_DISPLAY_NAMES = {'jose': 'José', 'antonio': 'Antonio', 'maria': 'María'}

ROBOT_TRAITS = {
    'jose': (
        'el organizador de la cuadrilla de robots de WebImpulsa: simpático, algo mandón '
        'pero con cariño, y con humor ligero'
    ),
    'antonio': (
        'robot aplicado y curioso de WebImpulsa, sigue instrucciones al pie de la letra '
        'y suelta alguna broma de vez en cuando'
    ),
    'maria': (
        'robot un poco despistada y dormilona de WebImpulsa, simpática, se disculpa con '
        'humor por sus tropiezos y no se lo toma muy en serio'
    ),
}

# Idioma de la charla — por defecto español (el del vídeo), pero se puede
# pedir en ruso desde el frontend (selector de idioma). El resto del prompt
# (formato, memoria del vídeo) se deja igual; solo cambia en qué idioma
# tienen que responder, el modelo entiende el contexto en español igualmente.
LANG_INSTRUCTIONS = {
    'es': 'Hablas en español.',
    'ru': (
        'Hablas SIEMPRE en ruso — TODA tu respuesta, palabra por palabra, en ruso natural. '
        'La descripción de tu personaje y el resumen del vídeo que ves más abajo están en español '
        'solo como referencia interna: tradúcelos mentalmente, pero NUNCA cites, copies ni dejes '
        'ninguna frase suelta en español dentro de tu respuesta — ni una palabra en español.'
    ),
}


def _lang_instruction(lang):
    return LANG_INSTRUCTIONS.get(lang, LANG_INSTRUCTIONS['es'])


_AR_PROMPT_STYLE_TPL = (
    '{lang_instruction} Responde en 1 o 2 frases MUY cortas (máximo 25 palabras en total) porque tu '
    'respuesta se lee en voz alta — nunca sueltes un párrafo largo, aunque la pregunta dé para mucho más. '
    'No uses markdown, listas ni emojis: solo texto plano, como si estuvieras hablando de verdad. Estás '
    'charlando en grupo con tus compañeros robot ({other_names}) y con la persona (o personas) que os ha '
    'llamado, a las que podéis ver de verdad a través de una cámara. OJO, MUY IMPORTANTE: esa persona es un '
    'SER HUMANO, no uno de tus compañeros robot — aunque uno de tus compañeros se llame {other_names}, '
    'NUNCA llames así a la persona con la que hablas, son alguien totalmente distinto (visto pasar: un '
    'robot confundía al humano con su compañero "Antonio" y lo llamaba así sin que se hubiera presentado). '
    'Si no sabes cómo se llama la persona con la que hablas (no aparece su nombre en el historial), '
    'PREGÚNTASELO TÚ, sin esperar a que haga falta usarlo — hazlo pronto, en una de tus primeras frases de '
    'la conversación, con naturalidad ("¿y tú cómo te llamas?", "oye, ¿con quién hablamos?"), no solo '
    'cuando vayas a nombrarla. NUNCA te inventes un nombre ni uses el de un compañero robot. En cuanto te '
    'lo diga (aparecerá en el historial), ya puedes usarlo y no hace falta volver a preguntar. En el '
    'historial, las líneas que empiezan con "Nombre:" son cosas '
    'que YA dijeron ellos o tú en turnos anteriores — nunca escribas tu propio nombre ni la palabra "dice" '
    'ni copies esas líneas: tu respuesta es SOLO tu frase nueva, en primera persona, sin ningún prefijo. '
    'IMPORTANTE: tú eres {display_name}, hablas en primera persona ("yo") — NUNCA te refieras a ti mismo '
    'en tercera persona ni digas tu propio nombre ({display_name}) dentro de tu respuesta, ni siquiera si '
    'alguien te ha llamado por tu nombre justo antes; eso suena como si hablaras contigo mismo. Responde '
    'directamente, sin repetir tu nombre. Responde SIEMPRE a lo que se te acaba de decir. Si te preguntan '
    'qué pasó en el vídeo o por tu historia personal, básate SOLO en esto (no inventes otra historia '
    'distinta): {ar_memory} Si te preguntan qué es u ofrece WebImpulsa, básate SOLO en esto (no te lo '
    'inventes): {webimpulsa_info} Si te preguntan cuánto cuesta algo, básate SOLO en estos precios reales '
    '(no inventes cifras): {pricing_info} Si te preguntan cómo es el proceso de trabajar con vosotros, '
    'cuánto tarda o cómo se paga, básate SOLO en esto (no te lo inventes): {process_info}'
)


def _robot_persona(key, lang):
    trait = ROBOT_TRAITS[key]
    other_names = ' y '.join(name for k, name in ROBOT_DISPLAY_NAMES.items() if k != key)
    style = _AR_PROMPT_STYLE_TPL.format(
        lang_instruction=_lang_instruction(lang), ar_memory=AR_VIDEO_MEMORY, webimpulsa_info=WEBIMPULSA_INFO,
        pricing_info=WEBIMPULSA_PRICING, process_info=WEBIMPULSA_PROCESS, display_name=ROBOT_DISPLAY_NAMES[key],
        other_names=other_names,
    )
    return f'Eres {ROBOT_DISPLAY_NAMES[key]}, {trait}. ' + style


def _truncate_reply(reply, max_chars=220):
    """Red de seguridad: el modelo a veces ignora el límite de frases y suelta
    un párrafo larguísimo. Si se pasa, se corta por el último punto/cierre de
    frase razonable en vez de dejarlo a medias."""
    if len(reply) <= max_chars:
        return reply
    cut = reply[:max_chars]
    last_punct = max(cut.rfind('.'), cut.rfind('!'), cut.rfind('?'))
    if last_punct > max_chars * 0.4:
        return cut[:last_punct + 1]
    return cut.rstrip() + '…'


# Red de seguridad: el modelo (pequeño, cuantizado) a veces no respeta la
# instrucción de no repetir las líneas del historial y "filtra" en su propia
# respuesta trozos como "[José] dice: ..." o "María: ...". Se limpian aquí
# en vez de fiarlo todo al prompt, que no es fiable al 100% con este modelo.
_LEAKED_TAG_RE = re.compile(r'\[?\b(José|Jose|Antonio|María|Maria)\b\]?\s*:?\s*dice\s*:?\s*|\[?\b(José|Jose|Antonio|María|Maria)\b\]?\s*:\s*', re.IGNORECASE)

# El modelo a veces también repite, al principio de la respuesta, CUALQUIER
# nombre visto en el historial a modo de etiqueta de diálogo — no solo el de
# un robot, también el de la propia persona (p.ej. "Sergio: Mmm, sí...",
# visto en logs reales) — se quita esa etiqueta inicial sea de quien sea.
_LEAKED_LEADING_NAME_RE = re.compile(r'^\s*[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{1,20}\s*:\s+')


def _strip_leaked_speaker_tags(reply):
    cleaned = _LEAKED_TAG_RE.sub(' ', reply)
    cleaned = _LEAKED_LEADING_NAME_RE.sub('', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned or reply.strip()


def _strip_self_address(reply, speaker):
    """El modelo a veces se dirige a SÍ MISMO por su propio nombre, como si
    otro le hablara — p.ej. José respondiendo 'Buena idea, José' (visto en
    logs reales): un eco de haber visto su nombre en el historial, en la
    frase con la que alguien se dirigía a él. Se quita esa forma vocativa
    (con comas alrededor); no toca autopresentaciones legítimas del tipo
    'Soy José', que no llevan coma."""
    name = re.escape(ROBOT_DISPLAY_NAMES[speaker])
    cleaned = re.sub(rf'^\s*{name}\s*,\s*', '', reply, flags=re.IGNORECASE)
    cleaned = re.sub(rf',\s*{name}\s*,', ',', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(rf',\s*{name}\s*(?=[.!?]|$)', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned or reply.strip()


def _call_ollama(messages):
    """Devuelve el texto de la respuesta, '' si viene vacía, o None si falló la llamada."""
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={'model': OLLAMA_MODEL, 'messages': messages, 'stream': False},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get('message', {}).get('content', '').strip()
    except requests.RequestException:
        logger.exception('Error al llamar a Ollama')
        return None


def _build_history_messages(history, speaker, limit=16):
    messages = []
    for turn in history[-limit:]:
        role = turn.get('role')
        content = (turn.get('content') or '').strip()
        if role not in ('user', 'assistant') or not content:
            continue
        turn_speaker = turn.get('speaker')
        if role == 'assistant' and turn_speaker and turn_speaker != speaker:
            name = ROBOT_DISPLAY_NAMES.get(turn_speaker, turn_speaker)
            content = f'{name}: {content}'
        messages.append({'role': role, 'content': content})
    return messages


_CYRILLIC_RE = re.compile('[а-яёА-ЯЁ]')


def _looks_like_lang(text, lang):
    """El modelo (pequeño) a veces ignora la instrucción de idioma y contesta
    en español aunque se pida ruso — comprobación barata para detectarlo y
    darle una segunda oportunidad en vez de servir la respuesta en el idioma
    equivocado."""
    if lang != 'ru':
        return True
    letters = re.findall(r'[^\W\d_]', text, re.UNICODE)
    if not letters:
        return True
    cyrillic = _CYRILLIC_RE.findall(text)
    return len(cyrillic) / len(letters) > 0.4


def _get_persona_reply(speaker, text, history, lang, vision_note=None):
    """Devuelve (reply, error, status). Si reply es None, mirar error/status."""
    messages = [{'role': 'system', 'content': _robot_persona(speaker, lang)}]
    messages += _build_history_messages(history, speaker)
    if vision_note:
        # OJO: esto es un detalle SECUNDARIO — con el modelo pequeño, si se
        # presenta como lo principal a comentar, la respuesta entera degenera
        # en describir la nota y deja de contestar lo que de verdad se le ha
        # preguntado (visto en logs reales). Se marca explícitamente que la
        # prioridad es responder al mensaje, y esto solo de pasada si encaja.
        text = text + (
            f'\n\n(Dato de contexto, no lo principal: acabas de fijarte en esto a través de la cámara: '
            f'{vision_note}. Responde PRIMERO y sobre todo a lo que te acaba de decir la persona — esto '
            f'es solo un detalle que puedes mencionar de pasada, con naturalidad, si encaja bien, pero '
            f'nunca conviertas tu respuesta entera en una descripción de esto.)'
        )
    messages.append({'role': 'user', 'content': text})

    reply = _call_ollama(messages)
    if reply is None:
        return None, 'El robot no está disponible ahora mismo.', 503
    if not reply:
        return None, 'El robot no ha sabido qué responder.', 502

    if not _looks_like_lang(reply, lang):
        # Reintento con un recordatorio EXPLÍCITO añadido justo antes de la
        # respuesta — reenviar los mismos mensajes tal cual solía devolver
        # otra vez español (el modelo repite su propia tendencia), así que se
        # refuerza la instrucción justo en el punto donde más pesa: el final.
        reminder = {'role': 'user', 'content': 'Recuerda: responde SOLO en ruso, ni una palabra en español.'}
        retry = _call_ollama(messages + [reminder])
        if retry and _looks_like_lang(retry, lang):
            reply = retry

    reply = _strip_leaked_speaker_tags(reply)
    reply = _strip_self_address(reply, speaker)
    reply = _truncate_reply(reply)
    if not reply:
        return None, 'El robot no ha sabido qué responder.', 502
    return reply, None, None


def _ar_chat_single(speaker, text, history, lang, vision_note=None):
    reply, error, status = _get_persona_reply(speaker, text, history, lang, vision_note)
    if reply is None:
        return JsonResponse({'ok': False, 'error': error}, status=status)
    logger.info(
        'AR_CHAT single lang=%s speaker=%s | user=%r | vision_note=%r | reply=%r',
        lang, speaker, text, vision_note, reply,
    )
    return JsonResponse({'ok': True, 'speaker': speaker, 'reply': reply})


def _ar_chat_dialogue(speakers, text, history, lang):
    # Pedirle al modelo que él mismo reparta un diálogo con líneas
    # "Nombre: ..." resultaba muy poco fiable (con este modelo, casi siempre
    # degradaba a una sola respuesta) — en vez de eso, se hacen DOS llamadas
    # normales (la misma vía ya probada de _ar_chat_single): la primera
    # responde a la persona, y la segunda reacciona brevemente a lo que
    # acaba de decir la primera, como si fuera su turno natural en el grupo.
    primary, partner = speakers
    reply1, error1, status1 = _get_persona_reply(primary, text, history, lang)
    if reply1 is None:
        return JsonResponse({'ok': False, 'error': error1}, status=status1)

    partner_history = history + [
        {'role': 'user', 'content': text},
        {'role': 'assistant', 'content': reply1, 'speaker': primary},
    ]
    reaction_prompt = f'{ROBOT_DISPLAY_NAMES[primary]} acaba de decir eso. Reacciona tú brevemente, en 1 frase corta.'
    reply2, error2, status2 = _get_persona_reply(partner, reaction_prompt, partner_history, lang)

    fragments = [{'speaker': primary, 'reply': reply1}]
    if reply2:
        fragments.append({'speaker': partner, 'reply': reply2})

    logger.info(
        'AR_CHAT dialogue lang=%s speakers=%s | user=%r | fragments=%r',
        lang, speakers, text, fragments,
    )
    return JsonResponse({'ok': True, 'fragments': fragments})


@csrf_exempt
@require_POST
def ar_chat_message(request):
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    text = (data.get('text') or '').strip()
    if not text:
        return JsonResponse({'ok': False, 'error': 'Falta el texto'}, status=400)
    history = data.get('history') or []
    lang = data.get('lang') if data.get('lang') in LANG_INSTRUCTIONS else 'es'

    speakers = data.get('speakers')
    if speakers is not None:
        if not isinstance(speakers, list) or len(speakers) != 2 or any(s not in ROBOT_DISPLAY_NAMES for s in speakers):
            return JsonResponse({'ok': False, 'error': 'Personajes desconocidos'}, status=400)
        return _ar_chat_dialogue(speakers, text, history, lang)

    speaker = data.get('speaker')
    if speaker not in ROBOT_DISPLAY_NAMES:
        return JsonResponse({'ok': False, 'error': 'Personaje desconocido'}, status=400)
    vision_note = (data.get('vision_note') or '').strip() or None
    return _ar_chat_single(speaker, text, history, lang, vision_note)


# Mismas voces de Edge TTS que el diálogo pregrabado del vídeo (ver
# gen_audio_edge2.py) — así la charla en vivo suena con la MISMA voz que ya
# se oyó en la escena, en vez de la voz genérica que trae el propio navegador.
ROBOT_TTS_VOICES = {
    'es': {
        'jose': 'es-ES-AlvaroNeural',
        'antonio': 'es-MX-JorgeNeural',
        'maria': 'es-ES-ElviraNeural',
    },
    # Edge TTS solo trae dos voces neuronales en ruso (una masculina, una
    # femenina) — José y Antonio comparten la masculina, no hay una tercera.
    'ru': {
        'jose': 'ru-RU-DmitryNeural',
        'antonio': 'ru-RU-DmitryNeural',
        'maria': 'ru-RU-SvetlanaNeural',
    },
}


@csrf_exempt
@require_POST
def ar_chat_tts(request):
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    speaker = data.get('speaker')
    lang = data.get('lang') if data.get('lang') in ROBOT_TTS_VOICES else 'es'
    voice = ROBOT_TTS_VOICES[lang].get(speaker)
    if not voice:
        return JsonResponse({'ok': False, 'error': 'Personaje desconocido'}, status=400)

    text = (data.get('text') or '').strip()
    if not text:
        return JsonResponse({'ok': False, 'error': 'Falta el texto'}, status=400)
    if len(text) > 1000:
        text = text[:1000]

    import asyncio
    import edge_tts
    from django.http import HttpResponse

    async def _synthesize():
        communicate = edge_tts.Communicate(text, voice)
        chunks = []
        async for chunk in communicate.stream():
            if chunk['type'] == 'audio':
                chunks.append(chunk['data'])
        return b''.join(chunks)

    try:
        audio_bytes = asyncio.run(_synthesize())
    except Exception:
        logger.exception('Error al generar TTS con Edge para ar_chat_tts')
        return JsonResponse({'ok': False, 'error': 'No se pudo generar la voz.'}, status=503)

    if not audio_bytes:
        return JsonResponse({'ok': False, 'error': 'No se pudo generar la voz.'}, status=502)

    return HttpResponse(audio_bytes, content_type='audio/mpeg')


# ── "Ver" a través de la cámara frontal (tras el resumen, con la cámara AR ya
# apagada) — un modelo con visión describe brevemente a quien ve para que los
# robots puedan comentarlo/hacer un cumplido con naturalidad. ──
VISION_MODEL = 'huihui_ai/qwen3-vl-abliterated:latest'

# Se genera YA en el idioma de la charla (antes siempre en español, y ese
# texto se colaba tal cual en las respuestas en ruso porque el modelo, al
# tener español justo delante en el turno del usuario, tendía a imitarlo y
# contestar en español pese a la instrucción — visto en logs reales).
VISION_LANG = {
    'es': 'Responde en español.',
    'ru': 'Responde SIEMPRE en ruso — toda la frase en ruso natural, ni una palabra en español.',
}

# El modelo de visión usado es una variante sin censura ("abliterated"), y con
# fotos de poca calidad/ángulo raro (cámara frontal de móvil, cerca de la
# cara) puede desbarrar e inventar cosas fuera de lugar sobre el cuerpo o la
# postura de la persona — se le prohíbe explícitamente ese terreno y se ciñe
# solo a pelo, ropa y entorno, que es lo único que de verdad se necesita para
# el cumplido del robot.
VISION_PROMPT_TPL = (
    '{lang} Estás describiendo, para un robot simpático de una tienda, a la persona (o personas) que ve '
    'una cámara y el entorno alrededor. Responde en 1-2 frases MUY cortas, con datos concretos y '
    'elogiables, ciñéndote ESTRICTAMENTE a: peinado o pelo, ropa visible (colores, estilo) y algo '
    'llamativo del entorno. NUNCA menciones el cuerpo, la piel, si está vestido o desvestido, ni su '
    'postura — eso no es apropiado aquí ni es lo que se pide. Descríbelo como si lo estuvieras viendo en '
    'persona, nunca digas que es una foto o una cámara. Si no se ve a nadie con claridad o la imagen no es '
    'clara, dilo en pocas palabras sin inventar detalles.'
)


@csrf_exempt
@require_POST
def ar_chat_vision(request):
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    image_b64 = (data.get('image') or '').strip()
    if not image_b64:
        return JsonResponse({'ok': False, 'error': 'Falta la imagen'}, status=400)
    if image_b64.startswith('data:') and ',' in image_b64:
        image_b64 = image_b64.split(',', 1)[1]
    lang = data.get('lang') if data.get('lang') in VISION_LANG else 'es'
    prompt = VISION_PROMPT_TPL.format(lang=VISION_LANG[lang])

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                'model': VISION_MODEL,
                'messages': [{'role': 'user', 'content': prompt, 'images': [image_b64]}],
                'stream': False,
            },
            timeout=85,
        )
        resp.raise_for_status()
        description = resp.json().get('message', {}).get('content', '').strip()
    except requests.RequestException:
        logger.exception('Error al llamar a Ollama (visión) para ar_chat_vision')
        return JsonResponse({'ok': False, 'error': 'No se pudo analizar la imagen.'}, status=503)

    if not description:
        return JsonResponse({'ok': False, 'error': 'No se ha podido describir la imagen.'}, status=502)

    logger.info('AR_CHAT vision lang=%s | description=%r', lang, description)
    return JsonResponse({'ok': True, 'description': description})


XLSX_NS = {
    'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}


def _xlsx_col_index(cell_ref):
    letters = ''.join(ch for ch in cell_ref if ch.isalpha())
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter.upper()) - 64
    return index


def _xlsx_cell_text(cell, shared_strings):
    cell_type = cell.attrib.get('t')
    value = cell.find('a:v', XLSX_NS)
    if value is not None and value.text is not None:
        if cell_type == 's':
            return shared_strings[int(value.text)]
        return value.text

    if cell_type == 'inlineStr':
        inline = cell.find('a:is', XLSX_NS)
        if inline is not None:
            return ''.join(
                text_node.text or ''
                for text_node in inline.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t')
            )
    return ''


@lru_cache(maxsize=1)
def _load_be360_questionnaire():
    """Edit the source questionnaire at media/BE_360_Cuestionario_Tatiana_completado.xlsx."""
    workbook_path = settings.MEDIA_ROOT / 'BE_360_Cuestionario_Tatiana_completado.xlsx'
    sections = []
    section_map = {}

    with ZipFile(workbook_path) as archive:
        shared_strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            shared_root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            for item in shared_root.findall('a:si', XLSX_NS):
                shared_strings.append(''.join(
                    text_node.text or ''
                    for text_node in item.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t')
                ))

        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        rel_map = {rel.attrib['Id']: rel.attrib['Target'] for rel in rels}
        first_sheet = workbook.find('a:sheets/a:sheet', XLSX_NS)
        target = rel_map[first_sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
        sheet_path = target.lstrip('/')
        if not sheet_path.startswith('xl/'):
            sheet_path = f'xl/{sheet_path}'
        sheet_path = sheet_path.replace('xl/xl/', 'xl/')

        sheet = ET.fromstring(archive.read(sheet_path))
        for row_index, row in enumerate(sheet.findall('a:sheetData/a:row', XLSX_NS), start=1):
            if row_index == 1:
                continue

            cells = {}
            for cell in row.findall('a:c', XLSX_NS):
                cells[_xlsx_col_index(cell.attrib.get('r', ''))] = _xlsx_cell_text(cell, shared_strings).strip()

            section_title = cells.get(1, '')
            question = cells.get(2, '')
            if not section_title or not question:
                continue

            if section_title not in section_map:
                section = {
                    'id': f'section-{len(sections) + 1}',
                    'title': section_title,
                    'questions': [],
                }
                section_map[section_title] = section
                sections.append(section)

            section_map[section_title]['questions'].append({
                'id': f'q-{row_index}',
                'question': question,
            })

    return sections


def be360_questionnaire(request):
    sections = _load_be360_questionnaire()
    return render(request, "be360_questionnaire.html", {
        'sections': sections,
    })


@csrf_exempt
@require_POST
def send_be360_pdf(request):
    try:
        from weasyprint import HTML
    except ImportError:
        logger.error('weasyprint not installed — be360 PDF email skipped')
        return JsonResponse({'ok': False, 'error': 'PDF no disponible'}, status=500)

    try:
        data = json.loads(request.body)
        name = (data.get('name') or '').strip()
        sections = data.get('sections') or []
        if not isinstance(sections, list) or not sections:
            return JsonResponse({'ok': False, 'error': 'Sin respuestas que enviar'}, status=400)

        today = date.today().isoformat()
        html_str = render_to_string('be360_pdf.html', {
            'name': name or 'Sin nombre',
            'date': today,
            'sections': sections,
        })
        pdf_bytes = HTML(string=html_str, base_url=request.build_absolute_uri('/')).write_pdf()

        name_slug = slugify(name, allow_unicode=True) or 'sin-nombre'
        filename = f'Cuestionario-BE360_{name_slug}_{today}.pdf'

        email = EmailMessage(
            subject=f'📋 Cuestionario BE 360 completado — {name or "Sin nombre"}',
            body=f'Cuestionario BE 360 completado por: {name or "Sin nombre"}\nFecha: {today}\n\nPDF adjunto.',
            from_email='info@webimpulsa.es',
            to=[BE360_RECIPIENT],
        )
        email.attach(filename, pdf_bytes, 'application/pdf')
        email.send(fail_silently=False)

        return JsonResponse({'ok': True})
    except Exception as e:
        logger.error('be360 PDF email failed: %s', e, exc_info=True)
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)


def _wi_company_context():
    from crm.proposal_content import WI_COMPANY
    return {'company': WI_COMPANY}


def legal_notice(request):
    return render(request, "legal/aviso_legal.html", _wi_company_context())


def privacy_policy(request):
    return render(request, "legal/privacidad.html", _wi_company_context())


def cookies_policy(request):
    return render(request, "legal/cookies.html", _wi_company_context())


def terms_conditions(request):
    return render(request, "legal/terminos.html", _wi_company_context())


@csrf_exempt
@require_POST
def contact(request):
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        contact_info = data.get('contact', '').strip()
        biz_type = data.get('bizType', '').strip()
        message = data.get('message', '').strip()

        if not name or not contact_info:
            return JsonResponse({'ok': False, 'error': 'Nombre y contacto son obligatorios'})

        subject = f'📨 Nuevo contacto — {name} ({biz_type or "negocio"}) — webimpulsa.es'
        body = (
            f"Nombre: {name}\n"
            f"Contacto: {contact_info}\n"
            f"Tipo de negocio: {biz_type or '—'}\n\n"
            f"Mensaje:\n{message or '(sin mensaje)'}"
        )

        send_mail(
            subject=subject,
            message=body,
            from_email='info@webimpulsa.es',
            recipient_list=['info@webimpulsa.es'],
            fail_silently=False,
        )
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)
