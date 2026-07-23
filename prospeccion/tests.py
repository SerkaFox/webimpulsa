import json

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from crm.models import Lead, Proposal
from .csv_import import parse_csv
from .models import BusinessProspect, ChequeoAudit, StaffMember
from .quiz_config import CATEGORY_WEIGHTS
from .scoring import compute_score, questions_for_sector
from .services import compute_dedupe_key, convert_prospect_to_lead, create_prospect, find_duplicate


@override_settings(ALLOWED_HOSTS=['testserver'])
class BaseTestCase(TestCase):
    def login(self):
        import os
        c = Client()
        c.post('/panel/prospeccion/', {'crm_password': os.environ.get('WI_CRM_PASSWORD', '')})
        return c


class ScoringTests(TestCase):
    def test_category_weights_sum_to_100(self):
        self.assertEqual(sum(CATEGORY_WEIGHTS.values()), 100)

    def test_all_si_gives_100(self):
        qs = questions_for_sector('bar')
        answers = {q['id']: 'si' for q in qs}
        result = compute_score('bar', answers)
        self.assertEqual(result['score'], 100)
        for cat_score in result['category_scores'].values():
            self.assertGreaterEqual(cat_score, 0)

    def test_all_no_gives_0(self):
        qs = questions_for_sector('bar')
        answers = {q['id']: 'no' for q in qs}
        result = compute_score('bar', answers)
        self.assertEqual(result['score'], 0)

    def test_no_aplica_excluded_from_denominator(self):
        qs = questions_for_sector('bar')
        answers = {q['id']: 'si' for q in qs}
        # marcar la única pregunta de una categoría de peso 10 como no_aplica
        answers['reviews_uptodate'] = 'no_aplica'
        result = compute_score('bar', answers)
        # sin preguntas contestadas en 'confianza' -> categoria a puntaje pleno, no penaliza
        self.assertEqual(result['category_scores']['confianza'], CATEGORY_WEIGHTS['confianza'])
        self.assertEqual(result['score'], 100)

    def test_en_parte_is_half_credit(self):
        qs = questions_for_sector('bar')
        answers = {q['id']: 'si' for q in qs}
        answers['gbp_accuracy'] = 'en_parte'
        result = compute_score('bar', answers)
        self.assertLess(result['score'], 100)
        self.assertIn('gbp_accuracy', result['en_progreso_ids'])
        self.assertNotIn('gbp_accuracy', result['good_ids'])
        self.assertNotIn('gbp_accuracy', result['fix_ids'])

    def test_unanswered_question_excluded_like_no_aplica(self):
        qs = questions_for_sector('bar')
        answers = {q['id']: 'si' for q in qs}
        del answers['reviews_uptodate']
        result = compute_score('bar', answers)
        self.assertEqual(result['category_scores']['confianza'], CATEGORY_WEIGHTS['confianza'])


class AuditVersioningTests(TestCase):
    def test_new_audit_never_mutates_previous_one(self):
        prospect = BusinessProspect.objects.create(name='Versioning Co', sector='bar')
        first = ChequeoAudit.objects.create(
            prospect=prospect, mode='personal', stage='preliminar', sector='bar',
            questionnaire_version='v1', answers=[], score=40, category_scores={},
            good_ids=[], fix_ids=['gbp_accuracy'],
        )
        second = ChequeoAudit.objects.create(
            prospect=prospect, mode='personal', stage='confirmado', sector='bar',
            questionnaire_version='v1', answers=[], score=80, category_scores={},
            good_ids=['gbp_accuracy'], fix_ids=[],
        )
        first.refresh_from_db()
        self.assertEqual(first.score, 40)
        self.assertEqual(first.stage, 'preliminar')
        self.assertEqual(second.score, 80)
        self.assertEqual(prospect.audits.count(), 2)


class PublicTokenSecurityTests(BaseTestCase):
    def test_wrong_token_404s(self):
        c = Client()
        r = c.get('/chequeo-digital/e/not-a-real-token/')
        self.assertEqual(r.status_code, 404)

    def test_valid_token_200s_and_shows_no_internal_ids(self):
        prospect = BusinessProspect.objects.create(name='Token Co', sector='bar')
        c = Client()
        r = c.get(f'/chequeo-digital/e/{prospect.public_token}/')
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn(prospect.public_token, html)
        # el pk interno no debe aparecer en ningún atributo/URL del HTML
        self.assertNotIn(f'/{prospect.pk}/', html)
        self.assertNotIn(f'"id":{prospect.pk}', html.replace(' ', ''))

    def test_submit_requires_matching_sector_questions_only(self):
        prospect = BusinessProspect.objects.create(name='Sector Co', sector='taller')
        c = Client()
        r = c.post(f'/chequeo-digital/e/{prospect.public_token}/api/submit/',
                   data=json.dumps({'answers': {'gbp_accuracy': 'si'}}), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        prospect.refresh_from_db()
        self.assertIsNotNone(prospect.current_score)


class PublicMapPrivacyTests(BaseTestCase):
    def test_only_consented_and_confirmed_prospects_appear(self):
        p_no_consent = BusinessProspect.objects.create(name='No Consent', sector='bar', lat=43.26, lng=-2.92)
        p_unconfirmed = BusinessProspect.objects.create(
            name='Unconfirmed', sector='bar', lat=43.27, lng=-2.93, publish_consent=True)
        p_revoked = BusinessProspect.objects.create(
            name='Revoked', sector='bar', lat=43.28, lng=-2.94,
            publish_consent=True, publish_confirmed_by_staff=True, publish_revoked_at=timezone.now())
        p_ok = BusinessProspect.objects.create(
            name='Published Co', sector='bar', lat=43.29, lng=-2.95,
            phone='611000000', publish_consent=True, publish_confirmed_by_staff=True)

        c = Client()
        r = c.get('/mapa-digital/api/prospects/', {'south': 43.0, 'north': 43.5, 'west': -3.2, 'east': -2.7})
        data = json.loads(r.content)
        names = {p['name'] for p in data['prospects']}
        self.assertEqual(names, {'Published Co'})
        for p in data['prospects']:
            self.assertNotIn('phone', p)
            self.assertNotIn('staff_notes', p)
            self.assertNotIn('sales_status', p)
            self.assertNotIn('id', p)


class PanelAuthTests(TestCase):
    """Cada ruta /panel/prospeccion/* debe exigir la sesión CRM."""

    def test_all_panel_routes_require_login(self):
        prospect = BusinessProspect.objects.create(name='Auth Co', sector='bar')
        routes = [
            ('GET', '/panel/prospeccion/'),
            ('GET', '/panel/prospeccion/mapa/'),
            ('GET', '/panel/prospeccion/mapa/api/prospects/'),
            ('GET', f'/panel/prospeccion/{prospect.pk}/'),
            ('GET', f'/panel/prospeccion/{prospect.pk}/pdf/'),
        ]
        with override_settings(ALLOWED_HOSTS=['testserver']):
            c = Client()
            for method, url in routes:
                r = c.get(url) if method == 'GET' else c.post(url)
                self.assertIn('Web-Impulsa CRM', r.content.decode(), msg=f'{url} no pidió login')


class DedupeTests(TestCase):
    def test_exact_duplicate_by_phone_is_detected(self):
        create_prospect({'name': 'Panadería Uno', 'phone': '600111222'})
        dup = find_duplicate('Panadería Uno (otro nombre)', phone='600111222')
        self.assertIsNotNone(dup)

    def test_different_business_is_not_a_duplicate(self):
        create_prospect({'name': 'Panadería Uno', 'phone': '600111222'})
        dup = find_duplicate('Ferretería Dos', phone='600999888')
        self.assertIsNone(dup)

    def test_create_prospect_does_not_duplicate(self):
        p1, created1 = create_prospect({'name': 'Taller X', 'phone': '611222333'})
        p2, created2 = create_prospect({'name': 'Taller X', 'phone': '611222333'})
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(p1.pk, p2.pk)
        self.assertEqual(BusinessProspect.objects.count(), 1)

    def test_same_name_close_coordinates_is_duplicate(self):
        create_prospect({'name': 'Bar Central', 'lat': 43.2600, 'lng': -2.9200})
        dup = find_duplicate('Bar Central', lat=43.2601, lng=-2.9201)
        self.assertIsNotNone(dup)

    def test_dedupe_key_is_stable(self):
        k1 = compute_dedupe_key('Nombre', phone='600111222')
        k2 = compute_dedupe_key('nombre', phone='600 111 222')
        self.assertEqual(k1, k2)


class ConversionTests(BaseTestCase):
    def test_convert_creates_lead_with_expected_package_and_extras(self):
        prospect = BusinessProspect.objects.create(name='Convert Co', sector='bar', phone='699000111')
        ChequeoAudit.objects.create(
            prospect=prospect, mode='personal', stage='confirmado', sector='bar',
            questionnaire_version='v1', answers=[], score=50, category_scores={},
            good_ids=[], fix_ids=['gbp_accuracy', 'one_tap_contact'],
        )
        lead, created = convert_prospect_to_lead(prospect)
        self.assertTrue(created)
        self.assertEqual(lead.source, Lead.SRC_MAPA_DIGITAL)
        self.assertIn('Ficha en Google Maps', lead.extras)
        self.assertIn('Botón de WhatsApp', lead.extras)
        prospect.refresh_from_db()
        self.assertEqual(prospect.converted_client_id, lead.pk)

    def test_converting_twice_reuses_same_lead(self):
        prospect = BusinessProspect.objects.create(name='Convert Twice', sector='taller', phone='699222333')
        lead1, created1 = convert_prospect_to_lead(prospect)
        lead2, created2 = convert_prospect_to_lead(prospect)
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(lead1.pk, lead2.pk)

    def test_draft_proposal_created_via_panel_view(self):
        prospect = BusinessProspect.objects.create(name='Proposal Co', sector='tienda', phone='699333444')
        c = self.login()
        r = c.post(f'/panel/prospeccion/{prospect.pk}/convert/', data='{}', content_type='application/json')
        self.assertEqual(r.status_code, 200)
        r = c.post(f'/panel/prospeccion/{prospect.pk}/draft-proposal/', data='{}', content_type='application/json')
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.content)
        proposal = Proposal.objects.get(pk=body['proposal_id'])
        self.assertEqual(proposal.status, Proposal.ST_DRAFT)
        self.assertGreater(proposal.total_with_iva, 0)


class CsvImportTests(TestCase):
    def test_parse_csv_flags_missing_coordinates_as_errors_not_crashes(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        content = b'name,sector,lat,lng\nCon Coordenadas,bar,43.26,-2.92\nSin Coordenadas,tienda,,\n'
        f = SimpleUploadedFile('x.csv', content, content_type='text/csv')
        rows, errors = parse_csv(f)
        self.assertEqual(len(rows), 2)
        self.assertIsNone(rows[1]['lat'])

    def test_csv_import_view_creates_and_dedupes(self):
        create_prospect({'name': 'Ya Existe', 'phone': '600555666'})
        with override_settings(ALLOWED_HOSTS=['testserver']):
            c = Client()
            import os
            c.post('/panel/prospeccion/', {'crm_password': os.environ.get('WI_CRM_PASSWORD', '')})
            from django.core.files.uploadedfile import SimpleUploadedFile
            content = ('name,sector,phone\nNueva Empresa,bar,600777888\nYa Existe,bar,600555666\n').encode()
            f = SimpleUploadedFile('import.csv', content, content_type='text/csv')
            r = c.post('/panel/prospeccion/mapa/api/import-csv/', {'file': f})
            body = json.loads(r.content)
            self.assertEqual(body['created'], 1)
            self.assertEqual(body['duplicates'], 1)


class MapFilterTests(BaseTestCase):
    def test_bbox_and_sector_filters(self):
        staff = StaffMember.objects.create(name='Ana')
        BusinessProspect.objects.create(name='Dentro Bar', sector='bar', lat=43.26, lng=-2.92, assigned_to=staff)
        BusinessProspect.objects.create(name='Dentro Taller', sector='taller', lat=43.27, lng=-2.93)
        BusinessProspect.objects.create(name='Fuera', sector='bar', lat=10.0, lng=10.0)

        c = self.login()
        r = c.get('/panel/prospeccion/mapa/api/prospects/', {
            'south': 43.0, 'north': 43.5, 'west': -3.2, 'east': -2.7,
        })
        names = {p['name'] for p in json.loads(r.content)['prospects']}
        self.assertEqual(names, {'Dentro Bar', 'Dentro Taller'})

        r = c.get('/panel/prospeccion/mapa/api/prospects/', {
            'south': 43.0, 'north': 43.5, 'west': -3.2, 'east': -2.7, 'sector': 'bar',
        })
        names = {p['name'] for p in json.loads(r.content)['prospects']}
        self.assertEqual(names, {'Dentro Bar'})

        r = c.get('/panel/prospeccion/mapa/api/prospects/', {
            'south': 43.0, 'north': 43.5, 'west': -3.2, 'east': -2.7, 'assigned_to': staff.pk,
        })
        names = {p['name'] for p in json.loads(r.content)['prospects']}
        self.assertEqual(names, {'Dentro Bar'})


class ConsentTests(BaseTestCase):
    def test_toggling_publish_consent_off_hides_from_public_map(self):
        prospect = BusinessProspect.objects.create(
            name='Consent Toggle', sector='bar', lat=43.26, lng=-2.92,
            publish_consent=True, publish_confirmed_by_staff=True)
        c = Client()
        r = c.get('/mapa-digital/api/prospects/', {'south': 43.0, 'north': 43.5, 'west': -3.2, 'east': -2.7})
        self.assertIn('Consent Toggle', [p['name'] for p in json.loads(r.content)['prospects']])

        prospect.publish_revoked_at = timezone.now()
        prospect.save()
        r = c.get('/mapa-digital/api/prospects/', {'south': 43.0, 'north': 43.5, 'west': -3.2, 'east': -2.7})
        self.assertNotIn('Consent Toggle', [p['name'] for p in json.loads(r.content)['prospects']])
