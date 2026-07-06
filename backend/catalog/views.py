import threading
import uuid
from datetime import timezone

from django.db.models import Q
from django.utils import timezone as dj_timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import (
    Entity,
    EntityType,
    IdentifiableInfo,
    IdentifiableInfoBooster,
    Relationship,
    RelationType,
    Tag,
    TaskStatus,
    Term,
)
from .serializers import (
    BoosterSerializer,
    DescriptionUpdateSerializer,
    EntityChildSerializer,
    EntityDetailSerializer,
    EntityListSerializer,
    TagCreateSerializer,
    TagSerializer,
    TaskRunSerializer,
    TaskStatusSerializer,
    TermSerializer,
)


class EntityViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for browsing entities."""
    permission_classes = [AllowAny]
    lookup_field = "fqn"
    lookup_value_regex = "[^/]+"

    def get_queryset(self):
        return Entity.objects.all()

    def get_serializer_class(self):
        if self.action == "retrieve":
            return EntityDetailSerializer
        return EntityListSerializer

    def get_object(self):
        fqn = self.kwargs["fqn"]
        return Entity.objects.get(fqn=fqn)

    @action(detail=True, methods=["get"], url_path="children")
    def children(self, request, fqn=None):
        """Get child entities of a given entity."""
        entity = Entity.objects.filter(fqn=fqn).first()
        if not entity:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        children = Entity.objects.filter(
            incoming_relationships__from_entity=entity,
            incoming_relationships__relation=RelationType.CONTAINS,
        ).select_related("identifiable_info").order_by("name")

        serializer = EntityChildSerializer(children, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get", "post"], url_path="tags")
    def tags(self, request, fqn=None):
        """Get or add tags for an entity."""
        entity = Entity.objects.filter(fqn=fqn).first()
        if not entity:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.method == "GET":
            tags = Tag.objects.filter(entity=entity)
            serializer = TagSerializer(tags, many=True)
            return Response(serializer.data)

        serializer = TagCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tag, created = Tag.objects.get_or_create(
            entity=entity,
            key=serializer.validated_data["key"],
            value=serializer.validated_data.get("value", ""),
        )
        return Response(TagSerializer(tag).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=["delete"], url_path="tags/(?P<tag_id>[0-9]+)")
    def remove_tag(self, request, fqn=None, tag_id=None):
        """Remove a tag from an entity."""
        deleted, _ = Tag.objects.filter(entity__fqn=fqn, id=tag_id).delete()
        if deleted:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=["put"], url_path="description")
    def update_description(self, request, fqn=None):
        """Update entity description."""
        entity = Entity.objects.filter(fqn=fqn).first()
        if not entity:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = DescriptionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity.description = serializer.validated_data["description"]
        entity.save(update_fields=["description", "updated_at"])
        return Response({"description": entity.description})

    @action(detail=True, methods=["get"], url_path="terms")
    def terms(self, request, fqn=None):
        """Get terms for an entity."""
        entity = Entity.objects.filter(fqn=fqn).first()
        if not entity:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        terms = Term.objects.filter(entity=entity).exclude(term_type="sentinel")
        serializer = TermSerializer(terms, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="phi")
    def phi_info(self, request, fqn=None):
        """Get PHI/PII info and boosters for an entity."""
        entity = Entity.objects.filter(fqn=fqn).first()
        if not entity:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        info = IdentifiableInfo.objects.filter(entity=entity).first()
        boosters = IdentifiableInfoBooster.objects.filter(primary_entity=entity)

        return Response({
            "info": {
                "phi_score": info.phi_score if info else 0,
                "pii_score": info.pii_score if info else 0,
                "pass_stage": info.pass_stage if info else 0,
            },
            "boosters": BoosterSerializer(boosters, many=True).data,
        })


@api_view(["GET"])
@permission_classes([AllowAny])
def schema_list(request):
    """List all schema entities."""
    schemas = Entity.objects.filter(entity_type=EntityType.SCHEMA).order_by("name")
    serializer = EntityListSerializer(schemas, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def schema_children(request, schema_name):
    """List tables/views in a schema (by schema name)."""
    schema = Entity.objects.filter(entity_type=EntityType.SCHEMA, name=schema_name).first()
    if not schema:
        return Response({"detail": "Schema not found."}, status=status.HTTP_404_NOT_FOUND)

    children = Entity.objects.filter(
        incoming_relationships__from_entity=schema,
        incoming_relationships__relation=RelationType.CONTAINS,
    ).order_by("name")

    serializer = EntityChildSerializer(children, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def search_entities(request):
    """Search tables/views by name pattern."""
    q = request.query_params.get("q", "").strip()
    if not q:
        return Response([])

    results = Entity.objects.filter(
        entity_type__in=[EntityType.TABLE, EntityType.VIEW],
        name__icontains=q,
    ).order_by("fqn")[:100]

    serializer = EntityListSerializer(results, many=True)
    return Response(serializer.data)


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def task_list(request):
    """List tasks or trigger a new task."""
    if request.method == "GET":
        tasks = TaskStatus.objects.all()[:20]
        serializer = TaskStatusSerializer(tasks, many=True)
        available_tasks = [
            {"name": "refresh_schemas", "description": "Refresh schema list from Redshift (lightweight)"},
            {"name": "fetch_schema", "description": "Fetch full Redshift metadata (schemas + tables + columns)"},
            {"name": "compute_terms", "description": "Compute terms for entities"},
            {"name": "classify_phi", "description": "Classify entities for PHI/PII"},
        ]
        return Response({"available": available_tasks, "recent": serializer.data})

    serializer = TaskRunSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    task_name = serializer.validated_data["task_name"]
    task_status = TaskStatus.objects.create(
        task_name=task_name,
        state=TaskStatus.State.RUNNING,
        started_at=dj_timezone.now(),
    )

    def run_task():
        from django.core.management import call_command
        try:
            kwargs = {}
            schema = serializer.validated_data.get("schema")
            if schema:
                kwargs["schema"] = schema
            if serializer.validated_data.get("recompute"):
                kwargs["recompute"] = True
            kwargs["workers"] = serializer.validated_data.get("workers", 4)

            call_command(task_name, **kwargs)

            task_status.state = TaskStatus.State.COMPLETED
            task_status.completed_at = dj_timezone.now()
            task_status.save()
        except Exception as e:
            task_status.state = TaskStatus.State.FAILED
            task_status.message = str(e)
            task_status.completed_at = dj_timezone.now()
            task_status.save()

    thread = threading.Thread(target=run_task, daemon=True)
    thread.start()

    return Response(TaskStatusSerializer(task_status).data, status=status.HTTP_202_ACCEPTED)


@api_view(["GET"])
@permission_classes([AllowAny])
def task_detail(request, task_id):
    """Get task status by ID."""
    try:
        task = TaskStatus.objects.get(id=task_id)
    except TaskStatus.DoesNotExist:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    serializer = TaskStatusSerializer(task)
    return Response(serializer.data)
