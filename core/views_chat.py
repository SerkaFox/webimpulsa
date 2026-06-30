"""
Live chat backend for webimpulsa.es
Flow:
  visitor  → POST /wi/chat/start/   → creates ChatSession, notifies Tanya via WA
  visitor  → POST /wi/chat/send/    → saves ChatMessage, forwards to Tanya via WA
  visitor  → GET  /wi/chat/poll/    → returns new messages (operator replies)
  Tanya    → replies in WhatsApp    → GET/POST /wi/wh/ webhook → saves as operator message
"""
import json
import os
import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.dateparse import parse_datetime

from .models import ChatSession, ChatMessage
from . import wa_send

logger = logging.getLogger(__name__)

OPERATOR_PHONES  = [p.strip() for p in os.getenv("WI_OPERATOR_PHONE", "").split(",") if p.strip()]
WA_VERIFY_TOKEN  = os.getenv("WI_WA_VERIFY_TOKEN", "")
WA_PHONE_ID      = os.getenv("WI_WA_PHONE_NUMBER_ID", "")


# ── helpers ─────────────────────────────────────────────────────────────────

TEMPLATE_NAME = "nuevo_mensaje_webimpulsa"
TEMPLATE_LANG = "es"


def _send_to_all(phones: list, fn, *args, **kwargs):
    for phone in phones:
        try:
            fn(phone, *args, **kwargs)
        except Exception as e:
            logger.error("WA send to %s failed: %s", phone, e)


def _notify_operator(session: ChatSession, text: str, first: bool = False) -> None:
    if not OPERATOR_PHONES:
        return

    ticket_id = "WEB-" + session.session_id[:4].upper()
    short_text = text[:200] if text else "—"

    if first:
        components = [{
            "type": "body",
            "parameters": [
                {"type": "text", "text": ticket_id},
                {"type": "text", "text": "Visitante web"},
                {"type": "text", "text": short_text},
            ],
        }]
        template_ok = False
        for phone in OPERATOR_PHONES:
            try:
                wa_send.send_template(phone, TEMPLATE_NAME, TEMPLATE_LANG, components)
                template_ok = True
            except Exception as e:
                logger.error("WA template to %s failed: %s — falling back to text", phone, e)
                try:
                    wa_send.send_text(phone,
                        f"🌐 webimpulsa.es — nuevo chat [{ticket_id}]\n\n"
                        f"{short_text}\n\n"
                        f"_Responde aquí para contestar al visitante._")
                except Exception as e2:
                    logger.error("WA fallback to %s failed: %s", phone, e2)
    else:
        _send_to_all(OPERATOR_PHONES, wa_send.send_text,
                     f"💬 *Cliente [{ticket_id}]:* {text}")


def _messages_as_json(qs):
    out = []
    for m in qs.values("sender", "text", "created_at"):
        out.append({
            "sender":     m["sender"],
            "text":       m["text"],
            "created_at": m["created_at"].isoformat(),
        })
    return out


# ── visitor endpoints ────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def start_chat(request):
    """Create session + add system greeting + ping Tanya."""
    try:
        data         = json.loads(request.body or b"{}")
        session_id   = (data.get("session_id") or "").strip()
        trigger      = data.get("trigger", "timer")
        page_time    = int(data.get("page_time_sec", 0))
        first_msg    = (data.get("first_message") or "").strip()

        if not session_id:
            return JsonResponse({"ok": False, "error": "missing session_id"}, status=400)

        session, created = ChatSession.objects.get_or_create(
            session_id=session_id,
            defaults={"trigger": trigger, "page_time_sec": page_time},
        )

        if created:
            ChatMessage.objects.create(
                session=session,
                sender=ChatMessage.SYSTEM,
                text=(
                    "¡Hola! Somos el equipo de WebImpulsa. "
                    "¿Tienes alguna duda o quieres saber más sobre nuestros servicios? Escríbenos 😊"
                ),
            )
            intro = first_msg or f"Nuevo visitante — lleva {page_time}s leyendo la página."
            _notify_operator(session, intro, first=True)

        return JsonResponse({
            "ok":         True,
            "session_id": session.session_id,
            "short_id":   session.short_id,
            "messages":   _messages_as_json(session.messages.all()),
        })
    except Exception as e:
        logger.exception("start_chat: %s", e)
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@csrf_exempt
@require_POST
def send_message(request):
    """Visitor sends a message → save + forward to Tanya."""
    try:
        data       = json.loads(request.body or b"{}")
        session_id = (data.get("session_id") or "").strip()
        text       = (data.get("text") or "").strip()

        if not session_id or not text:
            return JsonResponse({"ok": False, "error": "missing session_id or text"}, status=400)

        try:
            session = ChatSession.objects.get(session_id=session_id)
        except ChatSession.DoesNotExist:
            return JsonResponse({"ok": False, "error": "session not found"}, status=404)

        msg = ChatMessage.objects.create(session=session, sender=ChatMessage.VISITOR, text=text)
        session.save()  # bump updated_at so webhook can find most-recent active session

        _notify_operator(session, text)

        return JsonResponse({"ok": True, "created_at": msg.created_at.isoformat()})
    except Exception as e:
        logger.exception("send_message: %s", e)
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


def poll_messages(request):
    """Return messages created after `after` ISO timestamp."""
    try:
        session_id = (request.GET.get("sid") or "").strip()
        after_str  = (request.GET.get("after") or "").strip()

        if not session_id:
            return JsonResponse({"ok": False, "error": "missing sid"}, status=400)

        try:
            session = ChatSession.objects.get(session_id=session_id)
        except ChatSession.DoesNotExist:
            return JsonResponse({"ok": False, "error": "session not found"}, status=404)

        qs = session.messages.all()
        if after_str:
            after_dt = parse_datetime(after_str)
            if after_dt:
                qs = qs.filter(created_at__gt=after_dt)

        return JsonResponse({
            "ok":        True,
            "short_id":  session.short_id,
            "messages":  _messages_as_json(qs),
            "is_active": session.is_active,
        })
    except Exception as e:
        logger.exception("poll_messages: %s", e)
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


def lookup_session(request):
    """Find a session by short_id and return its full data (cross-device restore)."""
    try:
        code = (request.GET.get("code") or "").strip().lstrip("#")
        if not code:
            return JsonResponse({"ok": False, "error": "missing code"}, status=400)
        try:
            session = ChatSession.objects.get(short_id=code)
        except ChatSession.DoesNotExist:
            return JsonResponse({"ok": False, "found": False})
        return JsonResponse({
            "ok":         True,
            "found":      True,
            "session_id": session.session_id,
            "short_id":   session.short_id,
            "messages":   _messages_as_json(session.messages.all()),
        })
    except Exception as e:
        logger.exception("lookup_session: %s", e)
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


# ── WhatsApp webhook ─────────────────────────────────────────────────────────

def _wa_verify(request):
    mode      = request.GET.get("hub.mode")
    token     = request.GET.get("hub.verify_token")
    challenge = request.GET.get("hub.challenge")
    if mode == "subscribe" and token == WA_VERIFY_TOKEN and challenge:
        return HttpResponse(challenge, status=200)
    return HttpResponse("Forbidden", status=403)


@csrf_exempt
def wa_webhook(request):
    """Meta WhatsApp Cloud API webhook — receive Tanya's replies."""
    if request.method == "GET":
        return _wa_verify(request)

    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return HttpResponse("Bad JSON", status=400)

    try:
        entry   = payload.get("entry", [])
        changes = entry[0].get("changes", []) if entry else []
        value   = changes[0].get("value", {}) if changes else {}

        # guard: only handle our phone number
        phone_id_in = (value.get("metadata") or {}).get("phone_number_id")
        if WA_PHONE_ID and phone_id_in and phone_id_in != WA_PHONE_ID:
            return JsonResponse({"ok": True, "note": "ignored other phone_id"})

        messages = value.get("messages", [])
        msg = messages[0] if messages else None
        if not msg:
            return JsonResponse({"ok": True, "note": "no message"})

        wa_from = msg.get("from", "")
        fr_clean = "".join(ch for ch in (wa_from or "") if ch.isdigit())
        ops_clean = ["".join(ch for ch in p if ch.isdigit()) for p in OPERATOR_PHONES]

        if not ops_clean or fr_clean not in ops_clean:
            logger.info("WA webhook: ignored non-operator from=%s", wa_from)
            return JsonResponse({"ok": True, "note": "not operator"})

        # extract text
        msg_type = msg.get("type", "")
        text = ""
        if msg_type == "text":
            text = (msg.get("text") or {}).get("body", "").strip()
        elif msg_type == "interactive":
            inter = msg.get("interactive") or {}
            if inter.get("type") == "button_reply":
                text = (inter.get("button_reply") or {}).get("title", "")
            elif inter.get("type") == "list_reply":
                text = (inter.get("list_reply") or {}).get("title", "")

        if not text:
            return JsonResponse({"ok": True, "note": "empty text"})

        # route to most recently active session
        session = ChatSession.objects.filter(is_active=True).order_by("-updated_at").first()
        if not session:
            logger.info("WA webhook: operator reply but no active chat session")
            return JsonResponse({"ok": True, "note": "no active session"})

        ChatMessage.objects.create(session=session, sender=ChatMessage.OPERATOR, text=text)
        session.save()
        logger.info("Operator reply saved → session %s", session.session_id[:8])

    except Exception as e:
        logger.exception("wa_webhook error: %s", e)

    return JsonResponse({"ok": True})  # always 200 to Meta
