from rest_framework import serializers

from .models import (
    Entity,
    IdentifiableInfo,
    IdentifiableInfoBooster,
    Relationship,
    Tag,
    TaskStatus,
    Term,
)


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "key", "value", "created_at"]


class TermSerializer(serializers.ModelSerializer):
    class Meta:
        model = Term
        fields = ["id", "term_name", "term_type", "score", "pass_stage", "created_at"]


class IdentifiableInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = IdentifiableInfo
        fields = ["phi_score", "pii_score", "pass_stage", "updated_at"]


class BoosterSerializer(serializers.ModelSerializer):
    secondary_entity_fqn = serializers.CharField(source="secondary_entity.fqn", read_only=True)

    class Meta:
        model = IdentifiableInfoBooster
        fields = ["id", "secondary_entity_fqn", "boost_type", "boost_score"]


class EntityListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entity
        fields = ["id", "fqn", "name", "entity_type", "updated_at"]


class EntityDetailSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True, read_only=True)
    terms = TermSerializer(many=True, read_only=True)
    identifiable_info = IdentifiableInfoSerializer(read_only=True)

    class Meta:
        model = Entity
        fields = [
            "id", "fqn", "name", "entity_type", "description",
            "metadata", "created_at", "updated_at",
            "tags", "terms", "identifiable_info",
        ]


class EntityChildSerializer(serializers.ModelSerializer):
    phi_score = serializers.SerializerMethodField()
    pii_score = serializers.SerializerMethodField()

    class Meta:
        model = Entity
        fields = ["id", "fqn", "name", "entity_type", "metadata", "phi_score", "pii_score"]

    def get_phi_score(self, obj):
        info = getattr(obj, 'identifiable_info', None)
        if info is None:
            try:
                info = obj.identifiable_info
            except Exception:
                return 0
        return info.phi_score if info else 0

    def get_pii_score(self, obj):
        info = getattr(obj, 'identifiable_info', None)
        if info is None:
            try:
                info = obj.identifiable_info
            except Exception:
                return 0
        return info.pii_score if info else 0


class RelationshipSerializer(serializers.ModelSerializer):
    from_fqn = serializers.CharField(source="from_entity.fqn", read_only=True)
    to_fqn = serializers.CharField(source="to_entity.fqn", read_only=True)

    class Meta:
        model = Relationship
        fields = ["id", "from_fqn", "to_fqn", "from_entity_type", "to_entity_type", "relation"]


class TaskStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskStatus
        fields = [
            "id", "task_name", "state",
            "progress_current", "progress_total", "message",
            "started_at", "completed_at", "created_at",
        ]


class TaskRunSerializer(serializers.Serializer):
    task_name = serializers.ChoiceField(choices=["fetch_schema", "compute_terms", "classify_phi"])
    schema = serializers.CharField(required=False, allow_blank=True, default="")
    recompute = serializers.BooleanField(required=False, default=False)
    workers = serializers.IntegerField(required=False, default=4, min_value=1, max_value=16)


class TagCreateSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=256)
    value = serializers.CharField(max_length=1024, required=False, allow_blank=True, default="")


class DescriptionUpdateSerializer(serializers.Serializer):
    description = serializers.CharField(allow_blank=True)
