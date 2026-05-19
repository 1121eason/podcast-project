import html
import logging
import re
import tempfile
import time
import wave
from pathlib import Path
from typing import Optional

from google.cloud import texttospeech

from app.clients.openai_client import openai_client
from app.clients.firestore_client import firestore_client
from app.core.config import settings
from app.models.podcast import RssPodcastEpisode, RssPodcastScript
from app.services.log_summary_utils import add_duplicate_log_summary, add_log_summary, seconds_text, tagged
from app.services.rss_source_service import utc_now_iso
from app.services.workflow_run_service import complete_workflow_run, fail_workflow_run, start_workflow_run

logger = logging.getLogger(__name__)

GOOGLE_TTS_MODEL_NAME = "google-cloud-text-to-speech-long-audio"
OPENAI_AUDIO_STYLE = "two_host_flow_max"
SSML_PARAGRAPH_BREAK_MS = 700
SSML_LINE_BREAK_MS = 350
OPENAI_TURN_PAUSE_MS = 220
OPENAI_SEGMENT_PAUSE_MS = 420
MAX_TTS_TURN_CHARS = 900
HOST_LINE_RE = re.compile(r"^(HOST_[AB])\s*[:：]\s*(.+)$")
RIGID_REPORT_LABELS = (
    "發生什麼：",
    "為什麼重要：",
    "影響誰：",
    "接下來看什麼：",
    "接下來看：",
)

TWO_HOST_DIALOGUE_INSTRUCTIONS = (
    "這是一版『自然流動優先』的高情緒 production 音訊稿。"
    "重點不是每句都塞情緒詞，而是讓聲音有一條連續的語氣弧線。"
    "每個 turn 以 2 到 4 句為主，讓同一位主持人在同一段裡完成鋪陳、轉折、落點。"
    "不要切成太多短句，否則聲音會變平；也不要一問一答。"
    "要像兩位主持人真的在錄音室聊天：接住上一句、補一個觀察、再把主線推進。"
    "可以用更口語的節奏詞，例如「你看」「等一下」「這裡先停一下」「我會這樣想」「這句話其實很重」。"
    "每一句都要有情緒意圖：提醒句帶一點急迫，風險句帶一點壓力，轉折句帶好奇，收束句要穩。"
    "保持 Informative AI 的冷靜、清楚、給決策者聽的語氣，不要綜藝化，不要尖叫。"
)


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


def _script_to_ssml(script: str) -> str:
    normalized = re.sub(r"\r\n?", "\n", script.strip())
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", normalized) if p.strip()]
    spoken_parts: list[str] = []
    for paragraph in paragraphs:
        lines = [line.strip() for line in paragraph.split("\n") if line.strip()]
        escaped_lines = [html.escape(line, quote=False) for line in lines]
        spoken_parts.append(
            f'<break time="{SSML_LINE_BREAK_MS}ms"/>'.join(escaped_lines)
        )
    return (
        "<speak>"
        + f'<break time="{SSML_PARAGRAPH_BREAK_MS}ms"/>'.join(spoken_parts)
        + "</speak>"
    )


def _tts_input_for_script(script: str) -> tuple[dict[str, str], str]:
    mode = (settings.PODCAST_TTS_INPUT_MODE or "text").strip().lower()
    if mode == "ssml":
        return {"ssml": _script_to_ssml(script)}, "ssml"
    return {"text": script}, "text"


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


def _upload_file_to_gcs(local_path: Path, bucket_name: str, object_path: str, content_type: str) -> None:
    try:
        from google.cloud import storage
    except Exception as exc:
        raise RuntimeError(f"Google Cloud Storage client unavailable: {exc}") from exc

    client = storage.Client(project=settings.GCP_PROJECT_ID or None)
    blob = client.bucket(bucket_name).blob(object_path)
    blob.upload_from_filename(str(local_path), content_type=content_type)


def _strip_code_fence(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _normalize_traditional_chinese(text: str) -> str:
    replacements = {
        "妳": "你",
        "为": "為",
        "这": "這",
        "个": "個",
        "会": "會",
        "关": "關",
        "键": "鍵",
        "说": "說",
        "对": "對",
        "国": "國",
        "发": "發",
        "现": "現",
        "经": "經",
        "济": "濟",
        "产": "產",
        "业": "業",
        "风": "風",
        "险": "險",
        "题": "題",
        "数": "數",
        "据": "據",
        "后": "後",
        "间": "間",
        "级": "級",
        "议": "議",
        "压": "壓",
        "变": "變",
        "让": "讓",
        "听": "聽",
        "众": "眾",
        "点": "點",
        "节": "節",
    }
    for simplified, traditional in replacements.items():
        text = text.replace(simplified, traditional)
    return text


def _rewrite_script_as_two_host_dialogue(podcast: RssPodcastScript) -> tuple[str, int, int]:
    if not openai_client.is_ready:
        raise RuntimeError("OpenAI client is not ready; OPENAI_API_KEY is required for podcast OpenAI TTS")

    prompt = f"""請把下面 Informative AI podcast 完整文稿，改寫成 production 可用的雙主持對談音訊稿。

重要前提：
- 原始文稿的內容判斷、主題順序、跨日連續性、重複防止邏輯都很重要。不要重寫成新的節目，不要新增未提供的新事實。
- 你的任務只是把「單人朗讀稿」改成「雙主持自然對話稿」，讓 TTS 聽起來更有互動感、更自然。
- 保留原文主要資訊密度；可以用口語轉述，但不要刪掉關鍵事件、影響對象、時間節點、watch points。

主持人設定：
- HOST_A：男聲，成熟、穩重、有情緒起伏，負責主線判斷。
- HOST_B：女聲，自然、聰明、有好奇感，負責反應、轉折、幫聽眾把重點講白。

硬性規則：
- 第一行必須由 HOST_A 說：「歡迎回到 Informative AI。」
- 最後一個 turn 必須自然包含：「感謝各位今天的收聽，明天見。」
- 每一行只能是 `HOST_A: ...` 或 `HOST_B: ...`
- 使用繁體中文，絕對不要混入簡體字。
- 不要出現：發生什麼：、為什麼重要：、影響誰：、接下來看什麼：、接下來看：
- 不要條列、不要 Markdown、不要括號舞台指示。
- 兩位主持人要像真正在同一個錄音室聊天，不要一問一答，不要像訪談逐字稿。
- HOST_A 不要每次都說「沒錯」「正確」「是的」；要自然接續、推進主線。
- HOST_B 不要一直提問；她可以用反應、補充、短句轉場來讓節奏更自然。
- {TWO_HOST_DIALOGUE_INSTRUCTIONS}
- 輸出只有對談稿，不要解釋。

原始 episode title：
{podcast.episode_title}

原始文稿：
{podcast.script}
"""
    rewritten, dialogue_input_tokens, dialogue_output_tokens = openai_client.generate_text(
        prompt,
        model=settings.PODCAST_OPENAI_DIALOGUE_MODEL,
        temperature=0.6,
        reasoning_effort=settings.PODCAST_OPENAI_DIALOGUE_REASONING_EFFORT,
    )
    dialogue = _normalize_traditional_chinese(_strip_code_fence(rewritten))
    for label in RIGID_REPORT_LABELS:
        if label in dialogue:
            raise ValueError(f"OpenAI dialogue rewrite leaked report label: {label}")
    return dialogue, dialogue_input_tokens, dialogue_output_tokens


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"([。！？!?])", text.strip())
    sentences: list[str] = []
    for idx in range(0, len(parts), 2):
        body = parts[idx].strip()
        if not body:
            continue
        punctuation = parts[idx + 1] if idx + 1 < len(parts) else ""
        sentences.append(f"{body}{punctuation}".strip())
    return sentences or [text.strip()]


def _split_long_turn(speaker: str, text: str) -> list[tuple[str, str]]:
    if len(text) <= MAX_TTS_TURN_CHARS:
        return [(speaker, text)]

    chunks: list[tuple[str, str]] = []
    current = ""
    for sentence in _split_sentences(text):
        if current and len(current) + len(sentence) + 1 > MAX_TTS_TURN_CHARS:
            chunks.append((speaker, current.strip()))
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append((speaker, current.strip()))
    return chunks


def _parse_dialogue(dialogue: str) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    for raw_line in dialogue.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = HOST_LINE_RE.match(line)
        if not match:
            continue
        speaker, text = match.groups()
        text = re.sub(r"（[^）]*(?:停頓|語氣|笑|音樂|轉場)[^）]*）", "", text).strip()
        if text:
            turns.extend(_split_long_turn(speaker, text))
    if not turns:
        raise ValueError("No HOST_A/HOST_B dialogue turns found")
    if not turns[0][1].startswith("歡迎回到 Informative AI"):
        first_speaker, first_text = turns[0]
        turns[0] = (first_speaker, "歡迎回到 Informative AI。" + first_text.lstrip("。.\n "))
    if not turns[-1][1].rstrip().endswith("感謝各位今天的收聽，明天見。"):
        last_speaker, last_text = turns[-1]
        turns[-1] = (last_speaker, f"{last_text.rstrip()} 感謝各位今天的收聽，明天見。")
    return turns


def _openai_tts_instructions(speaker: str) -> str:
    if speaker == "HOST_A":
        return (
            "Speak Traditional Chinese as a mature male podcast host with a low, steady, expressive voice. "
            "Use a flowing, continuous emotional arc across the whole turn, not isolated sentence-by-sentence reading. "
            "Start with attention, build through the middle, dip lower for risk, and land firmly on the final phrase. "
            "Every sentence needs emotional intent: urgency for action, concern for risk, curiosity for transitions, and confidence for conclusions. "
            "Use expressive pitch variation, stronger emphasis on key market terms, and natural micro-pauses. "
            "Sound like a mature host thinking out loud with conviction, not reading a script."
        )
    return (
        "Speak Traditional Chinese as a brighter, higher-pitched female podcast co-host with warm curiosity and natural energy. "
        "Use a flowing conversational arc across the whole turn, with bright energy and natural reactions. "
        "Let the voice rise when reframing, soften when acknowledging risk, and land clearly on summary phrases. "
        "Every sentence should carry a small emotional move: surprise, concern, curiosity, or confident summary. "
        "Make the delivery feel spontaneous, connected to the male host, and emotionally alive. "
        "Avoid flat assistant-like narration. Do not sound like a news anchor, assistant, or commercial voice-over."
    )


def _write_openai_tts_wav(
    text: str,
    output_path: Path,
    voice: str,
    speed: float,
    speaker: str,
) -> None:
    if not openai_client.is_ready:
        raise RuntimeError("OpenAI client is not ready; OPENAI_API_KEY is required for podcast OpenAI TTS")
    response = openai_client.client.audio.speech.create(
        model=settings.PODCAST_OPENAI_TTS_MODEL,
        voice=voice,
        input=text,
        instructions=_openai_tts_instructions(speaker),
        speed=speed,
        response_format="wav",
    )
    if hasattr(response, "write_to_file"):
        response.write_to_file(output_path)
    else:
        output_path.write_bytes(response.content)


def _silence(params: wave._wave_params, pause_ms: int) -> bytes:
    frame_count = int(params.framerate * pause_ms / 1000)
    return b"\x00" * frame_count * params.nchannels * params.sampwidth


def _concat_wavs(segment_paths: list[Path], output_path: Path) -> None:
    if not segment_paths:
        raise ValueError("No WAV segments to concatenate")

    with wave.open(str(segment_paths[0]), "rb") as first:
        params = first.getparams()
        nchannels = params.nchannels
        sampwidth = params.sampwidth
        framerate = params.framerate
        comptype = params.comptype
        compname = params.compname

    with wave.open(str(output_path), "wb") as out:
        out.setnchannels(nchannels)
        out.setsampwidth(sampwidth)
        out.setframerate(framerate)
        out.setcomptype(comptype, compname)
        for idx, path in enumerate(segment_paths):
            with wave.open(str(path), "rb") as segment:
                if segment.getparams()[:3] != params[:3]:
                    raise ValueError(f"WAV params mismatch: {path}")
                frame_count = (path.stat().st_size - 44) // (nchannels * sampwidth)
                out.writeframes(segment.readframes(frame_count))
            if idx < len(segment_paths) - 1:
                pause = OPENAI_SEGMENT_PAUSE_MS if idx % 2 else OPENAI_TURN_PAUSE_MS
                out.writeframes(_silence(params, pause))


def _synthesize_openai_two_host_audio(podcast: RssPodcastScript, output_path: Path) -> dict[str, object]:
    dialogue, dialogue_input_tokens, dialogue_output_tokens = _rewrite_script_as_two_host_dialogue(podcast)
    turns = _parse_dialogue(dialogue)
    segment_paths: list[Path] = []
    turns_dir = output_path.parent / "turns"
    turns_dir.mkdir(parents=True, exist_ok=True)

    for idx, (speaker, text) in enumerate(turns, start=1):
        voice = (
            settings.PODCAST_OPENAI_TTS_MALE_VOICE
            if speaker == "HOST_A"
            else settings.PODCAST_OPENAI_TTS_FEMALE_VOICE
        )
        segment_path = turns_dir / f"{idx:03d}_{speaker}_{voice}.wav"
        _write_openai_tts_wav(
            text=text,
            output_path=segment_path,
            voice=voice,
            speed=settings.PODCAST_OPENAI_TTS_SPEED,
            speaker=speaker,
        )
        segment_paths.append(segment_path)

    _concat_wavs(segment_paths, output_path)
    return {
        "dialogue_char_count": len(dialogue),
        "dialogue_input_tokens": dialogue_input_tokens,
        "dialogue_output_tokens": dialogue_output_tokens,
        "turn_count": len(turns),
        "tts_chars": sum(len(text) for _, text in turns),
    }


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
        provider = (settings.PODCAST_TTS_PROVIDER or "google").strip().lower()
        tts_chars = len(podcast.script)
        tts_model = ""
        tts_voice = settings.PODCAST_TTS_VOICE
        tts_language_code = settings.PODCAST_TTS_LANGUAGE_CODE
        tts_location = settings.PODCAST_TTS_LOCATION

        if provider == "openai":
            with tempfile.TemporaryDirectory(prefix="podcast_openai_tts_") as tmp_dir:
                local_audio = Path(tmp_dir) / "podcast.wav"
                openai_meta = _synthesize_openai_two_host_audio(podcast, local_audio)
                _upload_file_to_gcs(local_audio, settings.GCS_AUDIO_BUCKET, object_path, "audio/wav")
            tts_chars = int(openai_meta.get("tts_chars") or tts_chars)
            tts_voice = (
                f"{settings.PODCAST_OPENAI_TTS_MALE_VOICE}+"
                f"{settings.PODCAST_OPENAI_TTS_FEMALE_VOICE}"
            )
            tts_model = (
                f"openai:{settings.PODCAST_OPENAI_TTS_MODEL}:{OPENAI_AUDIO_STYLE}:"
                f"{settings.PODCAST_OPENAI_DIALOGUE_MODEL}:turns={openai_meta.get('turn_count', 0)}:"
                f"speed={settings.PODCAST_OPENAI_TTS_SPEED}"
            )
            tts_language_code = "zh-TW"
            tts_location = "openai"
        elif provider == "google":
            parent = f"projects/{settings.GCP_PROJECT_ID}/locations/{settings.PODCAST_TTS_LOCATION}"
            tts_input, tts_input_mode = _tts_input_for_script(podcast.script)

            client = texttospeech.TextToSpeechLongAudioSynthesizeClient()
            request = {
                "parent": parent,
                "input": tts_input,
                "voice": {
                    "language_code": settings.PODCAST_TTS_LANGUAGE_CODE,
                    "name": settings.PODCAST_TTS_VOICE,
                },
                # Long Audio Synthesis currently accepts LINEAR16 only; using
                # MP3 returns a 400 before any audio is generated.
                "audio_config": {"audio_encoding": texttospeech.AudioEncoding.LINEAR16},
                "output_gcs_uri": output_uri,
            }
            try:
                operation = client.synthesize_long_audio(request=request)
                operation.result(timeout=settings.PODCAST_TTS_TIMEOUT_SECONDS)
            except Exception:
                if tts_input_mode != "ssml":
                    raise
                logger.warning("SSML long-audio synthesis failed; retrying with plain text.", exc_info=True)
                tts_input_mode = "text_fallback"
                request["input"] = {"text": podcast.script}
                operation = client.synthesize_long_audio(request=request)
                operation.result(timeout=settings.PODCAST_TTS_TIMEOUT_SECONDS)
            tts_model = f"{GOOGLE_TTS_MODEL_NAME}:{tts_input_mode}"
        else:
            raise ValueError(f"Unsupported PODCAST_TTS_PROVIDER: {settings.PODCAST_TTS_PROVIDER}")

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
            tts_voice=tts_voice,
            tts_model=tts_model,
            tts_language_code=tts_language_code,
            tts_location=tts_location,
            tts_chars=tts_chars,
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
