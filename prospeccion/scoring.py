"""
Motor de puntuación del chequeo digital. Todo el cálculo vive aquí y solo
aquí — el cliente nunca puntúa nada, solo envía respuestas y recibe el
resultado ya calculado.
"""

from .quiz_config import CATEGORY_WEIGHTS, COEFFICIENTS, QUESTIONS, SECTOR_BENCHMARKS

NO_APLICA = 'no_aplica'


def questions_for_sector(sector):
    """Preguntas aplicables a un sector, con el texto ya localizado.
    Una pregunta sin `applies_to` aplica a todos los sectores; si una pregunta
    no aplica a este sector, ni se devuelve ni entra nunca en compute_score."""
    out = []
    for q in QUESTIONS:
        applies = q.get('applies_to')
        if applies is not None and sector not in applies:
            continue
        text = q['text_by_sector'].get(sector, q['text_by_sector']['_default'])
        out.append({
            'id': q['id'],
            'category': q['category'],
            'text': text,
            'hint': q.get('hint', ''),
        })
    return out


def compute_score(sector, answers):
    """answers: {question_id: 'si'|'en_parte'|'no_se'|'no'|'no_aplica'}.
    Devuelve score 0-100, desglose por categoría, e ids de preguntas
    'good'/'fix'/'en_progreso' para el bloque de resultado."""
    applicable = questions_for_sector(sector)
    applicable_by_id = {q['id']: q for q in applicable}

    # solo cuentan las preguntas aplicables a este sector Y respondidas con
    # un valor distinto de 'no_aplica' — mismo mecanismo para ambos casos.
    scored_answers = {
        qid: val for qid, val in answers.items()
        if qid in applicable_by_id and val != NO_APLICA and val is not None
    }

    cat_possible = {c: 0.0 for c in CATEGORY_WEIGHTS}
    cat_earned = {c: 0.0 for c in CATEGORY_WEIGHTS}
    good_ids, fix_ids, en_progreso_ids = [], [], []

    # nº de preguntas puntuables por categoría (para repartir el peso nominal
    # de la categoría entre las preguntas realmente contestadas en ella).
    by_category = {}
    for qid, val in scored_answers.items():
        cat = applicable_by_id[qid]['category']
        by_category.setdefault(cat, []).append(qid)

    for cat, qids in by_category.items():
        per_q_weight = CATEGORY_WEIGHTS[cat] / len(qids)
        for qid in qids:
            coeff = COEFFICIENTS.get(scored_answers[qid], 0.0)
            cat_possible[cat] += per_q_weight
            cat_earned[cat] += per_q_weight * coeff
            if coeff >= 1.0:
                good_ids.append(qid)
            elif coeff == 0.0:
                fix_ids.append(qid)
            else:
                en_progreso_ids.append(qid)

    category_scores = {}
    total_score = 0.0
    for cat, weight in CATEGORY_WEIGHTS.items():
        possible = cat_possible[cat]
        # sin preguntas aplicables/contestadas en esta categoría -> no se
        # penaliza: se cuenta a puntaje pleno para esa categoría.
        cat_score = round((cat_earned[cat] / possible) * weight) if possible > 0 else weight
        category_scores[cat] = cat_score
        total_score += cat_score

    return {
        'score': round(total_score),
        'category_scores': category_scores,
        'good_ids': good_ids,
        'fix_ids': fix_ids,
        'en_progreso_ids': en_progreso_ids,
        'benchmark': SECTOR_BENCHMARKS.get(sector, 75),
    }
