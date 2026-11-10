from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("theses", "0006_thesis_downloads"),
    ]

    operations = [
        migrations.AddField(
            model_name="thesis",
            name="ai_job_id",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]