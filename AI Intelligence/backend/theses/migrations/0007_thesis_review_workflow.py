import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("theses", "0007_thesis_ai_job_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="thesis",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("pending_review", "Pending review"),
                    ("changes_requested", "Changes requested"),
                    ("rejected", "Rejected"),
                    ("processing", "Processing"),
                    ("published", "Published"),
                    ("flagged", "Flagged"),
                ],
                default="draft",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="ThesisReview",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "decision",
                    models.CharField(
                        choices=[
                            ("approved", "Approved"),
                            ("changes_requested", "Changes requested"),
                            ("rejected", "Rejected"),
                        ],
                        max_length=24,
                    ),
                ),
                ("comments", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "reviewer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="thesis_reviews",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "thesis",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="review_history",
                        to="theses.thesis",
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddIndex(
            model_name="thesisreview",
            index=models.Index(fields=["decision", "created_at"], name="theses_th_decisi_739aba_idx"),
        ),
    ]
