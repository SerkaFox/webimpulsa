"""Rolling 3-snapshot backup of every client's live project (code + database).

Meant to run on a weekly cron. For each crm.Lead that has project_path set,
delegates to crm.services.backup_lead_project — the same function the CRM's
"backup now" button calls on demand, so both paths stay in sync.

This is the safety net behind the client file manager (crm/services.py),
which edits/deletes the LIVE project files directly by design — a mistake
made there is recoverable from here, up to 3 generations back.
"""
from django.core.management.base import BaseCommand

from crm.models import Lead
from crm.services import ProjectFileError, backup_lead_project


class Command(BaseCommand):
    help = "Rolling 3-snapshot backup (code + DB) for every client with a project_path set."

    def handle(self, *args, **options):
        leads = Lead.objects.exclude(project_path='')
        if not leads:
            self.stdout.write('No leads have a project_path configured — nothing to back up.')
            return

        for lead in leads:
            try:
                snapshot_path = backup_lead_project(lead)
                self.stdout.write(f'Lead #{lead.pk} ({lead.name}): snapshot saved → {snapshot_path.name}')
            except ProjectFileError as exc:
                self.stderr.write(f'Lead #{lead.pk} ({lead.name}): {exc}')
            except Exception as exc:  # one client's failure must not stop the rest
                self.stderr.write(f'Lead #{lead.pk} ({lead.name}): unexpected error: {exc}')
