from django.urls import path
from . import views
from .views_chat import start_chat, send_message, poll_messages, lookup_session, wa_webhook, tg_webhook

urlpatterns = [
    path('', views.home, name='home'),
    path('contact/', views.contact, name='contact'),

    # Live chat API
    path('wi/chat/start/',  start_chat,    name='chat_start'),
    path('wi/chat/send/',   send_message,  name='chat_send'),
    path('wi/chat/poll/',   poll_messages,   name='chat_poll'),
    path('wi/chat/lookup/', lookup_session,  name='chat_lookup'),

    # WhatsApp webhook (Meta sends here)
    path('wi/wh/', wa_webhook, name='wa_webhook'),

    # Telegram webhook (bot sends here)
    path('wi/tg/', tg_webhook, name='tg_webhook'),
]
