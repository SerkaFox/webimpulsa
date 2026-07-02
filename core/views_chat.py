"""
Live chat backend for webimpulsa.es

Flow:
  visitor  → POST /wi/chat/start/   → creates session, shows greeting (no WA template yet)
  visitor  → POST /wi/chat/send/    → saves message
                                       first message → sends WA template + Telegram notification
                                       subsequent   → sends WA plain text (if operator activated)
  visitor  → GET  /wi/chat/poll/    → returns new messages (operator replies)
  Tanya    → replies in WhatsApp    → webhook → first reply = activation (not shown to visitor),
                                       system resends visitor's first message; then normal routing
  Tanya/Sergey → reply in Telegram → webhook → saves as operator message, shown to visitor
"""
import json
import os
import logging
import requests

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.dateparse import parse_datetime

from .models import ChatSession, ChatMessage, WaMessageMap
from . import wa_send

logger = logging.getLogger(__name__)

OPERATOR_PHONES  = [p.strip() for p in os.getenv("WI_OPERATOR_PHONE", "").split(",") if p.strip()]
WA_VERIFY_TOKEN  = os.getenv("WI_WA_VERIFY_TOKEN", "")
WA_PHONE_ID      = os.getenv("WI_WA_PHONE_NUMBER_ID", "")

TG_TOKEN         = os.getenv("WI_TG_TOKEN", "")
TG_CHAT_ID       = os.getenv("WI_TG_CHAT_ID", "")

TEMPLATE_NAME = "nuevo_mensaje_webimpulsa"
TEMPLATE_LANG = "es_ES"


# ── helpers ─────────────────────────────────────────────────────────────────

def _store_wamid(result: dict, session: ChatSession) -> None:
    try:
        wamid = (result.get("messages") or [{}])[0].get("id", "")
        if wamid:
            WaMessageMap.objects.get_or_create(wamid=wamid, defaults={"session": session})
    except Exception as e:
        logger.warning("Could not store wamid: %s", e)


def _send_wa_template(session: ChatSession, visitor_text: str) -> None:
    """Send WA template to all operators — called once on first visitor message."""
    ticket_id = "WEB-" + session.short_id
    short_text = visitor_text[:200] if visitor_text else "—"
    components = [{
        "type": "body",
        "parameters": [
            {"type": "text", "text": ticket_id},
            {"type": "text", "text": "Visitante web"},
            {"type": "text", "text": short_text},
        ],
    }]
    for phone in OPERATOR_PHONES:
        try:
            result = wa_send.send_template(phone, TEMPLATE_NAME, TEMPLATE_LANG, components)
            _store_wamid(result, session)
        except Exception as e:
            logger.error("WA template to %s failed: %s — falling back", phone, e)
            try:
                result = wa_send.send_text(
                    phone,
                    f"🌐 webimpulsa.es — nuevo chat [{ticket_id}]\n\n"
                    f"{short_text}\n\n"
                    f"_Responde a ESTE mensaje para contestar al visitante._"
                )
                _store_wamid(result, session)
            except Exception as e2:
                logger.error("WA fallback to %s failed: %s", phone, e2)


def _send_wa_text(session: ChatSession, text: str) -> None:
    """Send plain text to all operators — only works after operator has activated (24h window)."""
    ticket_id = "WEB-" + session.short_id
    for phone in OPERATOR_PHONES:
        try:
            result = wa_send.send_text(phone, f"💬 *Chat {ticket_id}:* {text}")
            _store_wamid(result, session)
        except Exception as e:
            logger.error("WA send to %s failed: %s", phone, e)


def _send_tg(session: ChatSession, text: str, with_buttons: bool = False) -> None:
    """Send Telegram notification."""
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    ticket_id = "WEB-" + session.short_id
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload: dict = {
        "chat_id": TG_CHAT_ID,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "text": text,
    }
    if with_buttons:
        payload["reply_markup"] = {
            "inline_keyboard": [[
                {"text": "✅ Responder", "callback_data": f"chat_reply:{session.short_id}"},
                {"text": "❌ Ignorar",   "callback_data": f"chat_ignore:{session.short_id}"},
            ]]
        }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        logger.info("TG notification sent for chat #%s", ticket_id)
    except Exception as e:
        logger.error("TG send failed for chat #%s: %s", ticket_id, e)


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
    """Create session + show system greeting. WA/TG notifications sent on first real message."""
    try:
        data         = json.loads(request.body or b"{}")
        session_id   = (data.get("session_id") or "").strip()
        trigger      = data.get("trigger", "timer")
        page_time    = int(data.get("page_time_sec", 0))

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
    """Visitor sends a message → save + notify operators."""
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
        session.save()

        if not session.template_sent:
            # First real message — send WA template + Telegram notification
            _send_wa_template(session, text)
            _send_tg(
                session,
                f"💬 <b>Nuevo chat en webimpulsa.es</b>\n\n"
                f"🎫 Ticket: <b>WEB-{session.short_id}</b>\n"
                f"📝 Mensaje: <i>{text[:300]}</i>\n\n"
                f"Responde aquí para chatear con el visitante.",
                with_buttons=True,
            )
            session.template_sent = True
            session.save(update_fields=["template_sent"])
        elif session.operator_activated:
            # Operator already activated — send plain text via WA
            _send_wa_text(session, text)
            _send_tg(
                session,
                f"💬 <b>WEB-{session.short_id}:</b> {text[:300]}",
            )

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


def _route_session(msg: dict) -> ChatSession | None:
    """Find the session this operator reply belongs to."""
    context_wamid = (msg.get("context") or {}).get("id", "")
    if context_wamid:
        mapping = WaMessageMap.objects.filter(wamid=context_wamid).select_related("session").first()
        if mapping:
            logger.info("Routed by context wamid → session #%s", mapping.session.short_id)
            return mapping.session
    session = ChatSession.objects.filter(is_active=True).order_by("-updated_at").first()
    if session:
        logger.info("Routed by fallback (most recent) → session #%s", session.short_id)
    return session


@csrf_exempt
def wa_webhook(request):
    """Meta WhatsApp Cloud API webhook — receive operator replies."""
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

        session = _route_session(msg)
        if not session:
            logger.info("WA webhook: operator reply but no active session")
            return JsonResponse({"ok": True, "note": "no active session"})

        if not session.operator_activated:
            # First operator reply = activation. Don't show to visitor.
            # Mark activated and resend the visitor's first real message.
            session.operator_activated = True
            session.save(update_fields=["operator_activated"])
            logger.info("Operator activated session #%s", session.short_id)

            first_visitor_msg = (
                session.messages
                .filter(sender=ChatMessage.VISITOR)
                .order_by("created_at")
                .first()
            )
            if first_visitor_msg:
                _send_wa_text(session, first_visitor_msg.text)
                logger.info("Resent first visitor message to operators for session #%s", session.short_id)
        else:
            # Normal reply — save and show to visitor
            ChatMessage.objects.create(session=session, sender=ChatMessage.OPERATOR, text=text)
            session.save()
            logger.info("Operator reply saved → chat #%s", session.short_id)

    except Exception as e:
        logger.exception("wa_webhook error: %s", e)

    return JsonResponse({"ok": True})


# ── Telegram webhook ─────────────────────────────────────────────────────────

@csrf_exempt
def tg_webhook(request):
    """Telegram bot webhook — receive operator replies from Telegram."""
    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return HttpResponse("Bad JSON", status=400)

    try:
        # Handle inline button callbacks (✅ Responder / ❌ Ignorar)
        callback = payload.get("callback_query")
        if callback:
            data     = (callback.get("data") or "")
            tg_from  = str((callback.get("from") or {}).get("id", ""))
            if tg_from != str(TG_CHAT_ID):
                return JsonResponse({"ok": True})

            if data.startswith("chat_reply:"):
                short_id = data.split(":", 1)[1]
                try:
                    session = ChatSession.objects.get(short_id=short_id)
                    # Send all buffered visitor messages to Telegram
                    msgs = session.messages.filter(sender=ChatMessage.VISITOR).order_by("created_at")
                    lines = [f"📋 <b>WEB-{short_id} — mensajes del visitante:</b>"]
                    for m in msgs:
                        lines.append(f"• {m.text[:200]}")
                    _send_tg(session, "\n".join(lines))
                except ChatSession.DoesNotExist:
                    pass
            # Answer callback to remove spinner
            _tg_answer_callback(callback.get("id"))
            return JsonResponse({"ok": True})

        # Handle plain text reply
        message  = payload.get("message") or {}
        tg_from  = str((message.get("from") or {}).get("id", ""))
        if tg_from != str(TG_CHAT_ID):
            return JsonResponse({"ok": True})

        text = (message.get("text") or "").strip()
        if not text or text.startswith("/"):
            return JsonResponse({"ok": True})

        # Route to most recent active session
        session = ChatSession.objects.filter(is_active=True).order_by("-updated_at").first()
        if not session:
            return JsonResponse({"ok": True})

        ChatMessage.objects.create(session=session, sender=ChatMessage.OPERATOR, text=text)
        session.save()
        logger.info("TG operator reply saved → chat #%s", session.short_id)

    except Exception as e:
        logger.exception("tg_webhook error: %s", e)

    return JsonResponse({"ok": True})


def _tg_answer_callback(callback_id: str) -> None:
    if not TG_TOKEN or not callback_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/answerCallbackQuery",
            json={"callback_query_id": callback_id},
            timeout=5,
        )
    except Exception:
        pass
