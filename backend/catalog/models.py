import uuid

from django.db import models


class EntityType(models.TextChoices):
    DATABASE = "DATABASE"
    SCHEMA = "SCHEMA"
    TABLE = "TABLE"
    VIEW = "VIEW"
    COLUMN = "COLUMN"


class RelationType(models.TextChoices):
    CONTAINS = "CONTAINS"
    BELONGS_TO = "BELONGS_TO"


class Entity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fqn = models.CharField(max_length=1024, unique=True, db_index=True)
    name = models.CharField(max_length=512)
    entity_type = models.CharField(max_length=20, choices=EntityType.choices, db_index=True)
    description = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fqn"]
        verbose_name_plural = "entities"

    def __str__(self):
        return f"{self.entity_type}:{self.fqn}"


class Relationship(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_entity = models.ForeignKey(
        Entity, on_delete=models.CASCADE, related_name="outgoing_relationships"
    )
    to_entity = models.ForeignKey(
        Entity, on_delete=models.CASCADE, related_name="incoming_relationships"
    )
    from_entity_type = models.CharField(max_length=20, choices=EntityType.choices)
    to_entity_type = models.CharField(max_length=20, choices=EntityType.choices)
    relation = models.CharField(max_length=20, choices=RelationType.choices)

    class Meta:
        unique_together = [("from_entity", "to_entity", "relation")]

    def __str__(self):
        return f"{self.from_entity.fqn} -{self.relation}-> {self.to_entity.fqn}"


class Tag(models.Model):
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="tags")
    key = models.CharField(max_length=256)
    value = models.CharField(max_length=1024, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("entity", "key", "value")]

    def __str__(self):
        return f"{self.entity.fqn}:{self.key}={self.value}"


class TermType(models.TextChoices):
    BUSINESS = "business"
    OPERATIONS = "operations"
    LANGUAGE = "language"
    SENTINEL = "sentinel"


class Term(models.Model):
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="terms")
    term_name = models.CharField(max_length=256)
    term_type = models.CharField(max_length=20, choices=TermType.choices, default=TermType.LANGUAGE)
    score = models.IntegerField(default=0)
    pass_stage = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("entity", "term_name", "term_type")]
        ordering = ["-score", "term_name"]

    def __str__(self):
        return f"{self.entity.fqn}:{self.term_name}({self.term_type})={self.score}"


class IdentifiableInfo(models.Model):
    entity = models.OneToOneField(Entity, on_delete=models.CASCADE, primary_key=True, related_name="identifiable_info")
    phi_score = models.IntegerField(default=0)
    pii_score = models.IntegerField(default=0)
    pass_stage = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "identifiable info"
        verbose_name_plural = "identifiable info"

    def __str__(self):
        return f"{self.entity.fqn}: PHI={self.phi_score} PII={self.pii_score}"


class IdentifiableInfoBooster(models.Model):
    primary_entity = models.ForeignKey(
        Entity, on_delete=models.CASCADE, related_name="received_boosters"
    )
    secondary_entity = models.ForeignKey(
        Entity, on_delete=models.CASCADE, related_name="given_boosters"
    )
    boost_type = models.CharField(max_length=50)
    boost_score = models.IntegerField(default=5)

    class Meta:
        unique_together = [("primary_entity", "secondary_entity", "boost_type")]

    def __str__(self):
        return f"{self.secondary_entity.fqn} -[{self.boost_type}:{self.boost_score}]-> {self.primary_entity.fqn}"


class TaskStatus(models.Model):
    """Tracks background task execution status."""

    class State(models.TextChoices):
        PENDING = "pending"
        RUNNING = "running"
        COMPLETED = "completed"
        FAILED = "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_name = models.CharField(max_length=128)
    state = models.CharField(max_length=20, choices=State.choices, default=State.PENDING)
    progress_current = models.IntegerField(default=0)
    progress_total = models.IntegerField(default=0)
    message = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.task_name} [{self.state}]"
