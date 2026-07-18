import secrets

from django.contrib.auth.hashers import make_password
from django.db import migrations


def backfill(apps, schema_editor):
    Girl = apps.get_model('planner', 'Girl')
    CalendarEntry = apps.get_model('planner', 'CalendarEntry')

    tatiana, _ = Girl.objects.get_or_create(
        name='Tatiana',
        defaults={
            'password': make_password('tatiana2026'),
            'token': secrets.token_urlsafe(32),
        },
    )
    CalendarEntry.objects.filter(girl__isnull=True).update(girl=tatiana)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0003_girl_calendarentry_girl'),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
