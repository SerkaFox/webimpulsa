from django.urls import path
from . import views
from .views_chat import start_chat, send_message, poll_messages, lookup_session, wa_webhook, tg_webhook

urlpatterns = [
    path('', views.home, name='home'),
    path('chequeo-digital/', views.digital_checkup, name='digital_checkup'),
    path('cuestionario-be360/', views.be360_questionnaire, name='be360_questionnaire'),
    path('cuestionario-be360/enviar-pdf/', views.send_be360_pdf, name='be360_send_pdf'),
    path('tarjeta-ar/', views.ar_business_card, name='ar_business_card'),
    path('tarjeta-ar/api/message/', views.ar_chat_message, name='ar_chat_message'),
    path('tarjeta-ar/api/tts/', views.ar_chat_tts, name='ar_chat_tts'),
    path('tarjeta-ar/api/vision/', views.ar_chat_vision, name='ar_chat_vision'),
    path('robot-chat/', views.robot_chat, name='robot_chat'),
    path('robot-chat/api/message/', views.robot_chat_message, name='robot_chat_message'),
    path('contact/', views.contact, name='contact'),
    path('aviso-legal/', views.legal_notice, name='legal_notice'),
    path('privacidad/', views.privacy_policy, name='privacy_policy'),
    path('cookies/', views.cookies_policy, name='cookies_policy'),
    path('terminos/', views.terms_conditions, name='terms_conditions'),

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
