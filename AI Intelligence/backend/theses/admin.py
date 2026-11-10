import json

from django.contrib import admin
from django.contrib import messages

from ai_integration.services import (
    build_actor_context,
    derive_access_level,
    forward_to_v2,
    get_internal_service_token,
)
from .models import AccessRequest, SavedThesis, Tag, Thesis


class ThesisAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "department", "year", "status", "access_policy", "processing_status")
    list_filter = ("status", "access_policy", "processing_status", "department", "faculty")
    search_fields = ("title", "author", "abstract")
    filter_horizontal = ("tags",)
    actions = ("index_with_ai", "refresh_ai_index_status")

    @admin.action(description="Index published theses with AI")
    def index_with_ai(self, request, queryset):
        if request.user.role != "admin" and not request.user.is_superuser:
            self.message_user(
                request,
                "Only an administrator can start AI indexing.",
                level=messages.ERROR,
            )
            return

        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return

        for thesis in queryset.select_related("owner"):
            if thesis.status != Thesis.Status.PUBLISHED:
                self.message_user(
                    request,
                    f"{thesis.title}: publish the thesis before AI indexing.",
                    level=messages.WARNING,
                )
                continue
            if not thesis.file:
                self.message_user(
                    request,
                    f"{thesis.title}: no PDF is attached.",
                    level=messages.ERROR,
                )
                continue

            try:
                access_level = derive_access_level(thesis.id, request.user)
                if access_level is None:
                    raise ValueError("You cannot index this thesis.")

                metadata = {
                    "title": thesis.title,
                    "author": thesis.author,
                    "department": thesis.department,
                    "faculty": thesis.faculty,
                    "supervisor": thesis.supervisor,
                    "abstract": thesis.abstract,
                    "year": thesis.year,
                    "indexed_by_admin_id": str(request.user.id),
                }
                filename = thesis.file.name.rsplit("/", 1)[-1]

                # V2 records the actor as the document owner; issue this trusted
                # server-side request as the thesis owner to preserve ACLs.
                with thesis.file.open("rb") as pdf_file:
                    result = forward_to_v2(
                        method="POST",
                        path="/api/v2/documents/upload",
                        actor_context=build_actor_context(thesis.owner),
                        internal_token=internal_token,
                        data={
                            "backend_thesis_id": str(thesis.id),
                            "backend_user_id": str(thesis.owner_id),
                            "access_level": access_level,
                            "thesis_metadata": json.dumps(metadata),
                        },
                        files={
                            "file": (filename, pdf_file, "application/pdf")
                        },
                        timeout=120,
                    )

                job_id = result.get("job_id")
                if not job_id:
                    raise ValueError("V2 accepted the file but returned no job ID.")

                thesis.ai_job_id = str(job_id)
                thesis.processing_status = Thesis.ProcessingStatus.QUEUED
                thesis.save(update_fields=["ai_job_id", "processing_status", "updated_at"])
                self.message_user(
                    request,
                    f"{thesis.title}: AI indexing queued (job {job_id}).",
                    level=messages.SUCCESS,
                )
            except Exception as exc:
                self.message_user(
                    request,
                    f"{thesis.title}: AI indexing could not be queued: {exc}",
                    level=messages.ERROR,
                )

    @admin.action(description="Refresh AI indexing status")
    def refresh_ai_index_status(self, request, queryset):
        if request.user.role != "admin" and not request.user.is_superuser:
            self.message_user(
                request,
                "Only an administrator can refresh AI indexing status.",
                level=messages.ERROR,
            )
            return

        try:
            internal_token = get_internal_service_token()
        except ValueError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return

        status_map = {
            "pending": Thesis.ProcessingStatus.QUEUED,
            "processing": Thesis.ProcessingStatus.PROCESSING,
            "success": Thesis.ProcessingStatus.COMPLETED,
            "completed": Thesis.ProcessingStatus.COMPLETED,
            "failed": Thesis.ProcessingStatus.FAILED,
        }

        for thesis in queryset.select_related("owner"):
            if not thesis.ai_job_id:
                self.message_user(
                    request,
                    f"{thesis.title}: no AI job is recorded; index it first.",
                    level=messages.WARNING,
                )
                continue

            try:
                result = forward_to_v2(
                    method="GET",
                    path=f"/api/v2/documents/jobs/{thesis.ai_job_id}",
                    actor_context=build_actor_context(request.user),
                    internal_token=internal_token,
                )
                next_status = status_map.get(result.get("status"))
                if next_status is None:
                    raise ValueError("V2 returned an unknown ingestion status.")

                thesis.processing_status = next_status
                thesis.save(update_fields=["processing_status", "updated_at"])
                message = f"{thesis.title}: AI indexing is {next_status}."
                if result.get("error_message"):
                    message = f"{message} {result['error_message']}"
                self.message_user(
                    request,
                    message,
                    level=(
                        messages.ERROR
                        if next_status == Thesis.ProcessingStatus.FAILED
                        else messages.SUCCESS
                    ),
                )
            except Exception as exc:
                self.message_user(
                    request,
                    f"{thesis.title}: AI status could not be refreshed: {exc}",
                    level=messages.ERROR,
                )


admin.site.register(Thesis, ThesisAdmin)
admin.site.register(Tag)
admin.site.register(SavedThesis)
admin.site.register(AccessRequest)