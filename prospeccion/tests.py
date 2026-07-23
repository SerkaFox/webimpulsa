import json
import os
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from crm.models import Lead, Proposal
from .csv_import import parse_csv
from .models import BusinessContact, BusinessProspect, ChequeoAudit, StaffMember
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
