"""Fetch Redshift schema metadata into the Django entity database."""
import os
import queue
import sys
import threading
import time
import uuid

from django.core.management.base import BaseCommand

from catalog.models import Entity, EntityType, Relationship, RelationType


class Command(BaseCommand):
    help = "Fetch Redshift schema metadata into the local entity database."

    def add_arguments(self, parser):
        parser.add_argument("--schema", default=None, help="Schema name or pattern to limit fetch scope")
        parser.add_argument("--workers", type=int, default=4, help="Number of worker threads")
        parser.add_argument("--force", action="store_true", help="Re-fetch even if already present")

    def handle(self, *args, **options):
        try:
            import psycopg2
        except ImportError:
            self.stderr.write("psycopg2 is required. Install with: uv add psycopg2-binary")
            sys.exit(1)

        schema_filter = options["schema"]
        workers = options["workers"]
        force = options["force"]

        db_name = os.environ.get("PGDATABASE")
        if not db_name:
            self.stderr.write("Error: PGDATABASE not set.")
            sys.exit(1)

        def _make_connection():
            return psycopg2.connect(
                host=os.environ["PGHOST"],
                port=os.environ.get("PGPORT", "5439"),
                database=db_name,
                user=os.environ["PGUSER"],
                password=os.environ["PGPASSWORD"],
            )

        # Stage 1: Fetch schemas
        self.stderr.write("[Stage 1] Fetching schemas...")
        conn = _make_connection()
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

        # Save database entity
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

        # Save schema entities
        for schema_name in all_schemas:
            schema_entity, _ = Entity.objects.update_or_create(
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

        self.stderr.write(f"[Stage 1] Done. {len(all_schemas)} schemas saved.")

        # Stage 2: Fetch tables/views per schema
        self.stderr.write(f"\n[Stage 2] Fetching tables/views for {len(all_schemas)} schemas ({workers} threads)...")

        conn_pool = queue.Queue()
        for _ in range(workers):
            conn_pool.put(_make_connection())

        stage2_lock = threading.Lock()
        stage2_stats = {"tables": 0, "views": 0}
        all_table_items = []

        def stage2_worker(schema_name):
            c = conn_pool.get()
            try:
                with c.cursor() as cur:
                    cur.execute(
                        "SELECT table_name, table_type FROM information_schema.tables "
                        "WHERE table_schema = %s ORDER BY table_name",
                        (schema_name,),
                    )
                    tables_views = cur.fetchall()
            finally:
                conn_pool.put(c)

            schema_fqn = f"{db_name}.{schema_name}"
            schema_entity = Entity.objects.filter(fqn=schema_fqn).first()
            if not schema_entity:
                return

            for tbl_name, tbl_type in tables_views:
                fqn = f"{schema_fqn}.{tbl_name}"
                is_view = tbl_type != "BASE TABLE"
                etype = EntityType.VIEW if is_view else EntityType.TABLE

                with stage2_lock:
                    tbl_entity, _ = Entity.objects.update_or_create(
                        fqn=fqn,
                        defaults={
                            "name": tbl_name,
                            "entity_type": etype,
                            "metadata": {"schema_fqn": schema_fqn, "table_type": tbl_type},
                        },
                    )
                    Relationship.objects.get_or_create(
                        from_entity=schema_entity,
                        to_entity=tbl_entity,
                        relation=RelationType.CONTAINS,
                        defaults={
                            "from_entity_type": EntityType.SCHEMA,
                            "to_entity_type": etype,
                        },
                    )
                    all_table_items.append({"schema": schema_name, "name": tbl_name, "type": "view" if is_view else "table"})
                    if is_view:
                        stage2_stats["views"] += 1
                    else:
                        stage2_stats["tables"] += 1

        work_queue = queue.Queue()
        for s in all_schemas:
            work_queue.put(s)

        def _s2_thread():
            while True:
                try:
                    s = work_queue.get_nowait()
                except queue.Empty:
                    return
                try:
                    stage2_worker(s)
                except Exception as e:
                    self.stderr.write(f"  Stage 2 error ({s}): {e}")
                finally:
                    work_queue.task_done()

        threads = [threading.Thread(target=_s2_thread, daemon=True) for _ in range(workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        while not conn_pool.empty():
            conn_pool.get().close()

        self.stderr.write(f"[Stage 2] Done. {stage2_stats['tables']} tables, {stage2_stats['views']} views saved.")

        # Stage 3: Fetch columns
        self.stderr.write(f"\n[Stage 3] Fetching columns for {len(all_table_items)} tables/views ({workers} threads)...")

        conn_pool = queue.Queue()
        for _ in range(workers):
            conn_pool.put(_make_connection())

        stage3_lock = threading.Lock()
        stage3_stats = {"columns": 0}

        def stage3_worker(item):
            schema_name = item["schema"]
            tbl_name = item["name"]
            table_fqn = f"{db_name}.{schema_name}.{tbl_name}"

            c = conn_pool.get()
            try:
                with c.cursor() as cur:
                    cur.execute(
                        "SELECT column_name, data_type, is_nullable, column_default, ordinal_position "
                        "FROM information_schema.columns "
                        "WHERE table_schema = %s AND table_name = %s "
                        "ORDER BY ordinal_position",
                        (schema_name, tbl_name),
                    )
                    columns = cur.fetchall()
            finally:
                conn_pool.put(c)

            parent_entity = Entity.objects.filter(fqn=table_fqn).first()
            if not parent_entity:
                return

            parent_type = EntityType.TABLE if item["type"] == "table" else EntityType.VIEW

            with stage3_lock:
                for col_name, data_type, is_nullable, col_default, ordinal_pos in columns:
                    col_fqn = f"{table_fqn}.{col_name}"
                    col_entity, _ = Entity.objects.update_or_create(
                        fqn=col_fqn,
                        defaults={
                            "name": col_name,
                            "entity_type": EntityType.COLUMN,
                            "metadata": {
                                "table_fqn": table_fqn,
                                "data_type": data_type,
                                "is_nullable": is_nullable == "YES",
                                "column_default": col_default,
                                "ordinal_position": ordinal_pos or 0,
                            },
                        },
                    )
                    Relationship.objects.get_or_create(
                        from_entity=parent_entity,
                        to_entity=col_entity,
                        relation=RelationType.CONTAINS,
                        defaults={
                            "from_entity_type": parent_type,
                            "to_entity_type": EntityType.COLUMN,
                        },
                    )
                    stage3_stats["columns"] += 1

        work_queue = queue.Queue()
        for item in all_table_items:
            work_queue.put(item)

        def _s3_thread():
            while True:
                try:
                    item = work_queue.get_nowait()
                except queue.Empty:
                    return
                try:
                    stage3_worker(item)
                except Exception as e:
                    self.stderr.write(f"  Stage 3 error: {e}")
                finally:
                    work_queue.task_done()

        threads = [threading.Thread(target=_s3_thread, daemon=True) for _ in range(workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        while not conn_pool.empty():
            conn_pool.get().close()

        self.stderr.write(f"[Stage 3] Done. {stage3_stats['columns']} columns saved.")
        self.stderr.write(
            f"\nAll stages complete. {len(all_schemas)} schemas, "
            f"{len(all_table_items)} tables/views, {stage3_stats['columns']} columns."
        )
