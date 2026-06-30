import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.core.mail import send_mail


def home(request):
    return render(request, "tatiana.html")


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
