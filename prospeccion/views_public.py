import hashlib
import json
import logging

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import BusinessProspect, ChequeoAudit, SECTOR_CHOICES
from .quiz_config import ANSWER_OPTIONS, CATEGORY_LABELS, QUESTIONNAIRE_VERSION, QUESTIONS
from .scoring import compute_score, questions_for_sector

logger = logging.getLogger(__name__)

_VALID_SECTORS = {s[0] for s in SECTOR_CHOICES}
_VALID_VALUES = {'si', 'en_parte', 'no_se', 'no', 'no_aplica'}

RATE_LIMIT_MAX_PER_HOUR = 20


def _same_origin(request):
    """Defensa adicional para los endpoints que cambian estado: no hay
    CsrfViewMiddleware instalado en este proyecto (brecha preexistente, fuera
    de alcance de esta feature), así que se comprueba Origin/Referer contra
    el propio host como mitigación ligera solo para estas rutas nuevas."""
    host = request.get_host()
    origin = request.META.get('HTTP_ORIGIN', '')
    referer = request.META.get('HTTP_REFERER', '')
    if origin:
        return origin.endswith('://' + host) or origin.endswith('.' + host)
    if referer:
        return ('://' + host) in referer
    return True  # sin Origin ni Referer (ej. curl/apps nativas) — no bloquear


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _ip_hash(request):
    ip = _client_ip(request)
    return hashlib.sha256(ip.encode('utf-8')).hexdigest()


def _rate_limited(ip_hash):
    since = timezone.now() - timezone.timedelta(hours=1)
    return ChequeoAudit.objects.filter(ip_hash=ip_hash, created_at__gte=since).count() >= RATE_LIMIT_MAX_PER_HOUR


def _good_fix_progress(sector, result):
    """Traduce los ids devueltos por compute_score al texto real de cada
    pregunta (good/fix), para que el cliente no tenga que conocer el
    contenido del cuestionario."""
    by_id = {q['id']: q for q in QUESTIONS}

    def _items(ids, field):
        out = []
        for qid in ids:
            q = by_id.get(qid)
            if q:
                out.append({'id': qid, 'text': q[field]})
        return out

    return {
        'good': _items(result['good_ids'], 'good'),
        'fix': _items(result['fix_ids'], 'fix'),
        'en_progreso': _items(result['en_progreso_ids'], 'fix'),
    }


def _validate_answers(sector, answers):
    """Devuelve (answers_limpias, error). Solo acepta ids de pregunta reales
    del sector y valores del set permitido — nunca confía en lo que llega."""
    if not isinstance(answers, dict):
        return None, 'answers debe ser un objeto'
    valid_ids = {q['id'] for q in questions_for_sector(sector)}
    clean = {}
    for qid, val in answers.items():
        if qid not in valid_ids:
            continue
        if val not in _VALID_VALUES:
            return None, f'valor no válido para {qid}'
        clean[qid] = val
    return clean, None


@require_GET
def questionnaire_json(request, sector):
    if sector not in _VALID_SECTORS:
        return JsonResponse({'error': 'sector desconocido'}, status=404)
    return JsonResponse({
        'sector': sector,
        'version': QUESTIONNAIRE_VERSION,
        'questions': questions_for_sector(sector),
        'answer_options': ANSWER_OPTIONS,
    })


@csrf_exempt
@require_POST
def submit_public_audit(request):
    ip_hash = _ip_hash(request)
    if not _same_origin(request):
        return JsonResponse({'error': 'origen no permitido'}, status=403)
    if _rate_limited(ip_hash):
        return JsonResponse({'error': 'demasiados envíos, inténtalo más tarde'}, status=429)

    try:
        payload = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    sector = payload.get('sector')
    if sector not in _VALID_SECTORS:
        return JsonResponse({'error': 'sector desconocido'}, status=400)

    answers, err = _validate_answers(sector, payload.get('answers') or {})
    if err:
        return JsonResponse({'error': err}, status=400)

    result = compute_score(sector, answers)

    audit = ChequeoAudit.objects.create(
        prospect=None,
        mode=ChequeoAudit.MODE_PUBLIC,
        stage=ChequeoAudit.STAGE_CONFIRMADO,
        session_key=request.COOKIES.get('wi_chequeo_session', ''),
        sector=sector,
        questionnaire_version=QUESTIONNAIRE_VERSION,
        answers=[{'question_id': qid, 'value': val, 'source': 'respondent'} for qid, val in answers.items()],
        score=result['score'],
        category_scores=result['category_scores'],
        good_ids=result['good_ids'],
        fix_ids=result['fix_ids'],
        sector_benchmark=result['benchmark'],
        ip_hash=ip_hash,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
    )

    resp = JsonResponse({
        'score': result['score'],
        'category_scores': result['category_scores'],
        'category_labels': CATEGORY_LABELS,
        'benchmark': result['benchmark'],
        'stage': audit.stage,
        **_good_fix_progress(sector, result),
    })
    if not request.COOKIES.get('wi_chequeo_session'):
        resp.set_cookie('wi_chequeo_session', audit.session_key or _new_session_key(),
                         max_age=60 * 60 * 24 * 365, samesite='Lax')
    return resp


def _new_session_key():
    import secrets
    return secrets.token_urlsafe(24)


def personal_audit(request, token):
    prospect = get_object_or_404(BusinessProspect, public_token=token)
    latest_audit = prospect.audits.order_by('-created_at').first()
    prefill = {}
    if latest_audit:
        prefill = {a['question_id']: a for a in latest_audit.answers}

    context = {
        'mode': 'personal',
        'prospect_name': prospect.name,
        'sector': prospect.sector,
        'token': token,
        'prefill_json': json.dumps(prefill),
        'stage': latest_audit.stage if latest_audit else ChequeoAudit.STAGE_PRELIMINAR,
    }
    return render(request, 'chequeo_digital.html', context)


@csrf_exempt
@require_POST
def submit_personal_audit(request, token):
    if not _same_origin(request):
        return JsonResponse({'error': 'origen no permitido'}, status=403)

    prospect = get_object_or_404(BusinessProspect, public_token=token)

    try:
        payload = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    # el sector es el de la empresa, no algo que el respondente elija
    sector = prospect.sector
    answers, err = _validate_answers(sector, payload.get('answers') or {})
    if err:
        return JsonResponse({'error': err}, status=400)

    result = compute_score(sector, answers)

    audit = ChequeoAudit.objects.create(
        prospect=prospect,
        mode=ChequeoAudit.MODE_PERSONAL,
        stage=ChequeoAudit.STAGE_CONFIRMADO,
        sector=sector,
        questionnaire_version=QUESTIONNAIRE_VERSION,
        answers=[{'question_id': qid, 'value': val, 'source': 'respondent'} for qid, val in answers.items()],
        score=result['score'],
        category_scores=result['category_scores'],
        good_ids=result['good_ids'],
        fix_ids=result['fix_ids'],
        sector_benchmark=result['benchmark'],
        ip_hash=_ip_hash(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
    )

    # sincroniza los campos denormalizados del prospecto — mismo patrón que
    # crm/views_proposal.py sincroniza Proposal -> Lead al guardar.
    prospect.current_score = audit.score
    prospect.last_check_at = timezone.now()
    if prospect.sales_status in (prospect.SALES_DISCOVERED, prospect.SALES_PRE_AUDITED, prospect.SALES_CONTACTED):
        prospect.sales_status = prospect.SALES_AUDITED
    prospect.save(update_fields=['current_score', 'last_check_at', 'sales_status', 'updated_at'])

    return JsonResponse({
        'score': result['score'],
        'category_scores': result['category_scores'],
        'category_labels': CATEGORY_LABELS,
        'benchmark': result['benchmark'],
        'stage': audit.stage,
        **_good_fix_progress(sector, result),
    })
