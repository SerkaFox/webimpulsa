import random
from django.db import migrations, models


def _unique_short_id(used):
    while True:
        val = str(random.randint(100000, 999999))
        if val not in used:
            used.add(val)
            return val


def populate_short_ids(apps, schema_editor):
    ChatSession = apps.get_model('core', 'ChatSession')
    used = set()
    for session in ChatSession.objects.filter(short_id__isnull=True):
        session.short_id = _unique_short_id(used)
        session.save(update_fields=['short_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        # Step 1: add nullable (avoids unique conflict on existing rows)
        migrations.AddField(
            model_name='chatsession',
            name='short_id',
            field=models.CharField(max_length=8, null=True, blank=True),
        ),
        # Step 2: fill existing rows with unique values
        migrations.RunPython(populate_short_ids, migrations.RunPython.noop),
        # Step 3: make non-null + unique
        migrations.AlterField(
            model_name='chatsession',
            name='short_id',
            field=models.CharField(max_length=8, unique=True),
        ),
    ]
