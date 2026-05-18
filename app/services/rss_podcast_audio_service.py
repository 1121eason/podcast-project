import logging
import time
from typing import Optional

from google.cloud import texttospeech

from app.clients.firestore_client import firestore_client
from app.core.config import settings
from app.models.podcast import RssPodcastEpisode, RssPodcastScript
from app.services.log_summary_utils import add_duplicate_log_summary, add_log_summary, seconds_text, tagged
from app.services.rss_source_service import utc_now_iso
from app.services.workflow_run_service import complete_workflow_run, fail_workflow_run, start_workflow_run

logger = logging.getLogger(__name__)

TTS_MODEL_NAME = "google-cloud-text-to-speech-long-audio"


def _episode_id(script_id: str) -> str:
    return f"episode_{script_id}"


def _audio_object_path(podcast: RssPodcastScript) -> str:
    return f"podcasts/{podcast.briefing_date}/{podcast.script_id}.wav"


def _gcs_uri(bucket: str, object_path: str) -> str:
    return f"gs://{bucket}/{object_path}"


def _estimate_duration_seconds(podcast: RssPodcastScript) -> int:
    if podcast.duration_estimate_minutes:
        return int(round(podcast.duration_estimate_minutes * 60))
    if podcast.word_count:
        return int(round(podcast.word_count / 350 * 60))
    return 0


def _get_gcs_object_size(bucket_name: str, object_path: str) -> int:
    try:
        from google.cloud import storage
    except Exception as exc:
        logger.warning("Google Cloud Storage client unavailable: %s", exc)
        return 0

    try:
        client = storage.Client(project=settings.GCP_PROJECT_ID or None)
        blob = client.bucket(bucket_name).blob(object_path)
        blob.reload()
        return int(blob.size or 0)
    except Exception as exc:
        logger.warning("Unable to read GCS object metadata for %s/%s: %s", bucket_name, object_path, exc)
        return 0


def synthesize_podcast_audio(
    podcast: RssPodcastScript,
    force: bool = False,
    run_bucket: Optional[str] = None,
) -> dict[str, object]:
    should_skip, workflow_run_id, existing_summary = start_workflow_run(
        "podcast_audio",
        run_bucket,
        {"script_id": podcast.script_id, "force": force, "run_bucket": run_bucket},
    )
    if should_skip:
        out = dict(existing_summary)
        out.update({"skipped_duplicate": True, "run_bucket": run_bucket, "workflow_run_id": workflow_run_id})
        add_duplicate_log_summary(out, "W9 Podcast Audio", run_bucket)
        return out

    try:
        existing = firestore_client.get_podcast_episode_by_script_id(podcast.script_id)
        if existing and existing.audio_url and not force:
            result = existing.model_dump()
            result["run_bucket"] = run_bucket
            result["workflow_run_id"] = workflow_run_id
            result["skipped_duplicate"] = False
            add_log_summary(result, _compose_podcast_audio_log_summary(result, reused=True))
            complete_workflow_run(workflow_run_id, result)
            return result

        if not settings.GCS_AUDIO_BUCKET:
            raise ValueError("GCS_AUDIO_BUCKET is required for podcast audio generation")
        if not settings.GCP_PROJECT_ID:
            raise ValueError("GCP_PROJECT_ID is required for podcast audio generation")
        if not podcast.script.strip():
            raise ValueError(f"podcast script is empty: {podcast.script_id}")

        started = time.monotonic()
        object_path = _audio_object_path(podcast)
        output_uri = _gcs_uri(settings.GCS_AUDIO_BUCKET, object_path)
        parent = f"projects/{settings.GCP_PROJECT_ID}/locations/{settings.PODCAST_TTS_LOCATION}"

        client = texttospeech.TextToSpeechLongAudioSynthesizeClient()
        operation = client.synthesize_long_audio(
            request={
                "parent": parent,
                "input": {"text": podcast.script},
                "voice": {
                    "language_code": settings.PODCAST_TTS_LANGUAGE_CODE,
                    "name": settings.PODCAST_TTS_VOICE,
                },
                # Long Audio Synthesis currently accepts LINEAR16 only; using
                # MP3 returns a 400 before any audio is generated.
                "audio_config": {"audio_encoding": texttospeech.AudioEncoding.LINEAR16},
                "output_gcs_uri": output_uri,
            }
        )
        operation.result(timeout=settings.PODCAST_TTS_TIMEOUT_SECONDS)

        audio_size = _get_gcs_object_size(settings.GCS_AUDIO_BUCKET, object_path)
        episode = RssPodcastEpisode(
            episode_id=_episode_id(podcast.script_id),
            script_id=podcast.script_id,
            briefing_date=podcast.briefing_date,
            generated_at=utc_now_iso(),
            audio_url=output_uri,
            audio_gcs_uri=output_uri,
            audio_bucket=settings.GCS_AUDIO_BUCKET,
            audio_object_path=object_path,
            audio_size_bytes=audio_size,
            audio_duration_seconds=_estimate_duration_seconds(podcast),
            tts_voice=settings.PODCAST_TTS_VOICE,
            tts_model=TTS_MODEL_NAME,
            tts_language_code=settings.PODCAST_TTS_LANGUAGE_CODE,
            tts_location=settings.PODCAST_TTS_LOCATION,
            tts_chars=len(podcast.script),
            tts_cost_usd=0.0,
            tts_duration_ms=int((time.monotonic() - started) * 1000),
        )
        firestore_client.upsert_podcast_episode(episode)
        result = episode.model_dump()
        result["run_bucket"] = run_bucket
        result["workflow_run_id"] = workflow_run_id
        result["skipped_duplicate"] = False
        add_log_summary(result, _compose_podcast_audio_log_summary(result))
        complete_workflow_run(workflow_run_id, result)
        return result
    except Exception as exc:
        fail_workflow_run(workflow_run_id, str(exc))
        raise


def _compose_podcast_audio_log_summary(result: dict[str, object], reused: bool = False) -> list[str]:
    status = "沿用既有 audio" if reused else "完成 TTS audio"
    return [
        tagged(
            "ok",
            (
                f"W9 Audio {status}：episode_id={result.get('episode_id') or 'unknown'}，"
                f"duration 約 {result.get('audio_duration_seconds', 0)} 秒。"
            ),
        ),
        tagged("ok", f"GCS audio={result.get('audio_gcs_uri') or result.get('audio_url') or 'missing'}。"),
        tagged(
            "cost",
            f"TTS chars={result.get('tts_chars', 0)}，cost={result.get('tts_cost_usd', 0)}，voice={result.get('tts_voice') or 'unknown'}。",
        ),
        tagged("time", f"TTS 耗時 {seconds_text(result.get('tts_duration_ms'))}。"),
    ]
