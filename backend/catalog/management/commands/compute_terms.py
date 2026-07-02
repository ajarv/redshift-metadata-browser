"""Compute terms for entities using a multi-pass pipeline, processing schema by schema."""
import queue
import threading
import time

from django.core.management.base import BaseCommand
from django.db.models import Q

from catalog.models import Entity, EntityType, Term, TermType
from core.terms import tokenize_entity, classify_with_context


class Command(BaseCommand):
    help = "Compute terms for entities using a multi-pass pipeline, schema by schema."

    def add_arguments(self, parser):
        parser.add_argument("--schema", default=None, help="Specific schema FQN or name to process")
        parser.add_argument("--recompute", action="store_true", help="Recompute terms for already-processed entities")
        parser.add_argument("--workers", type=int, default=4, help="Number of worker threads")

    def handle(self, *args, **options):
        schema_filter = options["schema"]
        recompute = options["recompute"]
        workers = options["workers"]

        schemas = Entity.objects.filter(entity_type=EntityType.SCHEMA)
        if schema_filter:
            schemas = schemas.filter(Q(fqn__icontains=schema_filter) | Q(name__icontains=schema_filter))

        schema_list = list(schemas.order_by("fqn"))
        if not schema_list:
            self.stderr.write("No schemas found.")
            return

        self.stderr.write(f"Processing {len(schema_list)} schemas...\n")
        total_pass1 = 0
        total_pass2 = 0
        total_errors = 0

        for schema_idx, schema in enumerate(schema_list, 1):
            schema_start = time.time()
            schema_fqn = schema.fqn
            schema_name = schema.name

            entities = Entity.objects.filter(
                Q(fqn=schema_fqn) | Q(fqn__startswith=schema_fqn + ".")
            ).exclude(entity_type=EntityType.DATABASE)

            if not recompute:
                already_done = set(
                    Term.objects.filter(
                        entity__fqn__startswith=schema_fqn,
                        pass_stage__gte=2,
                    ).values_list("entity__fqn", flat=True).distinct()
                )
                entities = entities.exclude(fqn__in=already_done)

            entity_list = list(entities.values("id", "fqn", "name"))
            if not entity_list:
                self.stderr.write(f"[{schema_idx}/{len(schema_list)}] {schema_name}: all done, skipping.")
                continue

            self.stderr.write(f"[{schema_idx}/{len(schema_list)}] {schema_name}: {len(entity_list)} entities...")

            # Pass 1: Tokenize
            pass1_stats = {"computed": 0}
            pass1_lock = threading.Lock()

            def pass1_worker(entity):
                try:
                    terms = tokenize_entity(entity["name"])
                    with pass1_lock:
                        if recompute:
                            Term.objects.filter(entity_id=entity["id"]).delete()

                        if terms:
                            term_objs = [
                                Term(
                                    entity_id=entity["id"],
                                    term_name=t_name,
                                    term_type=t_type,
                                    score=t_score,
                                    pass_stage=1,
                                )
                                for t_name, t_type, t_score in terms
                            ]
                            Term.objects.bulk_create(term_objs, ignore_conflicts=True)
                            pass1_stats["computed"] += 1
                        else:
                            Term.objects.get_or_create(
                                entity_id=entity["id"],
                                term_name="__none__",
                                term_type=TermType.SENTINEL,
                                defaults={"score": 0, "pass_stage": 1},
                            )
                except Exception as e:
                    self.stderr.write(f"  P1 error {entity['fqn']}: {e}")

            self._run_threaded(entity_list, pass1_worker, workers, f"P1 {schema_name}")

            # Pass 2: Classify with context
            sentinel_fqns = set(
                Term.objects.filter(
                    entity__fqn__startswith=schema_fqn,
                    term_type=TermType.SENTINEL,
                ).values_list("entity__fqn", flat=True)
            )
            pass2_entities = [e for e in entity_list if e["fqn"] not in sentinel_fqns]
            pass2_stats = {"classified": 0, "errors": 0}
            pass2_lock = threading.Lock()

            def pass2_worker(entity):
                try:
                    fqn = entity["fqn"]
                    parts = fqn.split(".")

                    entity_terms = list(
                        Term.objects.filter(entity_id=entity["id"])
                        .exclude(term_type=TermType.SENTINEL)
                        .values("term_name", "term_type", "score")
                    )
                    if not entity_terms:
                        return

                    term_dicts = [{"name": t["term_name"], "type": t["term_type"], "score": t["score"]} for t in entity_terms]

                    parent_terms = []
                    sibling_terms = {}
                    sibling_count = 0

                    if len(parts) >= 3:
                        parent_fqn = ".".join(parts[:-1])
                        parent_terms = list(
                            Term.objects.filter(entity__fqn=parent_fqn)
                            .exclude(term_type=TermType.SENTINEL)
                            .values_list("term_name", flat=True)
                        )

                        sibling_fqns = list(
                            Entity.objects.filter(
                                incoming_relationships__from_entity__fqn=parent_fqn,
                                incoming_relationships__relation="CONTAINS",
                            ).exclude(fqn=fqn).values_list("fqn", flat=True)[:50]
                        )
                        sibling_count = len(sibling_fqns)

                        if sibling_fqns:
                            sibling_term_qs = Term.objects.filter(
                                entity__fqn__in=sibling_fqns
                            ).exclude(term_type=TermType.SENTINEL).values_list("entity__fqn", "term_name")
                            for s_fqn, t_name in sibling_term_qs:
                                sibling_terms.setdefault(s_fqn, []).append(t_name)

                    classified = classify_with_context(
                        entity_terms=term_dicts,
                        parent_terms=list(parent_terms),
                        sibling_terms=sibling_terms,
                        sibling_count=sibling_count,
                    )

                    with pass2_lock:
                        Term.objects.filter(entity_id=entity["id"]).exclude(term_type=TermType.SENTINEL).delete()
                        term_objs = [
                            Term(
                                entity_id=entity["id"],
                                term_name=t_name,
                                term_type=t_type,
                                score=t_score,
                                pass_stage=2,
                            )
                            for t_name, t_type, t_score in classified
                        ]
                        Term.objects.bulk_create(term_objs, ignore_conflicts=True)
                        pass2_stats["classified"] += 1
                except Exception as e:
                    with pass2_lock:
                        pass2_stats["errors"] += 1
                    self.stderr.write(f"  P2 error {entity['fqn']}: {e}")

            self._run_threaded(pass2_entities, pass2_worker, workers, f"P2 {schema_name}")

            elapsed = time.time() - schema_start
            total_pass1 += pass1_stats["computed"]
            total_pass2 += pass2_stats["classified"]
            total_errors += pass2_stats["errors"]

            self.stderr.write(
                f"  Done in {elapsed:.1f}s — P1: {pass1_stats['computed']} tokenized, "
                f"P2: {pass2_stats['classified']} classified"
                + (f", {pass2_stats['errors']} errors" if pass2_stats["errors"] else "")
            )

        self.stderr.write(
            f"\nAll schemas complete. Totals: {total_pass1} tokenized, {total_pass2} classified, {total_errors} errors."
        )

    def _run_threaded(self, items, worker_fn, num_workers, label):
        work_queue = queue.Queue()
        for item in items:
            work_queue.put(item)

        total = len(items)
        progress = {"done": 0, "start": time.time()}
        lock = threading.Lock()

        def _worker():
            from django.db import connection
            while True:
                try:
                    item = work_queue.get_nowait()
                except queue.Empty:
                    return
                try:
                    worker_fn(item)
                except Exception as e:
                    self.stderr.write(f"  Error: {e}")
                finally:
                    with lock:
                        progress["done"] += 1
                        done = progress["done"]
                    if done % 500 == 0 or (done < 500 and done % 100 == 0):
                        elapsed = time.time() - progress["start"]
                        rate = done / elapsed if elapsed > 0 else 0
                        eta = (total - done) / rate if rate > 0 else 0
                        self.stderr.write(f"  {label}: {done}/{total} ({rate:.0f}/s, ETA {eta:.0f}s)...")
                    work_queue.task_done()
            connection.close()

        threads = []
        for _ in range(num_workers):
            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()
