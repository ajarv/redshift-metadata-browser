"""One-time data migration from ~/.db-browser/catalog.db to Django's database."""
import json
import sqlite3
import uuid
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import (
    Entity,
    EntityType,
    IdentifiableInfo,
    IdentifiableInfoBooster,
    Relationship,
    RelationType,
    Tag,
    Term,
)

SOURCE_DB = Path.home() / ".db-browser" / "catalog.db"
BATCH_SIZE = 2000


class Command(BaseCommand):
    help = "Migrate data from ~/.db-browser/catalog.db into the Django database (one-time)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source", default=str(SOURCE_DB),
            help=f"Path to source SQLite DB (default: {SOURCE_DB})",
        )
        parser.add_argument("--skip-existing", action="store_true", help="Skip if Django DB already has entities")

    def handle(self, *args, **options):
        source_path = Path(options["source"])
        if not source_path.exists():
            self.stderr.write(self.style.ERROR(f"Source DB not found: {source_path}"))
            return

        if options["skip_existing"] and Entity.objects.exists():
            self.stderr.write("Django DB already has entities. Use --skip-existing to confirm skip.")
            return

        conn = sqlite3.connect(str(source_path))
        conn.row_factory = sqlite3.Row

        self.stderr.write(self.style.NOTICE(f"Migrating from: {source_path}"))

        self._migrate_entities(conn)
        self._migrate_relationships(conn)
        self._migrate_tags(conn)
        self._migrate_terms(conn)
        self._migrate_identifiable_info(conn)
        self._migrate_boosters(conn)

        conn.close()
        self.stderr.write(self.style.SUCCESS("\nMigration complete."))

    def _migrate_entities(self, conn):
        self.stderr.write("\n[1/6] Migrating entities...")
        cursor = conn.execute("SELECT id, entity_type, fqn, name, json FROM entities")

        batch = []
        count = 0
        while True:
            rows = cursor.fetchmany(BATCH_SIZE)
            if not rows:
                break
            for row in rows:
                data = json.loads(row["json"])
                description = data.pop("description", None) or ""

                metadata = {}
                for key in ("host", "port", "engine", "database_fqn", "schema_fqn",
                            "table_fqn", "table_type", "data_type", "is_nullable",
                            "column_default", "ordinal_position", "row_count",
                            "dist_key", "sort_keys", "view_definition"):
                    if key in data:
                        metadata[key] = data[key]

                batch.append(Entity(
                    id=uuid.UUID(row["id"]) if len(row["id"]) == 36 else uuid.uuid4(),
                    fqn=row["fqn"],
                    name=row["name"],
                    entity_type=row["entity_type"],
                    description=description,
                    metadata=metadata,
                ))

            if batch:
                with transaction.atomic():
                    Entity.objects.bulk_create(batch, ignore_conflicts=True)
                count += len(batch)
                batch = []
                if count % 10000 == 0:
                    self.stderr.write(f"  {count} entities...")

        if batch:
            with transaction.atomic():
                Entity.objects.bulk_create(batch, ignore_conflicts=True)
            count += len(batch)

        self.stderr.write(self.style.SUCCESS(f"  Done: {count} entities migrated."))

    def _migrate_relationships(self, conn):
        self.stderr.write("\n[2/6] Migrating relationships...")

        # Build FQN-to-UUID lookup from Django DB
        entity_ids = dict(Entity.objects.values_list("fqn", "id"))
        # Build old-id-to-fqn mapping from source
        old_id_to_fqn = {}
        for row in conn.execute("SELECT id, fqn FROM entities"):
            old_id_to_fqn[row["id"]] = row["fqn"]

        cursor = conn.execute("SELECT from_id, to_id, from_entity, to_entity, relation FROM relationships")

        batch = []
        count = 0
        skipped = 0
        while True:
            rows = cursor.fetchmany(BATCH_SIZE)
            if not rows:
                break
            for row in rows:
                from_fqn = old_id_to_fqn.get(row["from_id"])
                to_fqn = old_id_to_fqn.get(row["to_id"])
                if not from_fqn or not to_fqn:
                    skipped += 1
                    continue

                from_uuid = entity_ids.get(from_fqn)
                to_uuid = entity_ids.get(to_fqn)
                if not from_uuid or not to_uuid:
                    skipped += 1
                    continue

                batch.append(Relationship(
                    from_entity_id=from_uuid,
                    to_entity_id=to_uuid,
                    from_entity_type=row["from_entity"],
                    to_entity_type=row["to_entity"],
                    relation=row["relation"],
                ))

            if batch:
                with transaction.atomic():
                    Relationship.objects.bulk_create(batch, ignore_conflicts=True)
                count += len(batch)
                batch = []
                if count % 10000 == 0:
                    self.stderr.write(f"  {count} relationships...")

        if batch:
            with transaction.atomic():
                Relationship.objects.bulk_create(batch, ignore_conflicts=True)
            count += len(batch)

        self.stderr.write(self.style.SUCCESS(f"  Done: {count} relationships migrated ({skipped} skipped)."))

    def _migrate_tags(self, conn):
        self.stderr.write("\n[3/6] Migrating tags...")
        fqn_to_id = dict(Entity.objects.values_list("fqn", "id"))

        cursor = conn.execute("SELECT entity_fqn, tag_key, tag_value FROM tags")
        batch = []
        count = 0
        for row in cursor:
            entity_id = fqn_to_id.get(row["entity_fqn"])
            if not entity_id:
                continue
            batch.append(Tag(
                entity_id=entity_id,
                key=row["tag_key"],
                value=row["tag_value"] or "",
            ))
            if len(batch) >= BATCH_SIZE:
                with transaction.atomic():
                    Tag.objects.bulk_create(batch, ignore_conflicts=True)
                count += len(batch)
                batch = []

        if batch:
            with transaction.atomic():
                Tag.objects.bulk_create(batch, ignore_conflicts=True)
            count += len(batch)

        self.stderr.write(self.style.SUCCESS(f"  Done: {count} tags migrated."))

    def _migrate_terms(self, conn):
        self.stderr.write("\n[4/6] Migrating terms...")
        fqn_to_id = dict(Entity.objects.values_list("fqn", "id"))

        cursor = conn.execute("SELECT entity_fqn, term_name, term_type, score, pass_stage FROM terms")
        batch = []
        count = 0
        while True:
            rows = cursor.fetchmany(BATCH_SIZE)
            if not rows:
                break
            for row in rows:
                entity_id = fqn_to_id.get(row["entity_fqn"])
                if not entity_id:
                    continue
                batch.append(Term(
                    entity_id=entity_id,
                    term_name=row["term_name"],
                    term_type=row["term_type"],
                    score=row["score"],
                    pass_stage=row["pass_stage"],
                ))

            if batch:
                with transaction.atomic():
                    Term.objects.bulk_create(batch, ignore_conflicts=True)
                count += len(batch)
                batch = []
                if count % 100000 == 0:
                    self.stderr.write(f"  {count} terms...")

        if batch:
            with transaction.atomic():
                Term.objects.bulk_create(batch, ignore_conflicts=True)
            count += len(batch)

        self.stderr.write(self.style.SUCCESS(f"  Done: {count} terms migrated."))

    def _migrate_identifiable_info(self, conn):
        self.stderr.write("\n[5/6] Migrating identifiable_info...")
        fqn_to_id = dict(Entity.objects.values_list("fqn", "id"))

        cursor = conn.execute("SELECT entity_fqn, phi_score, pii_score, pass_stage FROM identifiable_info")
        batch = []
        count = 0
        while True:
            rows = cursor.fetchmany(BATCH_SIZE)
            if not rows:
                break
            for row in rows:
                entity_id = fqn_to_id.get(row["entity_fqn"])
                if not entity_id:
                    continue
                batch.append(IdentifiableInfo(
                    entity_id=entity_id,
                    phi_score=row["phi_score"],
                    pii_score=row["pii_score"],
                    pass_stage=row["pass_stage"],
                ))

            if batch:
                with transaction.atomic():
                    IdentifiableInfo.objects.bulk_create(batch, ignore_conflicts=True)
                count += len(batch)
                batch = []
                if count % 50000 == 0:
                    self.stderr.write(f"  {count} identifiable_info records...")

        if batch:
            with transaction.atomic():
                IdentifiableInfo.objects.bulk_create(batch, ignore_conflicts=True)
            count += len(batch)

        self.stderr.write(self.style.SUCCESS(f"  Done: {count} identifiable_info records migrated."))

    def _migrate_boosters(self, conn):
        self.stderr.write("\n[6/6] Migrating identifiable_info_boosters...")
        fqn_to_id = dict(Entity.objects.values_list("fqn", "id"))

        cursor = conn.execute(
            "SELECT primary_entity_fqn, secondary_entity_fqn, boost_type, boost_score "
            "FROM identifiable_info_booster"
        )
        batch = []
        count = 0
        skipped = 0
        while True:
            rows = cursor.fetchmany(BATCH_SIZE)
            if not rows:
                break
            for row in rows:
                primary_id = fqn_to_id.get(row["primary_entity_fqn"])
                secondary_id = fqn_to_id.get(row["secondary_entity_fqn"])
                if not primary_id or not secondary_id:
                    skipped += 1
                    continue
                batch.append(IdentifiableInfoBooster(
                    primary_entity_id=primary_id,
                    secondary_entity_id=secondary_id,
                    boost_type=row["boost_type"],
                    boost_score=row["boost_score"],
                ))

            if batch:
                with transaction.atomic():
                    IdentifiableInfoBooster.objects.bulk_create(batch, ignore_conflicts=True)
                count += len(batch)
                batch = []
                if count % 50000 == 0:
                    self.stderr.write(f"  {count} boosters...")

        if batch:
            with transaction.atomic():
                IdentifiableInfoBooster.objects.bulk_create(batch, ignore_conflicts=True)
            count += len(batch)

        self.stderr.write(self.style.SUCCESS(f"  Done: {count} boosters migrated ({skipped} skipped)."))
