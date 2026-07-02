from django.contrib import admin

from .models import (
    Entity,
    IdentifiableInfo,
    IdentifiableInfoBooster,
    Relationship,
    Tag,
    TaskStatus,
    Term,
)


class TagInline(admin.TabularInline):
    model = Tag
    extra = 0


class TermInline(admin.TabularInline):
    model = Term
    extra = 0


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display = ["fqn", "entity_type", "name", "updated_at"]
    list_filter = ["entity_type"]
    search_fields = ["fqn", "name"]
    inlines = [TagInline, TermInline]


@admin.register(Relationship)
class RelationshipAdmin(admin.ModelAdmin):
    list_display = ["from_entity", "relation", "to_entity"]
    list_filter = ["relation", "from_entity_type", "to_entity_type"]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["entity", "key", "value", "created_at"]
    search_fields = ["entity__fqn", "key", "value"]


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ["entity", "term_name", "term_type", "score", "pass_stage"]
    list_filter = ["term_type", "pass_stage"]
    search_fields = ["entity__fqn", "term_name"]


@admin.register(IdentifiableInfo)
class IdentifiableInfoAdmin(admin.ModelAdmin):
    list_display = ["entity", "phi_score", "pii_score", "pass_stage", "updated_at"]
    list_filter = ["pass_stage"]


@admin.register(IdentifiableInfoBooster)
class IdentifiableInfoBoosterAdmin(admin.ModelAdmin):
    list_display = ["primary_entity", "secondary_entity", "boost_type", "boost_score"]
    list_filter = ["boost_type"]


@admin.register(TaskStatus)
class TaskStatusAdmin(admin.ModelAdmin):
    list_display = ["task_name", "state", "progress_current", "progress_total", "started_at", "completed_at"]
    list_filter = ["state", "task_name"]
