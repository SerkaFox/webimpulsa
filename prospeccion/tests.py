import json
import os
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from crm.models import Lead, Proposal
from . import places, wa_bridge
from .csv_import import parse_csv
from .models import BusinessContact, BusinessProspect, ChequeoAudit, PlacesApiUsage, ProspectPhoto, StaffMember
from .quiz_config import CATEGORY_WEIGHTS
from .recommendations import build_recommendations
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


class PreliminarAuditUiTests(BaseTestCase):
    def test_complete_creates_preliminar_audit_with_source_comment_evidence(self):
        prospect = BusinessProspect.objects.create(name='Prelim UI Co', sector='bar')
        c = self.login()
        qs = questions_for_sector('bar')
        answers = {
            q['id']: {'value': 'si', 'comment': f'visto en la web ({q["id"]})', 'evidence_url': 'https://example.com/x'}
            for q in qs
        }
        r = c.post(f'/panel/prospeccion/{prospect.pk}/preliminar/complete/',
                   data=json.dumps({'sector': 'bar', 'answers': answers}), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.content)
        self.assertEqual(body['stage'], 'preliminar')
        self.assertEqual(body['score'], 100)

        audit = ChequeoAudit.objects.get(pk=body['audit_id'])
        self.assertEqual(audit.stage, ChequeoAudit.STAGE_PRELIMINAR)
        self.assertTrue(all(a['source'] == 'public_check' for a in audit.answers))
        self.assertTrue(all(a.get('comment') for a in audit.answers))
        self.assertTrue(all(a.get('evidence_url') == 'https://example.com/x' for a in audit.answers))

    def test_second_preliminar_does_not_overwrite_first(self):
        prospect = BusinessProspect.objects.create(name='Prelim Version Co', sector='taller')
        c = self.login()
        qs = questions_for_sector('taller')

        answers_low = {q['id']: {'value': 'no'} for q in qs}
        r1 = c.post(f'/panel/prospeccion/{prospect.pk}/preliminar/complete/',
                    data=json.dumps({'sector': 'taller', 'answers': answers_low}), content_type='application/json')
        first_id = json.loads(r1.content)['audit_id']

        answers_high = {q['id']: {'value': 'si'} for q in qs}
        r2 = c.post(f'/panel/prospeccion/{prospect.pk}/preliminar/complete/',
                    data=json.dumps({'sector': 'taller', 'answers': answers_high}), content_type='application/json')
        second_id = json.loads(r2.content)['audit_id']

        self.assertNotEqual(first_id, second_id)
        first = ChequeoAudit.objects.get(pk=first_id)
        self.assertEqual(first.score, 0)  # sigue igual, no lo tocó el segundo POST
        self.assertEqual(prospect.audits.count(), 2)

    def test_draft_save_then_complete_reads_session_draft(self):
        prospect = BusinessProspect.objects.create(name='Prelim Draft Co', sector='clinica')
        c = self.login()
        qs = questions_for_sector('clinica')
        answers = {q['id']: {'value': 'en_parte'} for q in qs}
        r = c.post(f'/panel/prospeccion/{prospect.pk}/preliminar/draft/',
                   data=json.dumps({'sector': 'clinica', 'answers': answers}), content_type='application/json')
        self.assertEqual(json.loads(r.content)['count'], len(qs))

        r = c.post(f'/panel/prospeccion/{prospect.pk}/preliminar/complete/', data='{}', content_type='application/json')
        body = json.loads(r.content)
        # en_parte = 50% en todas las preguntas, pero el redondeo por
        # categoría (round-half-to-even) sube algunas categorías de peso 15
        # de 7.5 a 8 — 52 es el resultado correcto, no 50 (verificado con
        # scoring.compute_score directamente, mismo criterio que ScoringTests).
        self.assertEqual(body['score'], 52)

        # el borrador se limpia tras completar: la pagina de detalle ya no
        # debe traer respuestas precargadas para una nueva auditoria
        r2 = c.get(f'/panel/prospeccion/{prospect.pk}/')
        html = r2.content.decode()
        import re
        m = re.search(r'var PRELIM_DRAFT = (\{.*?\});', html)
        self.assertIsNotNone(m)
        draft = json.loads(m.group(1))
        self.assertEqual(draft, {})

    def test_panel_routes_for_preliminar_require_login(self):
        prospect = BusinessProspect.objects.create(name='Prelim Auth Co', sector='bar')
        with override_settings(ALLOWED_HOSTS=['testserver']):
            c = Client()
            r = c.post(f'/panel/prospeccion/{prospect.pk}/preliminar/draft/', data='{}', content_type='application/json')
            self.assertIn('Web-Impulsa CRM', r.content.decode())
            r = c.post(f'/panel/prospeccion/{prospect.pk}/preliminar/complete/', data='{}', content_type='application/json')
            self.assertIn('Web-Impulsa CRM', r.content.decode())


class ContactCrudTests(BaseTestCase):
    def test_create_update_delete_contact(self):
        prospect = BusinessProspect.objects.create(name='Contact CRUD Co', sector='bar')
        c = self.login()

        r = c.post(f'/panel/prospeccion/{prospect.pk}/contacts/', data=json.dumps({
            'name': 'Juan', 'role': 'manager', 'phone': '600111222', 'whatsapp': '34600111222',
            'email': 'juan@x.com', 'preferred_channel': 'whatsapp', 'is_primary': True, 'notes': 'nota',
        }), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        contact_id = json.loads(r.content)['contact']['id']
        self.assertEqual(BusinessContact.objects.filter(prospect=prospect).count(), 1)

        r = c.post(f'/panel/prospeccion/{prospect.pk}/contacts/{contact_id}/update/',
                   data=json.dumps({'notes': 'nota editada', 'role': 'owner'}), content_type='application/json')
        body = json.loads(r.content)['contact']
        self.assertEqual(body['notes'], 'nota editada')
        self.assertEqual(body['role'], 'owner')

        r = c.post(f'/panel/prospeccion/{prospect.pk}/contacts/{contact_id}/delete/')
        self.assertEqual(json.loads(r.content), {'deleted': True})
        self.assertEqual(BusinessContact.objects.filter(prospect=prospect).count(), 0)

    def test_contact_routes_require_login(self):
        prospect = BusinessProspect.objects.create(name='Contact Auth Co', sector='bar')
        contact = BusinessContact.objects.create(prospect=prospect, name='X')
        with override_settings(ALLOWED_HOSTS=['testserver']):
            c = Client()
            for url in (
                f'/panel/prospeccion/{prospect.pk}/contacts/',
                f'/panel/prospeccion/{prospect.pk}/contacts/{contact.pk}/update/',
                f'/panel/prospeccion/{prospect.pk}/contacts/{contact.pk}/delete/',
                f'/panel/prospeccion/{prospect.pk}/contacts/{contact.pk}/consent/',
            ):
                r = c.post(url, data='{}', content_type='application/json')
                self.assertIn('Web-Impulsa CRM', r.content.decode(), msg=url)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PhotoGalleryTests(BaseTestCase):
    def _fake_image(self, name='foto.jpg', content_type='image/jpeg', size=None):
        return SimpleUploadedFile(name, b'\xff\xd8\xff' + b'0' * (size or 100), content_type=content_type)

    def test_upload_creates_photo_and_shows_in_detail(self):
        prospect = BusinessProspect.objects.create(name='Con Fotos', sector='bar')
        c = self.login()
        r = c.post(f'/panel/prospeccion/{prospect.pk}/photos/', {'photos': [self._fake_image()]})
        data = json.loads(r.content)
        self.assertEqual(len(data['photos']), 1)
        self.assertEqual(prospect.site_photos.count(), 1)
        detail = c.get(f'/panel/prospeccion/{prospect.pk}/')
        self.assertIn(b'photo-item', detail.content)

    def test_multiple_files_in_one_request(self):
        prospect = BusinessProspect.objects.create(name='Varias Fotos', sector='bar')
        c = self.login()
        r = c.post(f'/panel/prospeccion/{prospect.pk}/photos/', {
            'photos': [self._fake_image('a.jpg'), self._fake_image('b.png', 'image/png')],
        })
        data = json.loads(r.content)
        self.assertEqual(len(data['photos']), 2)
        self.assertEqual(prospect.site_photos.count(), 2)

    def test_rejects_disallowed_extension(self):
        prospect = BusinessProspect.objects.create(name='Extension Mala', sector='bar')
        c = self.login()
        bad_file = SimpleUploadedFile('script.exe', b'x' * 10, content_type='application/octet-stream')
        r = c.post(f'/panel/prospeccion/{prospect.pk}/photos/', {'photos': [bad_file]})
        data = json.loads(r.content)
        self.assertEqual(data['photos'], [])
        self.assertEqual(len(data['errors']), 1)
        self.assertEqual(prospect.site_photos.count(), 0)

    def test_rejects_oversized_file(self):
        prospect = BusinessProspect.objects.create(name='Foto Grande', sector='bar')
        c = self.login()
        big_file = self._fake_image(size=13 * 1024 * 1024)
        r = c.post(f'/panel/prospeccion/{prospect.pk}/photos/', {'photos': [big_file]})
        data = json.loads(r.content)
        self.assertEqual(data['photos'], [])
        self.assertEqual(len(data['errors']), 1)

    def test_delete_removes_photo(self):
        prospect = BusinessProspect.objects.create(name='Para Borrar', sector='bar')
        photo = ProspectPhoto.objects.create(prospect=prospect, image=self._fake_image())
        c = self.login()
        r = c.post(f'/panel/prospeccion/{prospect.pk}/photos/{photo.pk}/delete/')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(ProspectPhoto.objects.filter(pk=photo.pk).exists())

    def test_photo_routes_require_login(self):
        prospect = BusinessProspect.objects.create(name='Sin Login Fotos', sector='bar')
        photo = ProspectPhoto.objects.create(prospect=prospect, image=self._fake_image())
        with override_settings(ALLOWED_HOSTS=['testserver']):
            c = Client()
            for url in (
                f'/panel/prospeccion/{prospect.pk}/photos/',
                f'/panel/prospeccion/{prospect.pk}/photos/{photo.pk}/delete/',
            ):
                r = c.post(url)
                self.assertIn('Web-Impulsa CRM', r.content.decode(), msg=url)


class ConsentSeparationTests(BaseTestCase):
    def test_report_and_commercial_consent_are_independent(self):
        prospect = BusinessProspect.objects.create(name='Consent Sep Co', sector='bar')
        contact = BusinessContact.objects.create(prospect=prospect, name='Dueña')
        c = self.login()

        c.post(f'/panel/prospeccion/{prospect.pk}/contacts/{contact.pk}/consent/',
               data=json.dumps({'consent_type': 'report', 'action': 'grant', 'method': 'quiz_form'}),
               content_type='application/json')
        c.post(f'/panel/prospeccion/{prospect.pk}/contacts/{contact.pk}/consent/',
               data=json.dumps({'consent_type': 'commercial', 'action': 'grant', 'method': 'quiz_form'}),
               content_type='application/json')
        contact.refresh_from_db()
        self.assertTrue(contact.consent_receive_report)
        self.assertTrue(contact.consent_commercial_contact)

        r = c.post(f'/panel/prospeccion/{prospect.pk}/contacts/{contact.pk}/consent/',
                   data=json.dumps({'consent_type': 'commercial', 'action': 'revoke'}), content_type='application/json')
        body = json.loads(r.content)['contact']
        self.assertTrue(body['consent_receive_report'])
        self.assertFalse(body['consent_commercial_contact'])
        self.assertIsNone(body['consent_receive_report_revoked_at'])
        self.assertIsNotNone(body['consent_commercial_contact_revoked_at'])

    def test_grant_stores_purpose_method_version_and_actor(self):
        """Cada consentimiento debe guardar no solo la marca de tiempo, sino
        también con qué método se obtuvo, qué versión del texto se mostró, y
        quién lo registró — sin lo cual no se podría demostrar más adelante
        exactamente qué se aceptó."""
        from .models import CONSENT_TEXT_VERSION
        prospect = BusinessProspect.objects.create(name='Consent Fields Co', sector='bar')
        contact = BusinessContact.objects.create(prospect=prospect, name='Dueña 2')
        c = self.login()

        r = c.post(f'/panel/prospeccion/{prospect.pk}/contacts/{contact.pk}/consent/',
                   data=json.dumps({'consent_type': 'report', 'action': 'grant',
                                    'method': 'llamada', 'actor': 'Ana (equipo)'}),
                   content_type='application/json')
        body = json.loads(r.content)['contact']
        self.assertEqual(body['consent_receive_report_method'], 'llamada')
        self.assertEqual(body['consent_receive_report_version'], CONSENT_TEXT_VERSION)
        self.assertEqual(body['consent_receive_report_actor'], 'Ana (equipo)')

        contact.refresh_from_db()
        self.assertEqual(contact.consent_receive_report_method, 'llamada')
        self.assertEqual(contact.consent_receive_report_version, CONSENT_TEXT_VERSION)
        self.assertEqual(contact.consent_receive_report_actor, 'Ana (equipo)')

    def test_revoking_report_leaves_commercial_untouched(self):
        prospect = BusinessProspect.objects.create(name='Consent Sep Co 2', sector='bar')
        contact = BusinessContact.objects.create(prospect=prospect, name='Dueño')
        c = self.login()
        for t in ('report', 'commercial'):
            c.post(f'/panel/prospeccion/{prospect.pk}/contacts/{contact.pk}/consent/',
                   data=json.dumps({'consent_type': t, 'action': 'grant'}), content_type='application/json')
        r = c.post(f'/panel/prospeccion/{prospect.pk}/contacts/{contact.pk}/consent/',
                   data=json.dumps({'consent_type': 'report', 'action': 'revoke'}), content_type='application/json')
        body = json.loads(r.content)['contact']
        self.assertFalse(body['consent_receive_report'])
        self.assertTrue(body['consent_commercial_contact'])


class PublishConfirmationAuthorizationTests(BaseTestCase):
    def _secret(self):
        return os.environ.get('WI_PUBLISH_CONFIRM_SECRET', '')

    def test_ordinary_staff_cannot_self_confirm_publication(self):
        prospect = BusinessProspect.objects.create(name='No Auth Co', sector='bar', publish_consent=True)
        ordinary = StaffMember.objects.create(name='Empleado Normal', can_confirm_publication=False)
        c = self.login()
        r = c.post(f'/panel/prospeccion/{prospect.pk}/publish-confirm/',
                   data=json.dumps({'staff_member_id': ordinary.pk, 'confirm_secret': self._secret()}),
                   content_type='application/json')
        self.assertEqual(r.status_code, 403)
        prospect.refresh_from_db()
        self.assertFalse(prospect.publish_confirmed_by_staff)

    def test_authorized_staff_can_confirm_publication(self):
        prospect = BusinessProspect.objects.create(name='Auth Co', sector='bar', publish_consent=True)
        admin = StaffMember.objects.create(name='Admin', can_confirm_publication=True)
        c = self.login()
        r = c.post(f'/panel/prospeccion/{prospect.pk}/publish-confirm/',
                   data=json.dumps({'staff_member_id': admin.pk, 'confirm_secret': self._secret()}),
                   content_type='application/json')
        self.assertEqual(r.status_code, 200)
        prospect.refresh_from_db()
        self.assertTrue(prospect.publish_confirmed_by_staff)

    def test_nonexistent_staff_id_rejected(self):
        prospect = BusinessProspect.objects.create(name='Fake Staff Co', sector='bar', publish_consent=True)
        c = self.login()
        r = c.post(f'/panel/prospeccion/{prospect.pk}/publish-confirm/',
                   data=json.dumps({'staff_member_id': 999999, 'confirm_secret': self._secret()}),
                   content_type='application/json')
        self.assertEqual(r.status_code, 403)

    def test_spoofing_authorized_staff_id_without_secret_is_rejected(self):
        """El hallazgo central de la revisión de seguridad: elegir el ID de
        un StaffMember autorizado en el payload NO basta — la sesión CRM es
        compartida por todo el equipo, así que sin el secreto aparte,
        cualquiera podría enviar ese mismo ID y auto-confirmarse."""
        prospect = BusinessProspect.objects.create(name='Spoof Co', sector='bar', publish_consent=True)
        admin = StaffMember.objects.create(name='Admin Real', can_confirm_publication=True)
        c = self.login()  # sesión CRM normal, la misma que tiene cualquier empleado

        # sin secreto en absoluto
        r = c.post(f'/panel/prospeccion/{prospect.pk}/publish-confirm/',
                   data=json.dumps({'staff_member_id': admin.pk}), content_type='application/json')
        self.assertEqual(r.status_code, 403)

        # con un secreto adivinado/incorrecto
        r = c.post(f'/panel/prospeccion/{prospect.pk}/publish-confirm/',
                   data=json.dumps({'staff_member_id': admin.pk, 'confirm_secret': 'lo-que-sea-inventado'}),
                   content_type='application/json')
        self.assertEqual(r.status_code, 403)

        prospect.refresh_from_db()
        self.assertFalse(prospect.publish_confirmed_by_staff)

        # con el secreto correcto, la MISMA sesión SÍ puede — confirma que el
        # secreto (no la sesión CRM genérica) es lo que realmente autoriza
        r = c.post(f'/panel/prospeccion/{prospect.pk}/publish-confirm/',
                   data=json.dumps({'staff_member_id': admin.pk, 'confirm_secret': self._secret()}),
                   content_type='application/json')
        self.assertEqual(r.status_code, 200)
        prospect.refresh_from_db()
        self.assertTrue(prospect.publish_confirmed_by_staff)

    def test_missing_secret_configuration_fails_closed(self):
        """Si WI_PUBLISH_CONFIRM_SECRET no está configurado en el entorno,
        el endpoint debe rechazar SIEMPRE, nunca permitir por defecto."""
        prospect = BusinessProspect.objects.create(name='No Secret Configured Co', sector='bar', publish_consent=True)
        admin = StaffMember.objects.create(name='Admin Sin Secreto Configurado', can_confirm_publication=True)
        c = self.login()
        with mock.patch('prospeccion.views_panel._PUBLISH_CONFIRM_SECRET', ''):
            r = c.post(f'/panel/prospeccion/{prospect.pk}/publish-confirm/',
                       data=json.dumps({'staff_member_id': admin.pk, 'confirm_secret': 'cualquier-cosa'}),
                       content_type='application/json')
        self.assertEqual(r.status_code, 500)
        prospect.refresh_from_db()
        self.assertFalse(prospect.publish_confirmed_by_staff)


class PublicationRequiresBothFlagsTests(BaseTestCase):
    def test_publicity_needs_consent_and_staff_confirmation_together(self):
        prospect = BusinessProspect.objects.create(name='Both Flags Co', sector='bar', lat=43.26, lng=-2.92)
        admin = StaffMember.objects.create(name='Admin2', can_confirm_publication=True)
        c = self.login()

        def public_names():
            r = c.get('/mapa-digital/api/prospects/', {'south': 43.0, 'north': 43.5, 'west': -3.2, 'east': -2.7})
            return {p['name'] for p in json.loads(r.content)['prospects']}

        self.assertNotIn(prospect.name, public_names())

        c.post(f'/panel/prospeccion/{prospect.pk}/publish-consent/',
               data=json.dumps({'action': 'grant'}), content_type='application/json')
        self.assertNotIn(prospect.name, public_names())  # falta confirmación admin

        c.post(f'/panel/prospeccion/{prospect.pk}/publish-confirm/',
               data=json.dumps({'staff_member_id': admin.pk,
                                'confirm_secret': os.environ.get('WI_PUBLISH_CONFIRM_SECRET', '')}),
               content_type='application/json')
        self.assertIn(prospect.name, public_names())

        c.post(f'/panel/prospeccion/{prospect.pk}/publish-consent/',
               data=json.dumps({'action': 'revoke'}), content_type='application/json')
        self.assertNotIn(prospect.name, public_names())


# ── Mapa con búsqueda Google Places (UX simplificado) ─────────────────────

class GooglePlacesModuleTests(TestCase):
    @override_settings(GOOGLE_PLACES_API_KEY='')
    def test_search_text_requires_api_key(self):
        with self.assertRaises(places.PlacesConfigError):
            places.search_text('bar en Barakaldo')

    def test_field_mask_never_requests_reviews_photos_rating_hours(self):
        for forbidden in ('review', 'photo', 'rating', 'Hours'):
            self.assertNotIn(forbidden, places.FIELD_MASK)

    @override_settings(GOOGLE_PLACES_API_KEY='fake-key-for-tests', GOOGLE_PLACES_DAILY_QUOTA=1)
    def test_search_text_enforces_daily_quota(self):
        fake_response = mock.Mock()
        fake_response.raise_for_status = mock.Mock()
        fake_response.json.return_value = {'places': []}
        with mock.patch('prospeccion.places.requests.post', return_value=fake_response) as mocked_post:
            places.search_text('bar')  # 1ª llamada: consume la única unidad de cuota
            with self.assertRaises(places.PlacesQuotaExceeded):
                places.search_text('bar')  # 2ª llamada: por encima de cuota
        self.assertEqual(mocked_post.call_count, 1)  # la 2ª ni siquiera llamó a Google

    @override_settings(GOOGLE_PLACES_API_KEY='fake-key-for-tests')
    def test_search_text_sends_minimal_field_mask_and_region_bias(self):
        fake_response = mock.Mock()
        fake_response.raise_for_status = mock.Mock()
        fake_response.json.return_value = {'places': [{
            'id': 'ChIJ123', 'displayName': {'text': 'Bar de Prueba'},
            'formattedAddress': 'Calle Falsa 123, Barakaldo',
            'location': {'latitude': 43.29, 'longitude': -2.99},
            'types': ['bar', 'restaurant'], 'primaryType': 'bar',
            'nationalPhoneNumber': '944 000 000', 'websiteUri': 'https://bar-de-prueba.example',
            'googleMapsUri': 'https://maps.google.com/?cid=123',
        }]}
        with mock.patch('prospeccion.places.requests.post', return_value=fake_response) as mocked_post:
            results = places.search_text('bar de prueba', lat=43.29, lng=-2.99)
        _, kwargs = mocked_post.call_args
        self.assertEqual(kwargs['headers']['X-Goog-FieldMask'], places.FIELD_MASK)
        self.assertEqual(kwargs['json']['regionCode'], 'ES')
        self.assertEqual(kwargs['json']['locationBias']['circle']['center']['latitude'], 43.29)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['place_id'], 'ChIJ123')
        self.assertEqual(results[0]['category'], 'bar')
        for forbidden_key in ('reviews', 'photos', 'rating', 'regularOpeningHours'):
            self.assertNotIn(forbidden_key, results[0])

    def test_guess_sector_maps_known_google_types(self):
        self.assertEqual(places.guess_sector(['restaurant', 'food']), 'bar')
        self.assertEqual(places.guess_sector(['hair_salon']), 'salon')
        self.assertEqual(places.guess_sector(['car_repair']), 'taller')
        self.assertEqual(places.guess_sector(['something_unknown']), 'otro')

    def test_resolve_maps_link_extracts_coords_from_at_pattern(self):
        url = 'https://www.google.com/maps/place/Bar+de+Prueba/@43.2627,-2.9253,17z/data=!xyz'
        result = places.resolve_maps_link(url)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result['lat'], 43.2627)
        self.assertAlmostEqual(result['lng'], -2.9253)
        self.assertEqual(result['name'], 'Bar de Prueba')

    def test_resolve_maps_link_returns_none_for_unparseable_url(self):
        self.assertIsNone(places.resolve_maps_link('https://example.com/not-a-maps-link'))
        self.assertIsNone(places.resolve_maps_link(''))


class PlacesSearchViewTests(BaseTestCase):
    def test_requires_query(self):
        c = self.login()
        r = c.get('/panel/prospeccion/mapa/api/search/')
        self.assertEqual(r.status_code, 400)

    def test_finds_existing_webimpulsa_company_first(self):
        BusinessProspect.objects.create(name='Taller Ejemplo Ya Existente', sector='taller')
        c = self.login()
        with mock.patch('prospeccion.views_panel.places.search_text', return_value=[]):
            r = c.get('/panel/prospeccion/mapa/api/search/', {'q': 'Taller Ejemplo'})
        data = json.loads(r.content)
        self.assertEqual(len(data['existing']), 1)
        self.assertEqual(data['existing'][0]['name'], 'Taller Ejemplo Ya Existente')

    def test_existing_match_carries_lat_lng_color_and_score_for_map_markers(self):
        BusinessProspect.objects.create(
            name='Con Ubicación', sector='taller', lat=43.26, lng=-2.92, current_score=67,
            sales_status=BusinessProspect.SALES_AUDITED,
        )
        c = self.login()
        with mock.patch('prospeccion.views_panel.places.search_text', return_value=[]):
            r = c.get('/panel/prospeccion/mapa/api/search/', {'q': 'Con Ubicaci'})
        match = json.loads(r.content)['existing'][0]
        self.assertEqual(match['lat'], 43.26)
        self.assertEqual(match['lng'], -2.92)
        self.assertEqual(match['current_score'], 67)
        self.assertTrue(match['color'].startswith('#'))
        self.assertEqual(match['prospect_id'], BusinessProspect.objects.get(name='Con Ubicación').pk)

    def test_annotates_google_result_as_existing_when_phone_matches(self):
        BusinessProspect.objects.create(name='Bar Antiguo', sector='bar', phone='944123456')
        c = self.login()
        fake_google_result = {
            'place_id': 'ChIJnew', 'name': 'Bar Antiguo (Google)', 'address': 'Calle X',
            'lat': 43.29, 'lng': -2.99, 'category': 'bar', 'category_raw': 'bar',
            'phone': '944 123 456', 'website': '', 'google_maps_url': '',
        }
        with mock.patch('prospeccion.views_panel.places.search_text', return_value=[fake_google_result]):
            r = c.get('/panel/prospeccion/mapa/api/search/', {'q': 'Bar Antiguo'})
        data = json.loads(r.content)
        self.assertEqual(len(data['google']), 1)
        self.assertIsNotNone(data['google'][0]['existing_prospect_id'])

    def test_google_results_never_carry_reviews_photos_rating(self):
        c = self.login()
        fake_google_result = {
            'place_id': 'ChIJnew2', 'name': 'Cafetería Nueva', 'address': '',
            'lat': None, 'lng': None, 'category': 'bar', 'category_raw': 'cafe',
            'phone': '', 'website': '', 'google_maps_url': '',
        }
        with mock.patch('prospeccion.views_panel.places.search_text', return_value=[fake_google_result]):
            r = c.get('/panel/prospeccion/mapa/api/search/', {'q': 'Cafetería Nueva'})
        data = json.loads(r.content)
        for forbidden_key in ('reviews', 'photos', 'rating', 'regularOpeningHours'):
            self.assertNotIn(forbidden_key, data['google'][0])

    def test_places_config_error_is_reported_but_existing_matches_still_work(self):
        BusinessProspect.objects.create(name='Academia Existente', sector='academia')
        c = self.login()
        with mock.patch('prospeccion.views_panel.places.search_text',
                         side_effect=places.PlacesConfigError('sin clave')):
            r = c.get('/panel/prospeccion/mapa/api/search/', {'q': 'Academia'})
        data = json.loads(r.content)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(data['existing']), 1)
        self.assertTrue(data['google_error'])


class AddFromPlaceTests(BaseTestCase):
    def test_create_from_confirmed_place_stores_only_whitelisted_fields(self):
        c = self.login()
        payload = {
            'name': 'Clínica Confirmada', 'address': 'Calle Salud 5', 'sector': 'clinica',
            'lat': 43.3, 'lng': -3.0, 'phone': '944555555', 'website': 'https://clinica.example',
            'place_id': 'ChIJconfirmed', 'google_maps_url': 'https://maps.google.com/?cid=999',
            # campos que Google NUNCA debería haber entregado (no se piden en
            # FIELD_MASK), y que aunque llegasen aquí en un payload
            # manipulado, no existen en el modelo:
            'rating': 4.8, 'reviews': ['excelente'], 'photos': ['http://x/1.jpg'],
            'opening_hours': {'monday': '9-18'},
        }
        r = c.post('/panel/prospeccion/mapa/api/prospects/add-from-place/',
                    data=json.dumps(payload), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        prospect = BusinessProspect.objects.get(name='Clínica Confirmada')
        self.assertEqual(prospect.google_place_id, 'ChIJconfirmed')
        self.assertEqual(prospect.gmaps_url, 'https://maps.google.com/?cid=999')
        self.assertEqual(prospect.source, BusinessProspect.SOURCE_GOOGLE_PLACES)
        field_names = {f.name for f in BusinessProspect._meta.get_fields()}
        for forbidden_field in ('rating', 'reviews', 'photos', 'opening_hours'):
            self.assertNotIn(forbidden_field, field_names)

    def test_dedupe_by_place_id_prevents_duplicate_creation(self):
        existing = BusinessProspect.objects.create(
            name='Ya Estaba', sector='bar', google_place_id='ChIJexisting', lat=43.2, lng=-3.1,
        )
        c = self.login()
        payload = {
            'name': 'Ya Estaba (nombre distinto en Google)', 'sector': 'bar',
            'lat': 43.2, 'lng': -3.1, 'place_id': 'ChIJexisting',
        }
        r = c.post('/panel/prospeccion/mapa/api/prospects/add-from-place/',
                    data=json.dumps(payload), content_type='application/json')
        data = json.loads(r.content)
        self.assertFalse(data['created'])
        self.assertEqual(data['prospect']['id'], existing.pk)
        self.assertEqual(BusinessProspect.objects.filter(google_place_id='ChIJexisting').count(), 1)

    def test_requires_name(self):
        c = self.login()
        r = c.post('/panel/prospeccion/mapa/api/prospects/add-from-place/',
                    data=json.dumps({'sector': 'bar'}), content_type='application/json')
        self.assertEqual(r.status_code, 400)


class ManualPinPlacementTests(BaseTestCase):
    def test_manual_click_creates_prospect_with_exact_coordinates(self):
        c = self.login()
        r = c.post('/panel/prospeccion/mapa/api/prospects/add/', data=json.dumps({
            'name': 'Lugar Marcado a Mano', 'sector': 'otro', 'lat': 43.25, 'lng': -2.95,
        }), content_type='application/json')
        data = json.loads(r.content)
        self.assertTrue(data['created'])
        prospect = BusinessProspect.objects.get(pk=data['prospect']['id'])
        self.assertEqual(prospect.lat, 43.25)
        self.assertEqual(prospect.lng, -2.95)
        self.assertFalse(prospect.needs_manual_placement)
        self.assertEqual(prospect.source, BusinessProspect.SOURCE_MAP_CLICK)


class ParseMapsLinkViewTests(BaseTestCase):
    def test_parses_at_pattern_link(self):
        c = self.login()
        url = 'https://www.google.com/maps/place/Taller+Test/@43.1,-3.2,15z'
        r = c.post('/panel/prospeccion/mapa/api/parse-maps-link/',
                    data=json.dumps({'url': url}), content_type='application/json')
        data = json.loads(r.content)
        self.assertAlmostEqual(data['lat'], 43.1)
        self.assertAlmostEqual(data['lng'], -3.2)

    def test_rejects_unparseable_link(self):
        c = self.login()
        r = c.post('/panel/prospeccion/mapa/api/parse-maps-link/',
                    data=json.dumps({'url': 'https://example.com/nope'}), content_type='application/json')
        self.assertEqual(r.status_code, 400)


class OldRoutesStillWorkTests(BaseTestCase):
    """El rediseño de /panel/prospeccion/mapa/ no debe romper nada de lo que
    ya funcionaba: filtros por bbox, alta manual clásica, importación CSV,
    ficha de prospect con sus acciones existentes."""

    def test_internal_map_renders_without_google_maps_key(self):
        c = self.login()
        with override_settings(GOOGLE_MAPS_JS_API_KEY=''):
            r = c.get('/panel/prospeccion/mapa/')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'GOOGLE_MAPS_JS_API_KEY', r.content)

    def test_bbox_api_still_filters(self):
        BusinessProspect.objects.create(name='Dentro', sector='bar', lat=43.26, lng=-2.92)
        BusinessProspect.objects.create(name='Fuera', sector='bar', lat=10.0, lng=10.0)
        c = self.login()
        r = c.get('/panel/prospeccion/mapa/api/prospects/',
                   {'south': 43.0, 'north': 43.5, 'west': -3.2, 'east': -2.7})
        names = {p['name'] for p in json.loads(r.content)['prospects']}
        self.assertIn('Dentro', names)
        self.assertNotIn('Fuera', names)

    def test_prospect_detail_still_renders_with_all_sections(self):
        prospect = BusinessProspect.objects.create(name='Ficha Clásica', sector='bar')
        c = self.login()
        r = c.get(f'/panel/prospeccion/{prospect.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'Hacer chequeo', r.content)
        self.assertIn(b'Preparar propuesta', r.content)
        self.assertIn('Añadir contacto'.encode('utf-8'), r.content)


class CrmProspeccionNavigationTests(BaseTestCase):
    """Tania entra por /wi/crm/ (contraseña compartida) y antes no había
    ningún enlace desde ahí hacia el mapa de prospección interno, ni de
    vuelta — se navegaba solo escribiendo la URL de memoria."""

    def test_crm_leads_list_links_to_prospeccion_map(self):
        c = self.login()
        r = c.get('/wi/crm/')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'href="/panel/prospeccion/mapa/"', r.content)

    def test_prospeccion_dashboard_links_back_to_crm(self):
        c = self.login()
        r = c.get('/panel/prospeccion/')
        self.assertIn(b'href="/wi/crm/"', r.content)

    def test_internal_map_links_back_to_crm(self):
        c = self.login()
        r = c.get('/panel/prospeccion/mapa/')
        self.assertIn(b'href="/wi/crm/"', r.content)


class MapMarkerScoreAndSearchPlottingTests(BaseTestCase):
    def test_internal_map_renders_score_label_and_search_marker_plotting(self):
        c = self.login()
        r = c.get('/panel/prospeccion/mapa/')
        html = r.content.decode()
        self.assertIn('function scoreLabel', html)
        self.assertIn('function plotSearchMarkers', html)
        self.assertIn('label: scoreLabel(p.current_score)', html)


class RecommendationsTests(TestCase):
    def test_dedupes_repeated_extra_across_questions(self):
        reco = build_recommendations('bar', ['messages_lost', 'centralized_records'])
        labels = [it['label'] for it in reco['items']]
        self.assertEqual(labels.count('Panel para tu equipo'), 1)

    def test_needs_core_site_separated_from_priced_items(self):
        reco = build_recommendations('salon', ['mobile_page', 'one_tap_contact'])
        self.assertTrue(reco['needs_core_site'])
        labels = [it['label'] for it in reco['items']]
        self.assertEqual(labels, ['Botón de WhatsApp'])

    def test_no_core_site_flag_when_mobile_page_not_in_fix_ids(self):
        reco = build_recommendations('salon', ['one_tap_contact'])
        self.assertFalse(reco['needs_core_site'])

    def test_estimated_total_matches_sum_of_items(self):
        reco = build_recommendations('bar', ['one_tap_contact', 'auto_confirmation'])
        self.assertEqual(reco['estimated_total'], sum(it['price'] for it in reco['items']))

    def test_sector_aware_main_action_mapping(self):
        bar_reco = build_recommendations('bar', ['main_action_no_wait'])
        salon_reco = build_recommendations('salon', ['main_action_no_wait'])
        self.assertEqual(bar_reco['items'][0]['label'], 'Pedidos online')
        self.assertEqual(salon_reco['items'][0]['label'], 'Citas y reservas online')

    def test_unmapped_or_unknown_fix_id_ignored(self):
        reco = build_recommendations('bar', ['not_a_real_question'])
        self.assertEqual(reco['items'], [])
        self.assertFalse(reco['needs_core_site'])

    def test_generic_hours_package_used_as_fallback(self):
        reco = build_recommendations('bar', ['reviews_uptodate'])
        self.assertEqual(reco['items'][0]['label'], 'Bolsa 5 horas')


class WaBridgeTests(TestCase):
    """El bridge compartido con `anna` tiene un bug conocido: a veces devuelve
    HTTP 500 justo después de entregar el mensaje de verdad, al intentar leer
    result.id de una respuesta undefined de whatsapp-web.js. send_text() debe
    tratar ESE error concreto como éxito (no bloquear al usuario ni marcar el
    informe como no enviado), pero seguir fallando ante errores reales."""

    def test_known_result_id_crash_is_treated_as_success(self):
        import urllib.error

        from prospeccion import wa_bridge

        body = b'{"error":"Cannot read properties of undefined (reading \'id\')"}'
        http_error = urllib.error.HTTPError(
            'http://127.0.0.1:8125/messages', 500, 'Internal Server Error', {}, mock.Mock()
        )
        http_error.read = mock.Mock(return_value=body)
        with override_settings(WHATSAPP_BRIDGE_URL='http://127.0.0.1:8125', WHATSAPP_BRIDGE_TOKEN='t'):
            with mock.patch('prospeccion.wa_bridge.urlopen', side_effect=http_error):
                result = wa_bridge.send_text('+34600111222', 'hola')
        self.assertTrue(result['ok'])

    def test_other_bridge_errors_still_raise(self):
        import urllib.error

        from prospeccion import wa_bridge

        http_error = urllib.error.HTTPError(
            'http://127.0.0.1:8125/messages', 409, 'Conflict', {}, mock.Mock()
        )
        http_error.read = mock.Mock(return_value=b'{"error":"Session is not ready: starting"}')
        with override_settings(WHATSAPP_BRIDGE_URL='http://127.0.0.1:8125', WHATSAPP_BRIDGE_TOKEN='t'):
            with mock.patch('prospeccion.wa_bridge.urlopen', side_effect=http_error):
                with self.assertRaises(wa_bridge.WhatsAppBridgeError):
                    wa_bridge.send_text('+34600111222', 'hola')


class ReceiveReportPublicTests(BaseTestCase):
    def _create_audit(self, **overrides):
        defaults = dict(
            prospect=None, mode='public', stage='confirmado', sector='bar',
            questionnaire_version='v1', answers=[], score=40, category_scores={},
            good_ids=[], fix_ids=['one_tap_contact'],
        )
        defaults.update(overrides)
        return ChequeoAudit.objects.create(**defaults)

    def _post(self, audit, phone='+34600111222', consent=True):
        c = Client()
        return c, c.post(
            '/chequeo-digital/api/receive-report/',
            data=json.dumps({'report_token': audit.report_token, 'phone': phone, 'consent': consent}),
            content_type='application/json',
        )

    def test_requires_consent(self):
        audit = self._create_audit()
        _, r = self._post(audit, consent=False)
        self.assertEqual(r.status_code, 400)

    def test_rejects_invalid_phone(self):
        audit = self._create_audit()
        _, r = self._post(audit, phone='abc')
        self.assertEqual(r.status_code, 400)

    def test_unknown_report_token_404s(self):
        c = Client()
        r = c.post('/chequeo-digital/api/receive-report/',
                   data=json.dumps({'report_token': 'not-real', 'phone': '+34600111222', 'consent': True}),
                   content_type='application/json')
        self.assertEqual(r.status_code, 404)

    def test_sends_and_stores_phone_and_consent(self):
        audit = self._create_audit()
        with mock.patch('prospeccion.views_public.wa_bridge.send_text', return_value={'ok': True}) as send_mock:
            _, r = self._post(audit)
        self.assertEqual(r.status_code, 200)
        send_mock.assert_called_once()
        self.assertEqual(send_mock.call_args[0][0], '+34600111222')
        audit.refresh_from_db()
        self.assertEqual(audit.respondent_phone, '+34600111222')
        self.assertIsNotNone(audit.respondent_consent_at)
        self.assertIsNotNone(audit.report_sent_at)

    def test_bridge_failure_returns_502_and_does_not_store_phone(self):
        audit = self._create_audit()
        with mock.patch('prospeccion.views_public.wa_bridge.send_text',
                         side_effect=wa_bridge.WhatsAppBridgeError('boom')):
            _, r = self._post(audit)
        self.assertEqual(r.status_code, 502)
        audit.refresh_from_db()
        self.assertEqual(audit.respondent_phone, '')
        self.assertIsNone(audit.report_sent_at)


class ReceiveReportPersonalTests(BaseTestCase):
    def test_uses_saved_whatsapp_no_phone_needed_in_request(self):
        prospect = BusinessProspect.objects.create(name='Con WhatsApp', sector='bar', whatsapp='611222333')
        ChequeoAudit.objects.create(
            prospect=prospect, mode='personal', stage='confirmado', sector='bar',
            questionnaire_version='v1', answers=[], score=50, category_scores={}, good_ids=[], fix_ids=[],
        )
        c = Client()
        with mock.patch('prospeccion.views_public.wa_bridge.send_text', return_value={'ok': True}) as send_mock:
            r = c.post(f'/chequeo-digital/e/{prospect.public_token}/receive-report/')
        self.assertEqual(r.status_code, 200)
        send_mock.assert_called_once()
        self.assertEqual(send_mock.call_args[0][0], '611222333')

    def test_falls_back_to_phone_when_no_whatsapp(self):
        prospect = BusinessProspect.objects.create(name='Solo Telefono', sector='bar', phone='611222444')
        ChequeoAudit.objects.create(
            prospect=prospect, mode='personal', stage='confirmado', sector='bar',
            questionnaire_version='v1', answers=[], score=50, category_scores={}, good_ids=[], fix_ids=[],
        )
        c = Client()
        with mock.patch('prospeccion.views_public.wa_bridge.send_text', return_value={'ok': True}):
            c.post(f'/chequeo-digital/e/{prospect.public_token}/receive-report/')
        self.assertTrue(prospect.interactions.filter(type='report_sent').exists())

    def test_no_audit_yet_returns_404(self):
        prospect = BusinessProspect.objects.create(name='Sin Audit', sector='bar', whatsapp='611000000')
        c = Client()
        r = c.post(f'/chequeo-digital/e/{prospect.public_token}/receive-report/')
        self.assertEqual(r.status_code, 404)

    def test_no_phone_saved_returns_400(self):
        prospect = BusinessProspect.objects.create(name='Sin Telefono', sector='bar')
        ChequeoAudit.objects.create(
            prospect=prospect, mode='personal', stage='confirmado', sector='bar',
            questionnaire_version='v1', answers=[], score=50, category_scores={}, good_ids=[], fix_ids=[],
        )
        c = Client()
        r = c.post(f'/chequeo-digital/e/{prospect.public_token}/receive-report/')
        self.assertEqual(r.status_code, 400)

    def test_wrong_token_404s(self):
        c = Client()
        r = c.post('/chequeo-digital/e/not-a-real-token/receive-report/')
        self.assertEqual(r.status_code, 404)


class AuditReportViewTests(BaseTestCase):
    def test_wrong_token_404s(self):
        c = Client()
        r = c.get('/chequeo-digital/informe/not-a-real-token/')
        self.assertEqual(r.status_code, 404)

    def test_valid_token_200s_with_score(self):
        audit = ChequeoAudit.objects.create(
            prospect=None, mode='public', stage='confirmado', sector='bar',
            questionnaire_version='v1', answers=[], score=63, category_scores={},
            good_ids=[], fix_ids=['one_tap_contact'],
        )
        c = Client()
        r = c.get(f'/chequeo-digital/informe/{audit.report_token}/')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'63', r.content)

    def test_public_audit_report_never_shows_a_prospect_name(self):
        prospect = BusinessProspect.objects.create(name='Secreta SL', sector='bar')
        other_audit = ChequeoAudit.objects.create(
            prospect=None, mode='public', stage='confirmado', sector='bar',
            questionnaire_version='v1', answers=[], score=50, category_scores={}, good_ids=[], fix_ids=[],
        )
        c = Client()
        r = c.get(f'/chequeo-digital/informe/{other_audit.report_token}/')
        self.assertNotIn(b'Secreta SL', r.content)
        self.assertIsNotNone(prospect)  # solo para dejar constancia de que existe y no debe filtrarse


class AuditReportPdfTests(BaseTestCase):
    def test_wrong_token_404s(self):
        c = Client()
        r = c.get('/chequeo-digital/informe/not-a-real-token/pdf/')
        self.assertEqual(r.status_code, 404)

    def test_valid_token_returns_pdf(self):
        audit = ChequeoAudit.objects.create(
            prospect=None, mode='public', stage='confirmado', sector='bar',
            questionnaire_version='v1', answers=[], score=50, category_scores={}, good_ids=[], fix_ids=[],
        )
        c = Client()
        with mock.patch('prospeccion.pdf.generate_audit_pdf', return_value=b'%PDF-fake'):
            r = c.get(f'/chequeo-digital/informe/{audit.report_token}/pdf/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')


class PersonalModeMusicFullscreenParityTests(BaseTestCase):
    def test_personal_mode_no_longer_disables_music_or_fullscreen(self):
        prospect = BusinessProspect.objects.create(name='Paridad Co', sector='bar')
        c = Client()
        r = c.get(f'/chequeo-digital/e/{prospect.public_token}/')
        html = r.content.decode()
        self.assertNotIn("if(MODE === 'personal') return;\n  var el = document.documentElement;", html)
        self.assertNotIn('.qz-music-btn{display:none}', html)

    def test_has_a_visible_back_to_site_button(self):
        c = Client()
        r = c.get('/chequeo-digital/')
        html = r.content.decode()
        self.assertIn('id="qzBackBtn"', html)
        self.assertIn('href="/"', html)

    def test_result_screen_shows_prospect_name_placeholder(self):
        prospect = BusinessProspect.objects.create(name='Nombrada SL', sector='bar')
        c = Client()
        r = c.get(f'/chequeo-digital/e/{prospect.public_token}/')
        self.assertIn(b'resultEyebrow', r.content)
        self.assertIn(b'data-prospect-name="Nombrada SL"', r.content)
