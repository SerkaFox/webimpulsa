import shutil
import sqlite3
import tarfile
import tempfile
import zipfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from crm.models import ClientAccess, Lead
from crm.services import (
    ProjectFileError, backup_lead_project, delete_project_path, get_project_root,
    get_sqlite_db_path, list_project_directory, list_server_directories,
    list_sqlite_tables, read_project_text_file, read_sqlite_table, resolve_project_path,
    write_project_text_file, zip_project,
)


def _make_lead(**kwargs):
    kwargs.setdefault('name', 'Cliente de prueba')
    kwargs.setdefault('email', 'cliente@example.com')
    return Lead.objects.create(**kwargs)


def _login_crm(client):
    """Bypass the password form — set the session flag _crm_auth checks for."""
    session = client.session
    session['wi_crm_authed'] = True
    session.save()


def _make_access(lead, pin_required=False):
    return ClientAccess.objects.create(
        lead=lead,
        token='test-token-' + str(lead.pk) + '-' * 20,
        pin_required=pin_required,
        expires_at=timezone.now() + timezone.timedelta(hours=72),
    )


class ProjectFileServiceTests(TestCase):
    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp(prefix='wi_project_test_'))
        (self.project_dir / 'index.html').write_text('<h1>hola</h1>')
        (self.project_dir / 'app.py').write_text('print("hi")')
        (self.project_dir / 'logo.png').write_bytes(b'\x89PNG\r\n fake binary data')
        sub = self.project_dir / 'static'
        sub.mkdir()
        (sub / 'style.css').write_text('body { color: red; }')
        self.lead = _make_lead(project_path=str(self.project_dir))

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_no_project_path_raises(self):
        lead = _make_lead(name='Sin ruta')
        with self.assertRaises(ProjectFileError):
            resolve_project_path(lead, '')

    def test_path_traversal_rejected(self):
        with self.assertRaises(ProjectFileError):
            resolve_project_path(self.lead, '../../etc/passwd')

    def test_absolute_looking_path_is_neutralized_not_escaped(self):
        # An OS-absolute-looking rel_path must still resolve *inside* project_path
        # (leading slashes are stripped, not honored as a real absolute path).
        resolved = resolve_project_path(self.lead, '/etc/passwd')
        self.assertEqual(resolved, self.project_dir.resolve() / 'etc' / 'passwd')

    def test_own_app_base_dir_rejected(self):
        from django.conf import settings
        lead = _make_lead(name='Apunta a la CRM misma', project_path=str(settings.BASE_DIR))
        with self.assertRaises(ProjectFileError):
            get_project_root(lead)

    def test_list_directory_root(self):
        listing = list_project_directory(self.lead, '')
        names = {e['name'] for e in listing['entries']}
        self.assertEqual(names, {'index.html', 'app.py', 'logo.png', 'static'})
        self.assertIsNone(listing['parent_rel'])

    def test_list_directory_editable_flag(self):
        listing = list_project_directory(self.lead, '')
        by_name = {e['name']: e for e in listing['entries']}
        self.assertTrue(by_name['index.html']['editable'])
        self.assertTrue(by_name['app.py']['editable'])
        self.assertFalse(by_name['logo.png']['editable'])
        self.assertTrue(by_name['static']['is_dir'])
        self.assertFalse(by_name['static']['editable'])

    def test_list_subdirectory(self):
        listing = list_project_directory(self.lead, 'static')
        names = {e['name'] for e in listing['entries']}
        self.assertEqual(names, {'style.css'})
        self.assertEqual(listing['parent_rel'], '')

    def test_read_write_text_file_roundtrip(self):
        write_project_text_file(self.lead, 'index.html', '<h1>adios</h1>')
        self.assertEqual(read_project_text_file(self.lead, 'index.html'), '<h1>adios</h1>')

    def test_read_binary_file_rejected(self):
        with self.assertRaises(ProjectFileError):
            read_project_text_file(self.lead, 'logo.png')

    def test_write_outside_allowlist_rejected(self):
        with self.assertRaises(ProjectFileError):
            write_project_text_file(self.lead, 'logo.png', 'oops')

    def test_delete_file(self):
        delete_project_path(self.lead, 'app.py')
        self.assertFalse((self.project_dir / 'app.py').exists())

    def test_delete_directory_recursive(self):
        delete_project_path(self.lead, 'static')
        self.assertFalse((self.project_dir / 'static').exists())

    def test_cannot_delete_project_root(self):
        with self.assertRaises(ProjectFileError):
            delete_project_path(self.lead, '')

    def test_zip_project_contains_files(self):
        buf = zip_project(self.lead)
        with zipfile.ZipFile(buf) as zf:
            names = set(zf.namelist())
        self.assertIn('index.html', names)
        self.assertIn('static/style.css', names)

    def test_zip_project_includes_external_db(self):
        db_dir = Path(tempfile.mkdtemp(prefix='wi_db_test_'))
        try:
            db_file = db_dir / 'db.sqlite3'
            db_file.write_bytes(b'fake sqlite content')
            self.lead.project_db_path = str(db_file)
            self.lead.save(update_fields=['project_db_path'])
            buf = zip_project(self.lead)
            with zipfile.ZipFile(buf) as zf:
                names = set(zf.namelist())
            self.assertIn('database/db.sqlite3', names)
        finally:
            shutil.rmtree(db_dir, ignore_errors=True)


class PortalFileManagerViewTests(TestCase):
    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp(prefix='wi_project_view_test_'))
        (self.project_dir / 'index.html').write_text('<h1>hola</h1>')
        self.lead = _make_lead(project_path=str(self.project_dir))
        self.access = _make_access(self.lead)

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_browse_requires_valid_token(self):
        resp = self.client.get('/p/not-a-real-token/files/')
        self.assertEqual(resp.status_code, 404)

    def test_browse_lists_project_root(self):
        resp = self.client.get(f'/p/{self.access.token}/files/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'index.html')

    def test_download_single_file(self):
        resp = self.client.get(f'/p/{self.access.token}/files/download/?path=index.html')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(b''.join(resp.streaming_content), b'<h1>hola</h1>')

    def test_download_rejects_traversal(self):
        resp = self.client.get(f'/p/{self.access.token}/files/download/?path=../../etc/passwd')
        self.assertEqual(resp.status_code, 404)

    def test_download_zip(self):
        resp = self.client.get(f'/p/{self.access.token}/files/download-all/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/zip')

    def test_edit_get_and_post(self):
        resp = self.client.get(f'/p/{self.access.token}/files/edit/?path=index.html')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['content'], '<h1>hola</h1>')

        resp = self.client.post(
            f'/p/{self.access.token}/files/edit/?path=index.html',
            {'content': '<h1>cambiado</h1>'},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual((self.project_dir / 'index.html').read_text(), '<h1>cambiado</h1>')

    def test_delete_file(self):
        resp = self.client.post(f'/p/{self.access.token}/files/delete/', {'path': 'index.html'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['ok'])
        self.assertFalse((self.project_dir / 'index.html').exists())

    def test_expired_token_blocked(self):
        self.access.expires_at = timezone.now() - timezone.timedelta(hours=1)
        self.access.save(update_fields=['expires_at'])
        resp = self.client.get(f'/p/{self.access.token}/files/download/?path=index.html')
        self.assertEqual(resp.status_code, 404)

    def test_pin_required_blocks_until_verified(self):
        access = _make_access(_make_lead(name='Con PIN', project_path=str(self.project_dir)), pin_required=True)
        resp = self.client.post(f'/p/{access.token}/files/delete/', {'path': 'index.html'})
        self.assertEqual(resp.status_code, 403)
        # file untouched
        self.assertTrue((self.project_dir / 'index.html').exists())


class BackupClientProjectsCommandTests(TestCase):
    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp(prefix='wi_project_backup_test_'))
        (self.project_dir / 'index.html').write_text('<h1>hola</h1>')
        self.media_root = Path(tempfile.mkdtemp(prefix='wi_media_backup_test_'))
        self.lead = _make_lead(project_path=str(self.project_dir))

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_creates_snapshot_with_project_contents(self):
        with self.settings(MEDIA_ROOT=self.media_root):
            call_command('backup_client_projects', stdout=StringIO())
        snap_dir = self.media_root / 'client_backups' / str(self.lead.pk)
        snapshots = list(snap_dir.glob('snapshot_*.tar.gz'))
        self.assertEqual(len(snapshots), 1)
        with tarfile.open(snapshots[0]) as tar:
            names = tar.getnames()
        self.assertIn('project/index.html', names)

    def test_prunes_to_three_most_recent(self):
        snap_dir = self.media_root / 'client_backups' / str(self.lead.pk)
        snap_dir.mkdir(parents=True)
        for i in range(5):
            (snap_dir / f'snapshot_2026010{i}_000000.tar.gz').write_bytes(b'old')

        with self.settings(MEDIA_ROOT=self.media_root):
            call_command('backup_client_projects', stdout=StringIO())

        snapshots = sorted(snap_dir.glob('snapshot_*.tar.gz'))
        self.assertEqual(len(snapshots), 3)
        # the two oldest fake snapshots must be gone
        self.assertFalse((snap_dir / 'snapshot_20260100_000000.tar.gz').exists())
        self.assertFalse((snap_dir / 'snapshot_20260101_000000.tar.gz').exists())

    def test_skips_lead_without_project_path(self):
        _make_lead(name='Sin ruta')
        with self.settings(MEDIA_ROOT=self.media_root):
            err = StringIO()
            call_command('backup_client_projects', stdout=StringIO(), stderr=err)
        self.assertEqual(err.getvalue(), '')

    def test_bad_project_path_does_not_crash_other_leads(self):
        _make_lead(name='Ruta inexistente', project_path='/no/existe/de/verdad')
        with self.settings(MEDIA_ROOT=self.media_root):
            call_command('backup_client_projects', stdout=StringIO(), stderr=StringIO())
        snap_dir = self.media_root / 'client_backups' / str(self.lead.pk)
        self.assertEqual(len(list(snap_dir.glob('snapshot_*.tar.gz'))), 1)


class ServerFolderPickerTests(TestCase):
    """list_server_directories is scoped to /home/seradmin — can't easily
    sandbox that root in tests, so we only exercise it against real,
    always-present paths (the CRM app's own worktree lives under there)."""

    def test_lists_directories_only(self):
        from django.conf import settings
        rel = str(Path(settings.BASE_DIR).parent.relative_to('/home/seradmin'))
        listing = list_server_directories(rel)
        self.assertIn('entries', listing)
        for entry in listing['entries']:
            self.assertNotIn('.', entry['name'][1:])  # sanity: looks like a dir name, not a stray file check
        names = {e['name'] for e in listing['entries']}
        self.assertIn(Path(settings.BASE_DIR).name, names)

    def test_root_listing_has_no_parent(self):
        listing = list_server_directories('')
        self.assertIsNone(listing['parent_rel'])

    def test_traversal_outside_root_rejected(self):
        with self.assertRaises(ProjectFileError):
            list_server_directories('../../etc')

    def test_browse_fs_endpoint_requires_crm_login(self):
        resp = self.client.get('/wi/crm/browse-fs/?path=')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'crm_password', resp.content)  # login form, not the JSON listing


class SqliteBrowserTests(TestCase):
    def setUp(self):
        self.db_dir = Path(tempfile.mkdtemp(prefix='wi_sqlite_test_'))
        self.db_path = self.db_dir / 'db.sqlite3'
        con = sqlite3.connect(self.db_path)
        con.execute('CREATE TABLE clientes (id INTEGER PRIMARY KEY, nombre TEXT)')
        for i in range(5):
            con.execute('INSERT INTO clientes (nombre) VALUES (?)', (f'Cliente {i}',))
        con.commit()
        con.close()
        self.lead = _make_lead(project_db_path=str(self.db_path))
        self.access = _make_access(self.lead)

    def tearDown(self):
        shutil.rmtree(self.db_dir, ignore_errors=True)

    def test_no_db_path_raises(self):
        lead = _make_lead(name='Sin BD')
        with self.assertRaises(ProjectFileError):
            get_sqlite_db_path(lead)

    def test_list_tables(self):
        self.assertEqual(list_sqlite_tables(self.lead), ['clientes'])

    def test_read_table_rows(self):
        data = read_sqlite_table(self.lead, 'clientes')
        self.assertEqual(data['total'], 5)
        self.assertEqual(data['columns'], ['id', 'nombre'])
        self.assertEqual(len(data['rows']), 5)

    def test_read_unknown_table_rejected(self):
        with self.assertRaises(ProjectFileError):
            read_sqlite_table(self.lead, 'usuarios_secretos')

    def test_read_table_injection_attempt_rejected(self):
        with self.assertRaises(ProjectFileError):
            read_sqlite_table(self.lead, 'clientes"; DROP TABLE clientes;--')

    def test_connection_is_read_only(self):
        # even if somehow called with a real table name, the connection itself
        # must refuse writes — belt-and-suspenders on top of the whitelist.
        import sqlite3 as sq
        con = sq.connect(f'file:{self.db_path}?mode=ro', uri=True)
        with self.assertRaises(sq.OperationalError):
            con.execute("INSERT INTO clientes (nombre) VALUES ('hack')")
        con.close()

    def test_portal_database_view_lists_tables(self):
        resp = self.client.get(f'/p/{self.access.token}/database/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'clientes')

    def test_portal_database_table_view(self):
        resp = self.client.get(f'/p/{self.access.token}/database/table/clientes/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Cliente 0')

    def test_portal_database_table_injection_via_url_rejected(self):
        resp = self.client.get(f'/p/{self.access.token}/database/table/no_existe/')
        self.assertEqual(resp.status_code, 200)  # error rendered inline, not a crash
        self.assertContains(resp, 'no existe')

    def test_portal_database_download(self):
        resp = self.client.get(f'/p/{self.access.token}/database/download/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/x-sqlite3')


class BackupNowEndpointTests(TestCase):
    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp(prefix='wi_project_backupnow_test_'))
        (self.project_dir / 'index.html').write_text('<h1>hola</h1>')
        self.media_root = Path(tempfile.mkdtemp(prefix='wi_media_backupnow_test_'))
        self.lead = _make_lead(project_path=str(self.project_dir))
        _login_crm(self.client)

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_backup_now_creates_snapshot(self):
        with self.settings(MEDIA_ROOT=self.media_root):
            resp = self.client.post(f'/wi/crm/{self.lead.pk}/backup-now/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['ok'])
        snap_dir = self.media_root / 'client_backups' / str(self.lead.pk)
        self.assertEqual(len(list(snap_dir.glob('snapshot_*.tar.gz'))), 1)

    def test_backup_now_without_project_path_errors(self):
        lead = _make_lead(name='Sin ruta')
        with self.settings(MEDIA_ROOT=self.media_root):
            resp = self.client.post(f'/wi/crm/{lead.pk}/backup-now/')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['ok'])

    def test_saving_new_project_path_triggers_immediate_backup(self):
        lead = _make_lead(name='Nuevo cliente')
        with self.settings(MEDIA_ROOT=self.media_root):
            resp = self.client.post(f'/wi/crm/{lead.pk}/', {
                'status': lead.status,
                'preferred_channel': lead.preferred_channel,
                'notes': '',
                'project_path': str(self.project_dir),
                'project_db_path': '',
            })
        self.assertEqual(resp.status_code, 200)
        snap_dir = self.media_root / 'client_backups' / str(lead.pk)
        self.assertEqual(len(list(snap_dir.glob('snapshot_*.tar.gz'))), 1)
