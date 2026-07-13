"""Refresh the schema list from Redshift without fetching tables/columns."""
import os
import sys

from django.core.management.base import BaseCommand

from catalog.models import Entity, EntityType, Relationship, RelationType


class Command(BaseCommand):
    help = "Refresh the schema list from Redshift (lightweight, schemas only)."

    def add_arguments(self, parser):
        parser.add_argument("--schema", default=None, help="Schema name pattern to filter")

    def handle(self, *args, **options):
        try:
            import psycopg2
        except ImportError:
            self.stderr.write("psycopg2 is required. Install with: uv add psycopg2-binary")
            sys.exit(1)

        schema_filter = options["schema"]

        db_name = os.environ.get("PGDATABASE")
        if not db_name:
            self.stderr.write("Error: PGDATABASE not set.")
            sys.exit(1)

        conn = psycopg2.connect(
            host=os.environ["PGHOST"],
            port=os.environ.get("PGPORT", "5439"),
            database=db_name,
            user=os.environ["PGUSER"],
            password=os.environ["PGPASSWORD"],
        )

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT nspname FROM pg_namespace "
                    "WHERE nspname NOT IN ('information_schema', 'pg_catalog', 'pg_internal') "
                    "AND nspname NOT LIKE 'pg_temp_%%' "
                    "AND nspname NOT LIKE 'pg_toast_%%' "
                    "ORDER BY nspname"
                )
                all_schemas = [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

        if schema_filter:
            all_schemas = [s for s in all_schemas if schema_filter.lower() in s.lower()]

        if not all_schemas:
            self.stderr.write("No schemas matched the filter.")
            return

        db_entity, _ = Entity.objects.update_or_create(
            fqn=db_name,
            defaults={
                "name": db_name,
                "entity_type": EntityType.DATABASE,
                "metadata": {
                    "host": os.environ.get("PGHOST"),
                    "port": int(os.environ.get("PGPORT", "5439")),
                    "engine": "redshift",
                },
            },
        )

        created_count = 0
        for schema_name in all_schemas:
            schema_entity, created = Entity.objects.update_or_create(
                fqn=f"{db_name}.{schema_name}",
                defaults={
                    "name": schema_name,
                    "entity_type": EntityType.SCHEMA,
                    "metadata": {"database_fqn": db_name},
                },
            )
            Relationship.objects.get_or_create(
                from_entity=db_entity,
                to_entity=schema_entity,
                relation=RelationType.CONTAINS,
                defaults={
                    "from_entity_type": EntityType.DATABASE,
                    "to_entity_type": EntityType.SCHEMA,
                },
            )
            if created:
                created_count += 1

        self.stderr.write(
            self.style.SUCCESS(
                f"Done. {len(all_schemas)} schemas total, {created_count} new."
            )
        )
