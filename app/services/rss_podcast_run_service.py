import hashlib
import time
from typing import Optional

from app.clients.firestore_client import firestore_client
from app.models.podcast import RssPodcastEpisode, RssPodcastRun, RssPodcastScript
from app.services.log_summary_utils import add_duplicate_log_summary, add_log_summary, cost_text, seconds_text, tagged
from app.services.model_routing_service import effective_model_routes, validate_model_overrides
from app.services.rss_podcast_audio_service import synthesize_podcast_audio
from app.services.rss_podcast_script_service import generate_daily_podcast_script
from app.services.rss_publish_package_service import create_publish_package
from app.services.rss_source_service import utc_now_iso
from app.services.workflow_run_service import complete_workflow_run, fail_workflow_run, start_workflow_run


def _generate_run_id() -> str:
    generated_at = utc_now_iso()
    digest = hashlib.sha256(generated_at.encode()).hexdigest()[:6]
    return f"podcast_run_{generated_at[:10].replace('-', '')}_{digest}"


def run_daily_podcast(
    briefing_id: Optional[str] = None,
    write_google_doc: bool = True,
    force_audio: bool = False,
    force_package: bool = False,
    run_bucket: Optional[str] = None,
    model_overrides: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    started = time.monotonic()
    generated_at = utc_now_iso()
    run_id = _generate_run_id()
    should_skip, workflow_run_id, existing_summary = start_workflow_run(
        "podcast_run_daily",
        run_bucket,
        {
            "briefing_id": briefing_id,
            "write_google_doc": write_google_doc,
            "force_audio": force_audio,
            "force_package": force_package,
            "run_bucket": run_bucket,
            "model_overrides": validate_model_overrides(model_overrides),
        },
    )
    if should_skip:
        out = dict(existing_summary)
        out.update({"skipped_duplicate": True, "run_bucket": run_bucket, "workflow_run_id": workflow_run_id})
        add_duplicate_log_summary(out, "W9 Daily Podcast", run_bucket)
        return out
    briefing_date = ""
    script: RssPodcastScript | None = None
    episode: RssPodcastEpisode | None = None
    failed_step = "script"

    try:
        script_payload = generate_daily_podcast_script(
            briefing_id=briefing_id,
            write_google_doc=write_google_doc,
            run_bucket=f"{run_bucket}_script" if run_bucket else None,
            model_overrides=model_overrides,
        )
        script = RssPodcastScript(**script_payload)
        briefing_date = script.briefing_date

        failed_step = "audio"
        episode_payload = synthesize_podcast_audio(
            script,
            force=force_audio,
            run_bucket=f"{run_bucket}_audio" if run_bucket else None,
        )
        episode = RssPodcastEpisode(**episode_payload)

        failed_step = "publish_package"
        package_payload = create_publish_package(
            script,
            episode,
            force=force_package,
            run_bucket=f"{run_bucket}_package" if run_bucket else None,
        )

        run = RssPodcastRun(
            run_id=run_id,
            generated_at=generated_at,
            briefing_date=briefing_date,
            script_id=script.script_id,
            episode_id=episode.episode_id,
            package_id=str(package_payload.get("package_id") or ""),
            ok=True,
            duration_ms=int((time.monotonic() - started) * 1000),
            cost_usd=round(script.cost_usd + episode.tts_cost_usd, 6),
        )
        firestore_client.create_podcast_run(run)
        result = {
            "ok": True,
            "run": run.model_dump(),
            "script": script_payload,
            "episode": episode_payload,
            "publish_package": package_payload,
            "run_bucket": run_bucket,
            "workflow_run_id": workflow_run_id,
            "skipped_duplicate": False,
            "model_routing": effective_model_routes(model_overrides, ["w9_podcast_script"]),
        }
        add_log_summary(result, _compose_daily_podcast_log_summary(result))
        complete_workflow_run(workflow_run_id, result)
        return result
    except Exception as exc:
        run = RssPodcastRun(
            run_id=run_id,
            generated_at=generated_at,
            briefing_date=briefing_date,
            script_id=script.script_id if script else None,
            episode_id=episode.episode_id if episode else None,
            ok=False,
            failed_step=failed_step,
            error=str(exc),
            duration_ms=int((time.monotonic() - started) * 1000),
            cost_usd=round(script.cost_usd if script else 0.0, 6),
        )
        firestore_client.create_podcast_run(run)
        failure_summary = run.model_dump()
        failure_summary["workflow_run_id"] = workflow_run_id
        failure_summary["run_bucket"] = run_bucket
        failure_summary["model_routing"] = effective_model_routes(model_overrides, ["w9_podcast_script"])
        add_log_summary(failure_summary, _compose_daily_podcast_failure_log_summary(failure_summary))
        fail_workflow_run(workflow_run_id, str(exc), failure_summary)
        raise


def _compose_daily_podcast_log_summary(result: dict[str, object]) -> list[str]:
    run = result.get("run") if isinstance(result.get("run"), dict) else {}
    script = result.get("script") if isinstance(result.get("script"), dict) else {}
    episode = result.get("episode") if isinstance(result.get("episode"), dict) else {}
    package = result.get("publish_package") if isinstance(result.get("publish_package"), dict) else {}
    return [
        tagged(
            "ok",
            (
                f"W9 Daily Podcast 完成：script={script.get('script_id') or run.get('script_id') or 'missing'}，"
                f"episode={episode.get('episode_id') or run.get('episode_id') or 'missing'}，"
                f"package={package.get('package_id') or run.get('package_id') or 'missing'}。"
            ),
        ),
        tagged(
            "new",
            (
                f"script {script.get('word_count', 0)} 字，audio 約 {episode.get('audio_duration_seconds', 0)} 秒，"
                f"來源 URL {len(package.get('source_urls') or [])} 個。"
            ),
        ),
        tagged("ok", f"Google Doc={'有' if script.get('google_doc_url') else '無'}，audio_url={'有' if episode.get('audio_url') else '無'}。"),
        tagged("cost", f"總成本 {cost_text(run.get('cost_usd'))}。"),
        tagged("time", f"總耗時 {seconds_text(run.get('duration_ms'))}。"),
    ]


def _compose_daily_podcast_failure_log_summary(result: dict[str, object]) -> list[str]:
    return [
        tagged(
            "warn",
            (
                f"W9 Daily Podcast 失敗在 {result.get('failed_step') or 'unknown'}："
                f"{result.get('error') or 'unknown error'}。"
            ),
        ),
        tagged("cost", f"失敗前已記錄成本 {cost_text(result.get('cost_usd'))}。"),
        tagged("time", f"總耗時 {seconds_text(result.get('duration_ms'))}。"),
    ]
