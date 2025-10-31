from django.db import migrations, models
from django.utils import timezone

def backfill_entry_timestamps(apps, schema_editor):
    ScheduleEntry = apps.get_model("scheduler", "ScheduleEntry")
    now = timezone.now()
    # backfill NULLs so we can drop null=True afterward
    ScheduleEntry.objects.filter(created_at__isnull=True).update(created_at=now)
    ScheduleEntry.objects.filter(updated_at__isnull=True).update(updated_at=now)

class Migration(migrations.Migration):
    # IMPORTANT: set this to your latest scheduler migration
    dependencies = [
        ("scheduler", "0001_initial"),  # <-- change to your last migration filename
    ]

    operations = [
        migrations.AddField(
            model_name="scheduleentry",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, db_index=True, null=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="scheduleentry",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True, null=True),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_entry_timestamps, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="scheduleentry",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        migrations.AlterField(
            model_name="scheduleentry",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
    ]
