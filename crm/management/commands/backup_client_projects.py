"""Rolling 3-snapshot backup of every client's live project (code + database).

Meant to run on a daily cron. For each crm.Lead that has project_path set:
  1. Tar the project folder (+ project_db_path, if set and outside project_path)
     into media/client_backups/<lead_id>/snapshot_<timestamp>.tar.gz
  2. Keep only the 3 most recent snapshots per lead, deleting older ones.

This is the safety net behind the client file manager (crm/services.py),
which edits/deletes the LIVE project files directly by design — a mistake
made there is recoverable from here, up to 3 generations back.
"""
import tarfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from crm.models import Lead
from crm.services import ProjectFileError, get_project_root

KEEP_SNAPSHOTS = 3


class Command(BaseCommand):
    help = "Rolling 3-snapshot backup (code + DB) for every client with a project_path set."

    def handle(self, *args, **options):
        leads = Lead.objects.exclude(project_path='')
        if not leads:
            self.stdout.write('No leads have a project_path configured — nothing to back up.')
            return

        for lead in leads:
            try:
                self._backup_lead(lead)
            except ProjectFileError as exc:
                self.stderr.write(f'Lead #{lead.pk} ({lead.name}): {exc}')
            except Exception as exc:  # one client's failure must not stop the rest
                self.stderr.write(f'Lead #{lead.pk} ({lead.name}): unexpected error: {exc}')

    def _backup_lead(self, lead: Lead) -> None:
        root = get_project_root(lead)

        dest_dir = Path(settings.MEDIA_ROOT) / 'client_backups' / str(lead.pk)
        dest_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        snapshot_path = dest_dir / f'snapshot_{timestamp}.tar.gz'

        with tarfile.open(snapshot_path, 'w:gz') as tar:
            tar.add(root, arcname='project')
            if lead.project_db_path:
                db_path = Path(lead.project_db_path).resolve()
                if db_path.is_file() and root not in db_path.parents:
                    tar.add(db_path, arcname=f'database/{db_path.name}')

        self._prune_old_snapshots(dest_dir)
        self.stdout.write(f'Lead #{lead.pk} ({lead.name}): snapshot saved → {snapshot_path.name}')

    def _prune_old_snapshots(self, dest_dir: Path) -> None:
        snapshots = sorted(dest_dir.glob('snapshot_*.tar.gz'), key=lambda p: p.name)
        for old in snapshots[:-KEEP_SNAPSHOTS]:
            old.unlink()
