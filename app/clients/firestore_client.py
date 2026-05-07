from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from app.core.config import settings
from app.models.job import JobRecord
from app.models.rss import RssIngestRun, RssItem, RssSource
from app.models.signal import (
    RssBriefing,
    RssBusinessImpactRun,
    RssClusteringRun,
    RssJudgementRun,
    RssSignal,
)
from typing import Optional

from app.core.logging import logger

class FirestoreClient:
    def __init__(self):
        try:
            self.db = firestore.Client(project=settings.GCP_PROJECT_ID, database=settings.FIRESTORE_DATABASE)
            self.collection = self.db.collection("jobs")
        except Exception as e:
            logger.error(f"Failed to initialize Firestore Client: {e}")
            self.db = None
            self.collection = None
        
    def create_job(self, job_record: JobRecord):
        if not self.collection:
            logger.warning("Firestore not initialized, skipping create_job")
            return
        doc_ref = self.collection.document(job_record.job_id)
        doc_ref.set(job_record.model_dump())
        
    def update_job(self, job_id: str, update_data: dict):
        if not self.collection:
            logger.warning("Firestore not initialized, skipping update_job")
            return
        doc_ref = self.collection.document(job_id)
        doc_ref.update(update_data)
        
    def get_job(self, job_id: str) -> Optional[JobRecord]:
        if not self.collection:
            logger.warning("Firestore not initialized, returning None for get_job")
            return None
        doc = self.collection.document(job_id).get()
        if doc.exists:
            return JobRecord(**doc.to_dict())
        return None

    def upsert_rss_source(self, source: RssSource):
        if not self.db:
            logger.warning("Firestore not initialized, skipping upsert_rss_source")
            return
        self.db.collection("rss_sources").document(source.source_id).set(source.model_dump())

    def upsert_rss_sources(self, sources: list[RssSource]):
        if not self.db:
            logger.warning("Firestore not initialized, skipping upsert_rss_sources")
            return

        collection = self.db.collection("rss_sources")
        batch = self.db.batch()
        operation_count = 0
        for source in sources:
            batch.set(collection.document(source.source_id), source.model_dump())
            operation_count += 1
            if operation_count >= 450:
                batch.commit()
                batch = self.db.batch()
                operation_count = 0
        if operation_count:
            batch.commit()

    def update_rss_source_ingest_results(self, source_results: list[dict[str, object]], ingested_at: str):
        if not self.db:
            logger.warning("Firestore not initialized, skipping update_rss_source_ingest_results")
            return

        collection = self.db.collection("rss_sources")
        batch = self.db.batch()
        operation_count = 0
        for result in source_results:
            source_id = str(result.get("source_id") or "")
            if not source_id:
                continue

            status = str(result.get("status") or "failed")
            update_data = {
                "last_ingested_at": ingested_at,
                "last_ingest_status": status,
                "last_ingest_item_count": int(result.get("item_count") or 0),
                "last_ingest_new_item_count": int(result.get("new_item_count") or 0),
                "last_ingest_updated_item_count": int(result.get("updated_item_count") or 0),
                "last_ingest_duration_ms": int(result.get("duration_ms") or 0),
                "last_ingest_fetch_duration_ms": int(result.get("fetch_duration_ms") or 0),
                "last_ingest_write_duration_ms": int(result.get("write_duration_ms") or 0),
                "last_ingest_skipped_old_item_count": int(result.get("skipped_old_item_count") or 0),
                "last_ingest_error": str(result.get("error") or ""),
            }
            if status == "success":
                update_data["consecutive_ingest_failures"] = 0
            else:
                update_data["consecutive_ingest_failures"] = firestore.Increment(1)

            batch.update(collection.document(source_id), update_data)
            operation_count += 1
            if operation_count >= 450:
                batch.commit()
                batch = self.db.batch()
                operation_count = 0
        if operation_count:
            batch.commit()

    def deactivate_missing_rss_sources(self, active_source_ids: set[str], synced_at: str) -> int:
        if not self.db:
            logger.warning("Firestore not initialized, skipping deactivate_missing_rss_sources")
            return 0

        collection = self.db.collection("rss_sources")
        batch = self.db.batch()
        operation_count = 0
        deactivated_count = 0
        for doc in collection.stream():
            if doc.id in active_source_ids:
                continue
            batch.update(
                collection.document(doc.id),
                {
                    "is_fetchable": False,
                    "health_status": "removed",
                    "raw_status": "removed_from_sheet",
                    "synced_at": synced_at,
                },
            )
            operation_count += 1
            deactivated_count += 1
            if operation_count >= 450:
                batch.commit()
                batch = self.db.batch()
                operation_count = 0
        if operation_count:
            batch.commit()
        return deactivated_count

    def list_rss_sources(self, fetchable_only: bool = False) -> list[RssSource]:
        if not self.db:
            logger.warning("Firestore not initialized, returning empty rss_sources")
            return []

        query = self.db.collection("rss_sources")
        if fetchable_only:
            query = query.where(filter=FieldFilter("is_fetchable", "==", True))

        sources = []
        for doc in query.stream():
            data = doc.to_dict()
            if data:
                sources.append(RssSource(**data))
        return sources

    def upsert_rss_item(self, item: RssItem) -> bool:
        if not self.db:
            logger.warning("Firestore not initialized, skipping upsert_rss_item")
            return False

        doc_ref = self.db.collection("rss_items").document(item.item_id)
        try:
            doc_ref.create(item.model_dump())
            return True
        except AlreadyExists:
            doc_ref.update(
                {
                    "last_seen_at": item.last_seen_at,
                    "published_at": item.published_at,
                    "summary": item.summary,
                }
            )
            return False

    def upsert_rss_items(self, items: list[RssItem]) -> tuple[int, int]:
        if not self.db:
            logger.warning("Firestore not initialized, skipping upsert_rss_items")
            return 0, 0
        if not items:
            return 0, 0

        collection = self.db.collection("rss_items")
        doc_refs = [collection.document(item.item_id) for item in items]
        existing_ids = {doc.id for doc in self.db.get_all(doc_refs) if doc.exists}

        batch = self.db.batch()
        operation_count = 0
        new_item_count = 0
        updated_item_count = 0
        for item, doc_ref in zip(items, doc_refs):
            if item.item_id in existing_ids:
                batch.update(
                    doc_ref,
                    {
                        "last_seen_at": item.last_seen_at,
                        "published_at": item.published_at,
                        "summary": item.summary,
                    },
                )
                updated_item_count += 1
            else:
                batch.set(doc_ref, item.model_dump())
                new_item_count += 1

            operation_count += 1
            if operation_count >= 450:
                batch.commit()
                batch = self.db.batch()
                operation_count = 0
        if operation_count:
            batch.commit()

        return new_item_count, updated_item_count

    def list_rss_items_since(self, since_iso: str) -> list[RssItem]:
        if not self.db:
            logger.warning("Firestore not initialized, returning empty rss_items")
            return []

        collection = self.db.collection("rss_items")
        first_seen_query = collection.where(
            filter=FieldFilter("first_seen_at", ">=", since_iso)
        )
        published_query = collection.where(
            filter=FieldFilter("published_at", ">=", since_iso)
        )

        items_by_id = {}
        for query in (first_seen_query, published_query):
            for doc in query.stream():
                data = doc.to_dict()
                if data:
                    item = RssItem(**data)
                    reference_time = item.published_at or item.first_seen_at
                    if reference_time >= since_iso:
                        items_by_id[item.item_id] = item
        items = list(items_by_id.values())
        return items

    def create_rss_ingest_run(self, run: RssIngestRun):
        if not self.db:
            logger.warning("Firestore not initialized, skipping create_rss_ingest_run")
            return
        self.db.collection("rss_ingest_runs").document(run.run_id).set(run.model_dump())

    def list_rss_items_pending_embedding(self, since_iso: str, limit: int = 1000) -> list[RssItem]:
        if not self.db:
            logger.warning("Firestore not initialized, returning empty pending embedding items")
            return []

        collection = self.db.collection("rss_items")
        items_by_id: dict[str, RssItem] = {}
        for field in ("first_seen_at", "published_at"):
            query = collection.where(filter=FieldFilter(field, ">=", since_iso)).limit(limit)
            for doc in query.stream():
                data = doc.to_dict()
                if not data:
                    continue
                if data.get("embedded_at"):
                    continue
                item = RssItem(**data)
                items_by_id[item.item_id] = item
        return list(items_by_id.values())

    def list_rss_items_with_embedding(self, since_iso: str) -> list[RssItem]:
        if not self.db:
            logger.warning("Firestore not initialized, returning empty rss_items with embedding")
            return []

        collection = self.db.collection("rss_items")
        items_by_id: dict[str, RssItem] = {}
        for field in ("first_seen_at", "published_at"):
            query = collection.where(filter=FieldFilter(field, ">=", since_iso))
            for doc in query.stream():
                data = doc.to_dict()
                if not data:
                    continue
                if not data.get("embedded_at"):
                    continue
                if not data.get("embedding"):
                    continue
                item = RssItem(**data)
                items_by_id[item.item_id] = item
        return list(items_by_id.values())

    def update_rss_item_embeddings(
        self,
        embeddings: dict[str, tuple[list[float], str, str]],
    ) -> int:
        """
        embeddings: {item_id: (embedding, embedding_model, embedded_at)}
        """
        if not self.db:
            logger.warning("Firestore not initialized, skipping update_rss_item_embeddings")
            return 0
        if not embeddings:
            return 0

        collection = self.db.collection("rss_items")
        batch = self.db.batch()
        operation_count = 0
        written = 0
        embedding_batch_limit = 100
        for item_id, (vector, model, ts) in embeddings.items():
            batch.update(
                collection.document(item_id),
                {
                    "embedding": vector,
                    "embedding_model": model,
                    "embedded_at": ts,
                },
            )
            operation_count += 1
            written += 1
            if operation_count >= embedding_batch_limit:
                batch.commit()
                batch = self.db.batch()
                operation_count = 0
        if operation_count:
            batch.commit()
        return written

    def update_rss_item_signal_ids(self, item_id_to_signal_id: dict[str, str]) -> int:
        if not self.db:
            logger.warning("Firestore not initialized, skipping update_rss_item_signal_ids")
            return 0
        if not item_id_to_signal_id:
            return 0

        collection = self.db.collection("rss_items")
        batch = self.db.batch()
        operation_count = 0
        for item_id, signal_id in item_id_to_signal_id.items():
            batch.update(collection.document(item_id), {"signal_id": signal_id})
            operation_count += 1
            if operation_count >= 450:
                batch.commit()
                batch = self.db.batch()
                operation_count = 0
        if operation_count:
            batch.commit()
        return len(item_id_to_signal_id)

    def upsert_rss_signals(self, signals: list[RssSignal]) -> int:
        if not self.db:
            logger.warning("Firestore not initialized, skipping upsert_rss_signals")
            return 0
        if not signals:
            return 0

        collection = self.db.collection("rss_signals")
        batch = self.db.batch()
        operation_count = 0
        for signal in signals:
            batch.set(collection.document(signal.signal_id), signal.model_dump())
            operation_count += 1
            if operation_count >= 450:
                batch.commit()
                batch = self.db.batch()
                operation_count = 0
        if operation_count:
            batch.commit()
        return len(signals)

    def list_recent_signals(self, since_iso: str, limit: int = 200) -> list[RssSignal]:
        if not self.db:
            logger.warning("Firestore not initialized, returning empty signals")
            return []
        query = (
            self.db.collection("rss_signals")
            .where(filter=FieldFilter("generated_at", ">=", since_iso))
            .order_by("generated_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        signals = []
        for doc in query.stream():
            data = doc.to_dict()
            if data:
                signals.append(RssSignal(**data))
        return signals

    def get_signal_by_id(self, signal_id: str) -> Optional[RssSignal]:
        if not self.db:
            logger.warning("Firestore not initialized, returning None for get_signal_by_id")
            return None
        doc = self.db.collection("rss_signals").document(signal_id).get()
        if doc.exists:
            return RssSignal(**doc.to_dict())
        return None

    def list_rss_items_by_ids(self, item_ids: list[str]) -> list[RssItem]:
        if not self.db:
            logger.warning("Firestore not initialized, returning empty items by ids")
            return []
        if not item_ids:
            return []
        collection = self.db.collection("rss_items")
        doc_refs = [collection.document(item_id) for item_id in item_ids]
        items: list[RssItem] = []
        for doc in self.db.get_all(doc_refs):
            if doc.exists:
                data = doc.to_dict() or {}
                items.append(RssItem(**data))
        return items

    def create_clustering_run(self, run: RssClusteringRun):
        if not self.db:
            logger.warning("Firestore not initialized, skipping create_clustering_run")
            return
        self.db.collection("rss_clustering_runs").document(run.run_id).set(run.model_dump())

    def list_recent_clustering_runs(self, since_iso: str) -> list[RssClusteringRun]:
        if not self.db:
            logger.warning("Firestore not initialized, returning empty clustering runs")
            return []
        query = (
            self.db.collection("rss_clustering_runs")
            .where(filter=FieldFilter("generated_at", ">=", since_iso))
            .order_by("generated_at", direction=firestore.Query.DESCENDING)
        )
        runs = []
        for doc in query.stream():
            data = doc.to_dict()
            if data:
                runs.append(RssClusteringRun(**data))
        return runs

    def create_judgement_run(self, run: RssJudgementRun):
        if not self.db:
            logger.warning("Firestore not initialized, skipping create_judgement_run")
            return
        self.db.collection("rss_judgement_runs").document(run.run_id).set(run.model_dump())

    def list_recent_judgement_runs(self, since_iso: str) -> list[RssJudgementRun]:
        if not self.db:
            logger.warning("Firestore not initialized, returning empty judgement runs")
            return []
        query = (
            self.db.collection("rss_judgement_runs")
            .where(filter=FieldFilter("generated_at", ">=", since_iso))
            .order_by("generated_at", direction=firestore.Query.DESCENDING)
        )
        runs = []
        for doc in query.stream():
            data = doc.to_dict()
            if data:
                runs.append(RssJudgementRun(**data))
        return runs

    def list_signals_for_impact(
        self,
        since_iso: str,
        min_score: int = 60,
        limit: int = 200,
        force: bool = False,
    ) -> list[RssSignal]:
        if not self.db:
            logger.warning("Firestore not initialized, returning empty signals_for_impact")
            return []
        query = self.db.collection("rss_signals").where(
            filter=FieldFilter("generated_at", ">=", since_iso)
        )
        signals: list[RssSignal] = []
        for doc in query.stream():
            data = doc.to_dict() or {}
            score = data.get("importance_score")
            if score is None:
                continue
            if score < min_score:
                continue
            if not force and data.get("impact_judged_at"):
                continue
            signals.append(RssSignal(**data))
        signals.sort(key=lambda s: (s.importance_score or 0), reverse=True)
        return signals[:limit]

    def list_signals_for_briefing(
        self,
        since_iso: str,
        min_score: int = 70,
        limit: int = 80,
    ) -> list[RssSignal]:
        if not self.db:
            logger.warning("Firestore not initialized, returning empty signals_for_briefing")
            return []
        query = self.db.collection("rss_signals").where(
            filter=FieldFilter("generated_at", ">=", since_iso)
        )
        signals: list[RssSignal] = []
        for doc in query.stream():
            data = doc.to_dict() or {}
            score = data.get("importance_score")
            if score is None or score < min_score:
                continue
            signals.append(RssSignal(**data))
        signals.sort(key=lambda s: (s.importance_score or 0), reverse=True)
        return signals[:limit]

    def upsert_briefing(self, briefing: RssBriefing):
        if not self.db:
            logger.warning("Firestore not initialized, skipping upsert_briefing")
            return
        self.db.collection("rss_briefings").document(briefing.briefing_id).set(briefing.model_dump())

    def get_briefing_by_id(self, briefing_id: str) -> Optional[RssBriefing]:
        if not self.db:
            return None
        doc = self.db.collection("rss_briefings").document(briefing_id).get()
        if doc.exists:
            return RssBriefing(**doc.to_dict())
        return None

    def list_recent_briefings(self, limit: int = 7) -> list[RssBriefing]:
        if not self.db:
            return []
        query = (
            self.db.collection("rss_briefings")
            .order_by("generated_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        return [RssBriefing(**doc.to_dict()) for doc in query.stream() if doc.exists]

    def create_business_impact_run(self, run: RssBusinessImpactRun):
        if not self.db:
            return
        self.db.collection("rss_business_impact_runs").document(run.run_id).set(run.model_dump())

    def list_top_signals(
        self,
        since_iso: str,
        min_score: int = 0,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> list[RssSignal]:
        if not self.db:
            logger.warning("Firestore not initialized, returning empty top signals")
            return []
        query = self.db.collection("rss_signals").where(
            filter=FieldFilter("generated_at", ">=", since_iso)
        )
        if status:
            query = query.where(filter=FieldFilter("cluster_status", "==", status))
        signals: list[RssSignal] = []
        for doc in query.stream():
            data = doc.to_dict() or {}
            score = data.get("importance_score")
            if score is None:
                continue
            if score < min_score:
                continue
            signals.append(RssSignal(**data))
        signals.sort(key=lambda s: (s.importance_score or 0), reverse=True)
        return signals[:limit]


firestore_client = FirestoreClient()
