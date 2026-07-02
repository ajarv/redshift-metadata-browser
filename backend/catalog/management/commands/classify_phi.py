"""Classify entities for PHI/PII using a 5-pass pipeline, processing schema by schema."""
import queue
import threading
import time

from django.core.management.base import BaseCommand
from django.db.models import Q

from catalog.models import (
    Entity,
    EntityType,
    IdentifiableInfo,
    IdentifiableInfoBooster,
    Term,
    TermType,
)
from core.phi_classifier import (
    compute_child_boost,
    compute_sibling_boost,
    score_by_name,
    score_by_terms,
)


class Command(BaseCommand):
    help = "Classify entities for PHI/PII using a 5-pass pipeline, schema by schema."

    def add_arguments(self, parser):
        parser.add_argument("--schema", default=None, help="Specific schema FQN or name to process")
        parser.add_argument("--recompute", action="store_true", help="Recompute scores for already-classified entities")
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

        self.stderr.write(f"Processing {len(schema_list)} schemas for PHI/PII classification...\n")
        totals = {"p1": 0, "p5": 0, "errors": 0}

        for schema_idx, schema in enumerate(schema_list, 1):
            schema_start = time.time()
            schema_fqn = schema.fqn
            schema_name = schema.name

            entities = Entity.objects.filter(
                Q(fqn=schema_fqn) | Q(fqn__startswith=schema_fqn + ".")
            ).exclude(entity_type=EntityType.DATABASE)

            if not recompute:
                done_ids = set(
                    IdentifiableInfo.objects.filter(
                        entity__fqn__startswith=schema_fqn,
                        pass_stage__gte=5,
                    ).values_list("entity_id", flat=True)
                )
                entities = entities.exclude(id__in=done_ids)

            entity_list = list(entities.values("id", "fqn", "name"))
            if not entity_list:
                self.stderr.write(f"[{schema_idx}/{len(schema_list)}] {schema_name}: all done, skipping.")
                continue

            self.stderr.write(f"[{schema_idx}/{len(schema_list)}] {schema_name}: {len(entity_list)} entities...")

            write_lock = threading.Lock()
            schema_errors = {"count": 0}

            # Pass 1: Name pattern matching
            pass1_stats = {"scored": 0}

            def phi_pass1_worker(entity):
                try:
                    phi_score, pii_score = score_by_name(entity["name"])
                    with write_lock:
                        if recompute:
                            IdentifiableInfo.objects.filter(entity_id=entity["id"]).delete()
                            IdentifiableInfoBooster.objects.filter(primary_entity_id=entity["id"]).delete()
                        IdentifiableInfo.objects.update_or_create(
                            entity_id=entity["id"],
                            defaults={"phi_score": phi_score, "pii_score": pii_score, "pass_stage": 1},
                        )
                        pass1_stats["scored"] += 1
                except Exception:
                    with write_lock:
                        schema_errors["count"] += 1

            self._run_threaded(entity_list, phi_pass1_worker, workers, f"P1 {schema_name}")

            # Pass 2: Term-based scoring
            pass2_stats = {"adjusted": 0}

            def phi_pass2_worker(entity):
                try:
                    with write_lock:
                        info = IdentifiableInfo.objects.filter(entity_id=entity["id"]).first()
                    if not info:
                        return

                    term_names = list(
                        Term.objects.filter(entity_id=entity["id"])
                        .exclude(term_type=TermType.SENTINEL)
                        .values_list("term_name", flat=True)
                    )
                    phi_score, pii_score = score_by_terms(term_names, info.phi_score, info.pii_score)

                    with write_lock:
                        info.phi_score = phi_score
                        info.pii_score = pii_score
                        info.pass_stage = 2
                        info.save()
                        pass2_stats["adjusted"] += 1
                except Exception:
                    with write_lock:
                        schema_errors["count"] += 1

            self._run_threaded(entity_list, phi_pass2_worker, workers, f"P2 {schema_name}")

            # Pass 3: Child-to-parent boosting
            pass3_stats = {"boosters": 0}

            def phi_pass3_worker(entity):
                try:
                    fqn = entity["fqn"]
                    parts = fqn.split(".")
                    if len(parts) <= 2:
                        return

                    info = IdentifiableInfo.objects.filter(entity_id=entity["id"]).first()
                    if not info or (info.phi_score == 0 and info.pii_score == 0):
                        return

                    parent_fqn = ".".join(parts[:-1])
                    parent = Entity.objects.filter(fqn=parent_fqn).first()
                    if not parent:
                        return

                    boost = compute_child_boost(info.phi_score, info.pii_score)
                    with write_lock:
                        IdentifiableInfoBooster.objects.update_or_create(
                            primary_entity=parent,
                            secondary_entity_id=entity["id"],
                            boost_type="child_to_parent",
                            defaults={"boost_score": boost},
                        )
                        pass3_stats["boosters"] += 1
                except Exception:
                    with write_lock:
                        schema_errors["count"] += 1

            self._run_threaded(entity_list, phi_pass3_worker, workers, f"P3 {schema_name}")

            # Pass 4: Sibling-to-sibling boosting
            pass4_stats = {"boosters": 0}

            def phi_pass4_worker(entity):
                try:
                    fqn = entity["fqn"]
                    parts = fqn.split(".")
                    if len(parts) <= 2:
                        return

                    info = IdentifiableInfo.objects.filter(entity_id=entity["id"]).first()
                    if not info or (info.phi_score == 0 and info.pii_score == 0):
                        return

                    parent_fqn = ".".join(parts[:-1])
                    sibling_ids = list(
                        Entity.objects.filter(
                            incoming_relationships__from_entity__fqn=parent_fqn,
                            incoming_relationships__relation="CONTAINS",
                        ).exclude(id=entity["id"]).values_list("id", flat=True)[:50]
                    )

                    siblings_with_scores = list(
                        IdentifiableInfo.objects.filter(
                            entity_id__in=sibling_ids,
                        ).filter(Q(phi_score__gt=0) | Q(pii_score__gt=0))
                        .values_list("entity_id", flat=True)
                    )

                    if len(siblings_with_scores) >= 2:
                        boost = compute_sibling_boost(info.phi_score, info.pii_score)
                        with write_lock:
                            for sib_id in siblings_with_scores:
                                IdentifiableInfoBooster.objects.update_or_create(
                                    primary_entity_id=entity["id"],
                                    secondary_entity_id=sib_id,
                                    boost_type="sibling_to_sibling",
                                    defaults={"boost_score": boost},
                                )
                            pass4_stats["boosters"] += len(siblings_with_scores)
                except Exception:
                    with write_lock:
                        schema_errors["count"] += 1

            self._run_threaded(entity_list, phi_pass4_worker, workers, f"P4 {schema_name}")

            # Pass 5: Score normalization and propagation
            pass5_stats = {"finalized": 0}

            def phi_pass5_worker(entity):
                try:
                    info = IdentifiableInfo.objects.filter(entity_id=entity["id"]).first()
                    if not info:
                        return

                    boosters = IdentifiableInfoBooster.objects.filter(primary_entity_id=entity["id"])
                    phi_total = info.phi_score
                    pii_total = info.pii_score

                    for b in boosters:
                        phi_total += b.boost_score
                        pii_total += b.boost_score

                    with write_lock:
                        info.phi_score = min(100, phi_total)
                        info.pii_score = min(100, pii_total)
                        info.pass_stage = 5
                        info.save()
                        pass5_stats["finalized"] += 1
                except Exception:
                    with write_lock:
                        schema_errors["count"] += 1

            self._run_threaded(entity_list, phi_pass5_worker, workers, f"P5 {schema_name}")

            elapsed = time.time() - schema_start
            totals["p1"] += pass1_stats["scored"]
            totals["p5"] += pass5_stats["finalized"]
            totals["errors"] += schema_errors["count"]

            self.stderr.write(
                f"  Done in {elapsed:.1f}s — P1: {pass1_stats['scored']}, P5: {pass5_stats['finalized']} finalized"
                + (f", {schema_errors['count']} errors" if schema_errors["count"] else "")
            )

        with_phi = IdentifiableInfo.objects.filter(phi_score__gt=0).count()
        with_pii = IdentifiableInfo.objects.filter(pii_score__gt=0).count()
        self.stderr.write(
            f"\nAll schemas complete. Totals: {totals['p1']} scored, {totals['p5']} finalized, {totals['errors']} errors.\n"
            f"  {with_phi} entities with PHI > 0, {with_pii} with PII > 0."
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
