import re
from typing import Optional

from app.clients.firestore_client import firestore_client
from app.models.podcast import RssPodcastEpisode, RssPodcastScript, RssPublishPackage
from app.services.log_summary_utils import add_duplicate_log_summary, add_log_summary, tagged
from app.services.rss_source_service import utc_now_iso
from app.services.workflow_run_service import complete_workflow_run, fail_workflow_run, start_workflow_run

URL_RE = re.compile(r"https?://[^\s\])>\"']+")


def _package_id(script_id: str) -> str:
    return f"package_{script_id}"


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        clean = str(value or "").strip().rstrip(".,;，。")
        if not clean or clean in seen:
            continue
        seen.add(clean)
        unique.append(clean)
    return unique


def _urls_from_briefing(briefing_id: str) -> list[str]:
    briefing = firestore_client.get_briefing_by_id(briefing_id)
    if not briefing:
        return []

    urls: list[str] = []
    for top_change in briefing.top_changes:
        urls.extend(top_change.referenced_urls or [])
    for category in briefing.categories:
        for section in category.sections:
            urls.extend(section.referenced_urls or [])
    return urls


def _urls_from_text(text: str) -> list[str]:
    return URL_RE.findall(text or "")


def create_publish_package(
    podcast: RssPodcastScript,
    episode: RssPodcastEpisode,
    force: bool = False,
    run_bucket: Optional[str] = None,
) -> dict[str, object]:
    should_skip, workflow_run_id, existing_summary = start_workflow_run(
        "podcast_publish_package",
        run_bucket,
        {"script_id": podcast.script_id, "force": force, "run_bucket": run_bucket},
    )
    if should_skip:
        out = dict(existing_summary)
        out.update({"skipped_duplicate": True, "run_bucket": run_bucket, "workflow_run_id": workflow_run_id})
        add_duplicate_log_summary(out, "W9 Publish Package", run_bucket)
        return out

    try:
        existing = firestore_client.get_publish_package_by_script_id(podcast.script_id)
        if existing and not force:
            result = existing.model_dump()
            result["run_bucket"] = run_bucket
            result["workflow_run_id"] = workflow_run_id
            result["skipped_duplicate"] = False
            add_log_summary(result, _compose_publish_package_log_summary(result, reused=True))
            complete_workflow_run(workflow_run_id, result)
            return result

        source_urls = _unique_preserve_order(
            _urls_from_briefing(podcast.briefing_id) + _urls_from_text(podcast.show_notes)
        )
        package = RssPublishPackage(
            package_id=_package_id(podcast.script_id),
            script_id=podcast.script_id,
            episode_id=episode.episode_id,
            briefing_id=podcast.briefing_id,
            briefing_date=podcast.briefing_date,
            generated_at=utc_now_iso(),
            episode_title=podcast.episode_title,
            show_notes=podcast.show_notes,
            audio_url=episode.audio_url,
            audio_gcs_uri=episode.audio_gcs_uri,
            google_doc_url=podcast.google_doc_url,
            source_urls=source_urls,
        )
        firestore_client.upsert_publish_package(package)
        result = package.model_dump()
        result["run_bucket"] = run_bucket
        result["workflow_run_id"] = workflow_run_id
        result["skipped_duplicate"] = False
        add_log_summary(result, _compose_publish_package_log_summary(result))
        complete_workflow_run(workflow_run_id, result)
        return result
    except Exception as exc:
        fail_workflow_run(workflow_run_id, str(exc))
        raise


def _compose_publish_package_log_summary(result: dict[str, object], reused: bool = False) -> list[str]:
    status = "沿用既有 publish package" if reused else "產生 publish package"
    source_urls = result.get("source_urls") if isinstance(result.get("source_urls"), list) else []
    return [
        tagged(
            "ok",
            (
                f"W9 Package {status}：package_id={result.get('package_id') or 'unknown'}，"
                f"來源 URL {len(source_urls)} 個。"
            ),
        ),
        tagged("ok", f"audio_url={'有' if result.get('audio_url') else '無'}，Google Doc={'有' if result.get('google_doc_url') else '無'}。"),
    ]
