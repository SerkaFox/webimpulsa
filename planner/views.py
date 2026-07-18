import calendar as cal_module
import json
from datetime import date

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_GET

from django.utils import timezone

from .models import TaskCatalogItem, CalendarEntry, TaskReport, Girl, AdminSettings, GirlMessage, GeneralMessage
from .report_fields import REPORT_FIELDS, CATEGORY_LABELS
from .guidance import CATEGORY_GUIDANCE, TASK_GUIDANCE
from .holidays import holidays_for_year

MANIFEST_JSON = """{
  "name": "Calendario BE Success",
  "short_name": "BE Success",
  "start_url": "/calendario/",
  "scope": "/calendario/",
  "display": "standalone",
  "background_color": "#fff6f0",
  "theme_color": "#2563eb",
  "icons": [
    {"src": "/static/wi/img/be-icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/static/wi/img/be-icon-512.png", "sizes": "512x512", "type": "image/png"}
  ]
}"""

SERVICE_WORKER_JS = """
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', (e) => { e.respondWith(fetch(e.request)); });
"""


def manifest_view(request):
    return HttpResponse(MANIFEST_JSON, content_type='application/manifest+json')


def service_worker_view(request):
    return HttpResponse(SERVICE_WORKER_JS, content_type='application/javascript')


MONTH_NAMES_ES = [
    '', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
]

WEEKDAY_NAMES_ES = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']


def _parse_year_month(request):
    today = date.today()
    try:
        year = int(request.GET.get('year', today.year))
        month = int(request.GET.get('month', today.month))
    except (TypeError, ValueError):
        year, month = today.year, today.month
    if month < 1 or month > 12:
        month = today.month
    return year, month


def _authenticate(request):
    """Devuelve (role, girl) a partir del token en 'X-Auth-Token' o ?token=.
    role es 'admin', 'girl' o None; girl es la instancia Girl o None."""
    token = request.headers.get('X-Auth-Token') or request.GET.get('token')
    if not token:
        return None, None
    if token == settings.PLANNER_ADMIN_TOKEN:
        return 'admin', None
    girl = Girl.objects.filter(token=token).first()
    if girl:
        return 'girl', girl
    return None, None


def _resolve_girl_id(request, role, girl, data=None):
    """Para admin, el girl_id viene en la petición; para una alumna, es ella misma."""
    if role == 'girl':
        return girl.id
    raw = (data or {}).get('girl_id') if data is not None else request.GET.get('girl_id')
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _check_admin_password(raw_password):
    row = AdminSettings.objects.first()
    if row and row.password_hash:
        return row.check_password(raw_password)
    return raw_password == settings.PLANNER_ADMIN_PASSWORD


def calendar_view(request):
    year, month = _parse_year_month(request)
    catalog = list(
        TaskCatalogItem.objects.values('id', 'title', 'category', 'default_points')
        .order_by('category', 'order', 'title')
    )

    cal = cal_module.Calendar(firstweekday=0)
    weeks = [
        [{'date': d, 'in_month': d.month == month} for d in week]
        for week in cal.monthdatescalendar(year, month)
    ]

    prev_month = month - 1 or 12
    prev_year = year - 1 if month == 1 else year
    next_month = month + 1 if month < 12 else 1
    next_year = year + 1 if month == 12 else year

    holidays = {}
    for y in {prev_year, year, next_year}:
        for mmdd, (name, desc) in holidays_for_year(y).items():
            holidays[mmdd] = {'name': name, 'desc': desc}

    birthdays = {}
    for g in Girl.objects.exclude(birth_date__isnull=True):
        mmdd = g.birth_date.strftime('%m-%d')
        birthdays.setdefault(mmdd, []).append(g.name)

    return render(request, 'planner/calendar.html', {
        'year': year,
        'month': month,
        'month_name': MONTH_NAMES_ES[month],
        'weekday_names': WEEKDAY_NAMES_ES,
        'weeks': weeks,
        'prev_year': prev_year,
        'prev_month': prev_month,
        'next_year': next_year,
        'next_month': next_month,
        'today_str': date.today().isoformat(),
        'catalog_json': catalog,
        'category_labels_json': CATEGORY_LABELS,
        'report_fields_json': REPORT_FIELDS,
        'category_guidance_json': CATEGORY_GUIDANCE,
        'task_guidance_json': TASK_GUIDANCE,
        'holidays_json': holidays,
        'birthdays_json': birthdays,
    })


@csrf_exempt
@require_http_methods(['POST'])
def api_login(request):
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    role = data.get('role')

    if role == 'admin':
        if _check_admin_password(data.get('password') or ''):
            return JsonResponse({'ok': True, 'role': 'admin', 'token': settings.PLANNER_ADMIN_TOKEN, 'name': 'Katerina'})
        return JsonResponse({'ok': False, 'error': 'Contraseña incorrecta'}, status=401)

    if role == 'girl':
        name = (data.get('name') or '').strip()
        girl = Girl.objects.filter(name__iexact=name).first()
        if not girl or not girl.check_password(data.get('password') or ''):
            return JsonResponse({'ok': False, 'error': 'Nombre o contraseña incorrectos'}, status=401)
        return JsonResponse({
            'ok': True, 'role': 'girl', 'token': girl.token, 'girl_id': girl.id, 'name': girl.name,
            'avatar_url': girl.avatar.url if girl.avatar else None,
        })

    return JsonResponse({'ok': False, 'error': 'Rol inválido'}, status=400)


@require_GET
def api_girls(request):
    role, _ = _authenticate(request)
    if role != 'admin':
        return JsonResponse({'ok': False, 'error': 'Solo para la administradora'}, status=403)
    girls = [
        {
            'id': g.id, 'name': g.name, 'avatar_url': g.avatar.url if g.avatar else None,
            'birth_date': g.birth_date.isoformat() if g.birth_date else None,
        }
        for g in Girl.objects.order_by('name')
    ]
    return JsonResponse({'ok': True, 'girls': girls})


@csrf_exempt
@require_http_methods(['POST'])
def api_girl_avatar(request, pk):
    role, _ = _authenticate(request)
    if role != 'admin':
        return JsonResponse({'ok': False, 'error': 'Solo para la administradora'}, status=403)
    girl = get_object_or_404(Girl, pk=pk)
    file = request.FILES.get('avatar')
    if not file:
        return JsonResponse({'ok': False, 'error': 'Falta la imagen'}, status=400)
    girl.avatar = file
    girl.save(update_fields=['avatar'])
    return JsonResponse({'ok': True, 'avatar_url': girl.avatar.url})


@csrf_exempt
@require_http_methods(['POST'])
def api_girl_create(request):
    role, _ = _authenticate(request)
    if role != 'admin':
        return JsonResponse({'ok': False, 'error': 'Solo para la administradora'}, status=403)
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    name = (data.get('name') or '').strip()
    password = data.get('password') or ''
    if not name or not password:
        return JsonResponse({'ok': False, 'error': 'Nombre y contraseña son obligatorios'}, status=400)
    if Girl.objects.filter(name__iexact=name).exists():
        return JsonResponse({'ok': False, 'error': 'Ya existe una alumna con ese nombre'}, status=400)

    girl = Girl(name=name)
    girl.set_password(password)
    girl.save()
    return JsonResponse({'ok': True, 'id': girl.id, 'name': girl.name})


@csrf_exempt
@require_http_methods(['POST'])
def api_girl_reset_password(request, pk):
    role, _ = _authenticate(request)
    if role != 'admin':
        return JsonResponse({'ok': False, 'error': 'Solo para la administradora'}, status=403)
    girl = get_object_or_404(Girl, pk=pk)
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)
    password = data.get('password') or ''
    if not password:
        return JsonResponse({'ok': False, 'error': 'Falta la contraseña'}, status=400)
    girl.set_password(password)
    girl.save(update_fields=['password'])
    return JsonResponse({'ok': True})


@csrf_exempt
@require_http_methods(['POST'])
def api_admin_change_password(request):
    role, _ = _authenticate(request)
    if role != 'admin':
        return JsonResponse({'ok': False, 'error': 'Solo para la administradora'}, status=403)
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    current = data.get('current_password') or ''
    new = data.get('new_password') or ''
    if not _check_admin_password(current):
        return JsonResponse({'ok': False, 'error': 'Contraseña actual incorrecta'}, status=401)
    if not new:
        return JsonResponse({'ok': False, 'error': 'Falta la nueva contraseña'}, status=400)

    row, _ = AdminSettings.objects.get_or_create(pk=1)
    row.set_password(new)
    row.save()
    return JsonResponse({'ok': True})


@require_GET
def api_entries(request):
    role, girl = _authenticate(request)
    if not role:
        return JsonResponse({'ok': False, 'error': 'No autenticado'}, status=401)

    girl_id = _resolve_girl_id(request, role, girl)
    if not girl_id:
        return JsonResponse({'ok': False, 'error': 'Falta girl_id'}, status=400)

    year, month = _parse_year_month(request)
    qs = (
        CalendarEntry.objects.filter(girl_id=girl_id, date__year=year, date__month=month)
        .select_related('catalog_item', 'report')
    )
    data = []
    for e in qs:
        data.append({
            'id': e.id,
            'date': e.date.isoformat(),
            'title': e.title,
            'category': e.category or (e.catalog_item.category if e.catalog_item else ''),
            'points': e.points,
            'completed': e.completed,
            'has_report': hasattr(e, 'report'),
        })
    return JsonResponse({'ok': True, 'entries': data})


@csrf_exempt
@require_http_methods(['POST'])
def api_entry_add(request):
    role, girl = _authenticate(request)
    if role != 'admin':
        return JsonResponse({'ok': False, 'error': 'Solo la administradora puede añadir tareas'}, status=403)

    try:
        data = json.loads(request.body)
        entry_date = date.fromisoformat(data['date'])
    except (KeyError, ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'Fecha inválida'}, status=400)

    girl_id = _resolve_girl_id(request, role, girl, data)
    if not girl_id or not Girl.objects.filter(pk=girl_id).exists():
        return JsonResponse({'ok': False, 'error': 'Alumna no encontrada'}, status=400)

    catalog_item_id = data.get('catalog_item_id')
    custom_title = (data.get('custom_title') or '').strip()
    category = (data.get('category') or '').strip()

    if catalog_item_id:
        catalog_item = TaskCatalogItem.objects.filter(pk=catalog_item_id).first()
        if not catalog_item:
            return JsonResponse({'ok': False, 'error': 'Elemento no encontrado'}, status=400)
        category = catalog_item.category
        points = int(data.get('points', catalog_item.default_points) or 0)
    elif custom_title:
        if category not in dict(TaskCatalogItem.CATEGORY_CHOICES):
            return JsonResponse({'ok': False, 'error': 'Selecciona una categoría'}, status=400)
        points = int(data.get('points') or 0)
        catalog_item, _ = TaskCatalogItem.objects.get_or_create(
            title=custom_title, defaults={'category': category, 'default_points': points}
        )
    else:
        return JsonResponse({'ok': False, 'error': 'Selecciona o escribe una tarea'}, status=400)

    entry = CalendarEntry.objects.create(
        girl_id=girl_id,
        date=entry_date,
        catalog_item=catalog_item,
        category=category,
        points=points,
    )
    return JsonResponse({'ok': True, 'id': entry.id})


@csrf_exempt
@require_http_methods(['POST'])
def api_entry_toggle(request, pk):
    role, girl = _authenticate(request)
    if not role:
        return JsonResponse({'ok': False, 'error': 'No autenticado'}, status=401)
    entry = get_object_or_404(CalendarEntry, pk=pk)
    if role == 'girl' and entry.girl_id != girl.id:
        return JsonResponse({'ok': False, 'error': 'No autorizado'}, status=403)

    entry.completed = not entry.completed
    entry.save(update_fields=['completed'])
    return JsonResponse({'ok': True, 'completed': entry.completed})


@csrf_exempt
@require_http_methods(['POST'])
def api_entry_delete(request, pk):
    role, _ = _authenticate(request)
    if role != 'admin':
        return JsonResponse({'ok': False, 'error': 'Solo la administradora puede eliminar tareas'}, status=403)
    entry = get_object_or_404(CalendarEntry, pk=pk)
    entry.delete()
    return JsonResponse({'ok': True})


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def api_entry_report(request, pk):
    role, girl = _authenticate(request)
    if not role:
        return JsonResponse({'ok': False, 'error': 'No autenticado'}, status=401)
    entry = get_object_or_404(CalendarEntry, pk=pk)
    if role == 'girl' and entry.girl_id != girl.id:
        return JsonResponse({'ok': False, 'error': 'No autorizado'}, status=403)

    if request.method == 'GET':
        report = getattr(entry, 'report', None)
        return JsonResponse({
            'ok': True,
            'category': entry.category,
            'fields': REPORT_FIELDS.get(entry.category, []),
            'data': report.data if report else {},
        })

    try:
        payload = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    report, _ = TaskReport.objects.get_or_create(entry=entry, defaults={'category': entry.category})
    report.category = entry.category
    report.data = payload.get('data') or {}
    report.save()
    entry.completed = True
    entry.save(update_fields=['completed'])
    return JsonResponse({'ok': True})


LEVELS = [
    {'points': 300, 'label': 'Explorer'},
    {'points': 600, 'label': 'Builder'},
    {'points': 900, 'label': 'Accelerator'},
    {'points': 1200, 'label': 'Leader'},
    {'points': 1500, 'label': 'Impact Maker'},
]

BONUS_RULES = [
    {'text': 'Conseguir un cliente', 'points': 100},
    {'text': 'Cerrar proyecto grande', 'points': 150},
    {'text': 'Colaboración estratégica', 'points': 80},
    {'text': 'Publicar 10 contenidos', 'points': 50},
    {'text': 'Leer un libro', 'points': 50},
    {'text': 'Completar todas las tareas de una semana', 'points': 100},
]


def _profile_payload(girl, year, month):
    entries = list(CalendarEntry.objects.filter(girl=girl, date__year=year, date__month=month))
    month_total = sum(e.points for e in entries)
    month_done = sum(e.points for e in entries if e.completed)

    weekly = {}
    for e in entries:
        wk = e.date.isocalendar()[1]
        w = weekly.setdefault(wk, {'week': wk, 'done': 0, 'total': 0})
        w['total'] += e.points
        if e.completed:
            w['done'] += e.points
    weekly_list = [weekly[k] for k in sorted(weekly.keys())]

    messages = [
        {'id': m.id, 'text': m.text, 'read': m.read, 'created_at': m.created_at.isoformat()}
        for m in girl.messages.all()[:30]
    ]
    unread_count = girl.messages.filter(read=False).count()

    return {
        'monthly_goal': girl.monthly_goal,
        'points_target': girl.points_target,
        'motto': girl.motto,
        'month_done': month_done,
        'month_total': month_total,
        'weekly': weekly_list,
        'messages': messages,
        'unread_count': unread_count,
        'levels': LEVELS,
        'bonus_rules': BONUS_RULES,
    }


@require_GET
def api_girl_profile(request):
    role, girl = _authenticate(request)
    if not role:
        return JsonResponse({'ok': False, 'error': 'No autenticado'}, status=401)
    girl_id = _resolve_girl_id(request, role, girl)
    if not girl_id:
        return JsonResponse({'ok': False, 'error': 'Falta girl_id'}, status=400)
    target_girl = get_object_or_404(Girl, pk=girl_id)
    year, month = _parse_year_month(request)
    return JsonResponse({'ok': True, **_profile_payload(target_girl, year, month)})


@csrf_exempt
@require_http_methods(['POST'])
def api_girl_profile_update(request, pk):
    role, _ = _authenticate(request)
    if role != 'admin':
        return JsonResponse({'ok': False, 'error': 'Solo para la administradora'}, status=403)
    girl = get_object_or_404(Girl, pk=pk)
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    if 'monthly_goal' in data:
        girl.monthly_goal = (data.get('monthly_goal') or '').strip()[:300]
    if 'motto' in data:
        girl.motto = (data.get('motto') or '').strip()[:300]
    if 'points_target' in data:
        try:
            girl.points_target = max(0, int(data.get('points_target') or 0))
        except (TypeError, ValueError):
            return JsonResponse({'ok': False, 'error': 'Objetivo BE inválido'}, status=400)
    if 'birth_date' in data:
        raw = (data.get('birth_date') or '').strip()
        if not raw:
            girl.birth_date = None
        else:
            try:
                girl.birth_date = date.fromisoformat(raw)
            except ValueError:
                return JsonResponse({'ok': False, 'error': 'Fecha de nacimiento inválida (usa AAAA-MM-DD)'}, status=400)
    girl.save()
    return JsonResponse({'ok': True})


@csrf_exempt
@require_http_methods(['POST'])
def api_girl_message_add(request, pk):
    role, _ = _authenticate(request)
    if role != 'admin':
        return JsonResponse({'ok': False, 'error': 'Solo para la administradora'}, status=403)
    girl = get_object_or_404(Girl, pk=pk)
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)
    text = (data.get('text') or '').strip()
    if not text:
        return JsonResponse({'ok': False, 'error': 'Mensaje vacío'}, status=400)
    GirlMessage.objects.create(girl=girl, text=text)
    return JsonResponse({'ok': True})


@csrf_exempt
@require_http_methods(['POST'])
def api_girl_messages_read(request):
    role, girl = _authenticate(request)
    if not role:
        return JsonResponse({'ok': False, 'error': 'No autenticado'}, status=401)
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        data = {}
    girl_id = _resolve_girl_id(request, role, girl, data)
    if not girl_id:
        return JsonResponse({'ok': False, 'error': 'Falta girl_id'}, status=400)
    GirlMessage.objects.filter(girl_id=girl_id, read=False).update(read=True)
    return JsonResponse({'ok': True})


# ── Minichat (bidireccional, con respuestas y reacciones) ──

def _serialize_chat_message(m):
    return {
        'id': m.id,
        'sender': m.sender,
        'text': m.text,
        'reaction': m.reaction,
        'reply_to': m.reply_to_id,
        'reply_to_text': m.reply_to.text if m.reply_to_id else None,
        'read': m.read,
        'created_at': m.created_at.isoformat(),
    }


@require_GET
def api_chat_messages(request):
    role, girl = _authenticate(request)
    if not role:
        return JsonResponse({'ok': False, 'error': 'No autenticado'}, status=401)
    girl_id = _resolve_girl_id(request, role, girl)
    if not girl_id:
        return JsonResponse({'ok': False, 'error': 'Falta girl_id'}, status=400)

    other_sender = 'girl' if role == 'admin' else 'admin'
    unread_count = GirlMessage.objects.filter(girl_id=girl_id, sender=other_sender, read=False).count()
    msgs = GirlMessage.objects.filter(girl_id=girl_id).select_related('reply_to').order_by('created_at')[:200]
    return JsonResponse({'ok': True, 'messages': [_serialize_chat_message(m) for m in msgs], 'unread_count': unread_count})


@csrf_exempt
@require_http_methods(['POST'])
def api_chat_send(request):
    role, girl = _authenticate(request)
    if not role:
        return JsonResponse({'ok': False, 'error': 'No autenticado'}, status=401)
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    girl_id = _resolve_girl_id(request, role, girl, data)
    if not girl_id:
        return JsonResponse({'ok': False, 'error': 'Falta girl_id'}, status=400)
    text = (data.get('text') or '').strip()
    if not text:
        return JsonResponse({'ok': False, 'error': 'Mensaje vacío'}, status=400)

    reply_to = None
    reply_to_id = data.get('reply_to')
    if reply_to_id:
        reply_to = GirlMessage.objects.filter(pk=reply_to_id, girl_id=girl_id).first()

    msg = GirlMessage.objects.create(
        girl_id=girl_id,
        sender='admin' if role == 'admin' else 'girl',
        text=text[:2000],
        reply_to=reply_to,
    )
    return JsonResponse({'ok': True, 'message': _serialize_chat_message(msg)})


@csrf_exempt
@require_http_methods(['POST'])
def api_chat_react(request, pk):
    role, girl = _authenticate(request)
    if not role:
        return JsonResponse({'ok': False, 'error': 'No autenticado'}, status=401)
    msg = get_object_or_404(GirlMessage, pk=pk)
    if role == 'girl' and msg.girl_id != girl.id:
        return JsonResponse({'ok': False, 'error': 'No autorizado'}, status=403)
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    emoji = (data.get('emoji') or '').strip()
    msg.reaction = '' if msg.reaction == emoji else emoji
    msg.save(update_fields=['reaction'])
    return JsonResponse({'ok': True, 'reaction': msg.reaction})


@csrf_exempt
@require_http_methods(['POST'])
def api_chat_read(request):
    role, girl = _authenticate(request)
    if not role:
        return JsonResponse({'ok': False, 'error': 'No autenticado'}, status=401)
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        data = {}
    girl_id = _resolve_girl_id(request, role, girl, data)
    if not girl_id:
        return JsonResponse({'ok': False, 'error': 'Falta girl_id'}, status=400)
    other_sender = 'girl' if role == 'admin' else 'admin'
    GirlMessage.objects.filter(girl_id=girl_id, sender=other_sender, read=False).update(read=True)
    return JsonResponse({'ok': True})


# ── Canal general (grupal: Katerina + todas las alumnas) ──

def _serialize_general_message(m, viewer_role, viewer_girl):
    is_mine = (
        (viewer_role == 'admin' and m.sender_type == 'admin')
        or (viewer_role == 'girl' and m.sender_type == 'girl' and m.sender_girl_id == viewer_girl.id)
    )
    return {
        'id': m.id,
        'sender_type': m.sender_type,
        'sender_name': m.sender_name,
        'mine': is_mine,
        'text': m.text,
        'reaction': m.reaction,
        'reply_to': m.reply_to_id,
        'reply_to_text': m.reply_to.text if m.reply_to_id else None,
        'reply_to_name': m.reply_to.sender_name if m.reply_to_id else None,
        'created_at': m.created_at.isoformat(),
    }


@require_GET
def api_general_chat_messages(request):
    role, girl = _authenticate(request)
    if not role:
        return JsonResponse({'ok': False, 'error': 'No autenticado'}, status=401)

    if role == 'admin':
        settings_row = AdminSettings.objects.first()
        last_read = settings_row.general_chat_read_at if settings_row else None
        unread_count = GeneralMessage.objects.filter(created_at__gt=last_read).exclude(sender_type='admin').count() if last_read \
            else GeneralMessage.objects.exclude(sender_type='admin').count()
    else:
        last_read = girl.general_chat_read_at
        qs = GeneralMessage.objects.exclude(sender_type='girl', sender_girl_id=girl.id)
        unread_count = qs.filter(created_at__gt=last_read).count() if last_read else qs.count()

    msgs = GeneralMessage.objects.select_related('reply_to', 'sender_girl', 'reply_to__sender_girl').order_by('created_at')[:200]
    return JsonResponse({
        'ok': True,
        'messages': [_serialize_general_message(m, role, girl) for m in msgs],
        'unread_count': unread_count,
    })


@csrf_exempt
@require_http_methods(['POST'])
def api_general_chat_send(request):
    role, girl = _authenticate(request)
    if not role:
        return JsonResponse({'ok': False, 'error': 'No autenticado'}, status=401)
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    text = (data.get('text') or '').strip()
    if not text:
        return JsonResponse({'ok': False, 'error': 'Mensaje vacío'}, status=400)

    reply_to = None
    reply_to_id = data.get('reply_to')
    if reply_to_id:
        reply_to = GeneralMessage.objects.filter(pk=reply_to_id).first()

    msg = GeneralMessage.objects.create(
        sender_type='admin' if role == 'admin' else 'girl',
        sender_girl=None if role == 'admin' else girl,
        text=text[:2000],
        reply_to=reply_to,
    )
    return JsonResponse({'ok': True, 'message': _serialize_general_message(msg, role, girl)})


@csrf_exempt
@require_http_methods(['POST'])
def api_general_chat_react(request, pk):
    role, girl = _authenticate(request)
    if not role:
        return JsonResponse({'ok': False, 'error': 'No autenticado'}, status=401)
    msg = get_object_or_404(GeneralMessage, pk=pk)
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)
    emoji = (data.get('emoji') or '').strip()
    msg.reaction = '' if msg.reaction == emoji else emoji
    msg.save(update_fields=['reaction'])
    return JsonResponse({'ok': True, 'reaction': msg.reaction})


@csrf_exempt
@require_http_methods(['POST'])
def api_general_chat_read(request):
    role, girl = _authenticate(request)
    if not role:
        return JsonResponse({'ok': False, 'error': 'No autenticado'}, status=401)
    now = timezone.now()
    if role == 'admin':
        row, _ = AdminSettings.objects.get_or_create(pk=1)
        row.general_chat_read_at = now
        row.save(update_fields=['general_chat_read_at'])
    else:
        girl.general_chat_read_at = now
        girl.save(update_fields=['general_chat_read_at'])
    return JsonResponse({'ok': True})
