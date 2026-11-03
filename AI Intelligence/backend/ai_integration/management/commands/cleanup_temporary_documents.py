"""Django management command to clean up expired temporary PDF documents.

Deletes temporary documents identified by the ``tmp-pdf-`` backend_thesis_id
prefix that are older than 24 hours and in a terminal ingestion state
(success or failed). Permanent repository theses are never affected.

Safe to run on a schedule (e.g. daily cron):

    python manage.py cleanup_temporary_documents

The command is idempotent and logs every deletion, skip, and error.
"""

from django.core.management.base import BaseCommand

from ai_integration.services import forward_to_v2, get_internal_service_token


class Command(BaseCommand):
    help = "Clean up expired temporary PDF documents (tmp-pdf- prefix)."

    def handle(self, *args, **options):
        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            self.stderr.write(str(exc))
            return

        # Build a minimal actor context for the cleanup operation.
        # The V2 endpoint requires admin role, so we use the system user if
        # available; otherwise the command reports that admin auth is needed.
        from django.contrib.auth import get_user_model

        User = get_user_model()
        admin_user = User.objects.filter(role="admin").first()
        if not admin_user:
            self.stderr.write(
                "No admin user found; cannot authenticate cleanup request."
            )
            return

        actor_context = {
            "user_id": str(admin_user.id),
            "roles": admin_user.role,
            "department": admin_user.department or "",
            "trace_id": f"cleanup-{__import__('uuid').uuid4()}",
        }

        try:
            result = forward_to_v2(
                method="DELETE",
                path="/api/v2/documents/cleanup-temporary",
                actor_context=actor_context,
                internal_token=internal_token,
            )
        except ValueError as exc:
            self.stderr.write(f"Cleanup failed: {exc}")
            return

        self.stdout.write(
            f"Temporary document cleanup complete: "
            f"{result.get('cleaned', 0)} cleaned, "
            f"{result.get('skipped', 0)} skipped, "
            f"{result.get('errors', 0)} errors."
        )

        for detail in result.get("error_details", []):
            self.stderr.write(f"  Cleanup error: {detail}")
