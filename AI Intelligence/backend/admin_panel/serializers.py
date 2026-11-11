from rest_framework import serializers

from accounts.models import User
from theses.models import Thesis, ThesisReview
from theses.serializers import TagField, ThesisReviewSerializer

from .models import AuditEvent, ModerationItem


class ModerationItemSerializer(serializers.ModelSerializer):
    thesis_title = serializers.CharField(source="thesis.title", read_only=True)
    thesis_author = serializers.CharField(source="thesis.author", read_only=True)
    thesis_department = serializers.CharField(source="thesis.department", read_only=True)
    reporter_name = serializers.CharField(source="reporter.display_name", read_only=True)
    reviewer_name = serializers.CharField(source="reviewer.display_name", read_only=True)

    class Meta:
        model = ModerationItem
        fields = (
            "id",
            "thesis",
            "thesis_title",
            "thesis_author",
            "thesis_department",
            "flag_type",
            "similarity_score",
            "note",
            "reporter",
            "reporter_name",
            "status",
            "reviewer",
            "reviewer_name",
            "created_at",
            "reviewed_at",
        )
        read_only_fields = fields


class ModerationReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["approved", "dismissed"])
    note = serializers.CharField(required=False, allow_blank=True)


class UserAdminSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="display_name", read_only=True)
    joined = serializers.DateTimeField(source="date_joined", read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "name",
            "email",
            "role",
            "status",
            "department",
            "faculty",
            "avatar",
            "joined",
        )
        read_only_fields = ("email", "joined", "avatar")


class UserUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=User.Role.choices, required=False)
    status = serializers.ChoiceField(choices=User.Status.choices, required=False)


class AuditEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.display_name", read_only=True, allow_null=True)

    class Meta:
        model = AuditEvent
        fields = ("id", "actor", "actor_name", "action", "subject_type", "subject_id", "detail", "created_at")
        read_only_fields = fields


class ServiceHealthSerializer(serializers.Serializer):
    db = serializers.CharField()
    storage = serializers.CharField()


class AdminSummarySerializer(serializers.Serializer):
    total_theses = serializers.IntegerField()
    published_theses = serializers.IntegerField()
    draft_theses = serializers.IntegerField()
    restricted_theses = serializers.IntegerField()
    total_users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    suspended_users = serializers.IntegerField()
    pending_moderation = serializers.IntegerField()
    pending_review_theses = serializers.IntegerField()
    pending_access_requests = serializers.IntegerField()
    moderation_by_type = serializers.DictField(child=serializers.IntegerField())
    health = ServiceHealthSerializer()
    recent_activity = AuditEventSerializer(many=True)


class AdminSubmissionSerializer(serializers.ModelSerializer):
    owner_id = serializers.IntegerField(source="owner.id", read_only=True)
    owner_name = serializers.CharField(source="owner.display_name", read_only=True)
    owner_email = serializers.EmailField(source="owner.email", read_only=True)
    tags = TagField(read_only=True)
    file_url = serializers.SerializerMethodField()
    review_history = serializers.SerializerMethodField()

    class Meta:
        model = Thesis
        fields = (
            "id", "title", "author", "owner_id", "owner_name", "owner_email",
            "department", "faculty", "year", "abstract", "supervisor", "tags",
            "status", "access_policy", "file_url", "processing_status", "created_at",
            "review_history",
        )
        read_only_fields = fields

    def get_file_url(self, obj):
        if not obj.file:
            return None
        from django.urls import reverse

        return reverse("thesis-download", args=[obj.pk])

    def get_review_history(self, obj):
        return ThesisReviewSerializer(
            obj.review_history.select_related("reviewer").all(), many=True
        ).data


class AdminSubmissionReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=("approved", "changes_requested", "rejected"))
    comments = serializers.CharField(required=False, allow_blank=True, max_length=10000)

    def validate(self, attrs):
        if attrs["decision"] in ("changes_requested", "rejected") and not attrs.get("comments", "").strip():
            raise serializers.ValidationError(
                {"comments": "Add guidance for the user when requesting changes or rejecting a submission."}
            )
        attrs["comments"] = attrs.get("comments", "").strip()
        return attrs
