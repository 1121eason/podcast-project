#!/usr/bin/env python3
"""Generate local A/B podcast style previews without touching production state."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import ssl
import sys
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.clients.openai_client import openai_client
from app.core.config import settings

DEFAULT_SOURCE_URL = "https://informative-ai.zeabur.app/podcasts/recent?limit=1"
DEFAULT_OUT_DIR = Path("/private/tmp/podcast_previews")
DEFAULT_SECONDS = 60
DEFAULT_CHARS_PER_MINUTE = 350
DEFAULT_REWRITE_MODEL = os.getenv("PODCAST_PREVIEW_REWRITE_MODEL", "gpt-5-mini")
DEFAULT_OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_OPENAI_TTS_VOICE = "onyx"
DEFAULT_OPENAI_TTS_SPEED = 1.2
DEFAULT_STYLE_PRESET = "warm_emotional"
RIGID_LABELS = ("發生什麼：", "為什麼重要：", "影響誰：", "接下來看什麼：", "接下來看：")
TRADITIONAL_REPLACEMENTS = {
    "与此同时": "同時",
    "为": "為",
    "会": "會",
    "这": "這",
    "个": "個",
    "节": "節",
    "气": "氣",
    "数": "數",
    "据": "據",
    "产": "產",
    "资": "資",
    "险": "險",
}
STYLE_PRESETS = {
    "natural": {
        "rewrite": (
            "風格：自然、清楚、像單人 podcast 主持人帶聽眾看懂。"
            "可以有承接句，但情緒保持克制。"
        ),
        "tts": (
            "Speak Traditional Chinese in a calm, conversational podcast-host style. "
            "Use natural pacing and gentle emphasis. Avoid news-anchor delivery."
        ),
    },
    "warm_emotional": {
        "rewrite": (
            "風格：更有情緒、更自然，但不要戲劇化。"
            "像一位聰明、有溫度的主持人，正在陪聽眾理解今天世界為什麼有點不穩。"
            "在風險句帶一點緊張感，在轉折句帶一點好奇，在結論句給聽眾一點穩定感。"
            "可以加入少量自然口語承接，例如「好，先抓住這一點」「你可以這樣想」「這裡真正有意思的是」。"
            "情緒要藏在節奏和措辭裡，不要直白說「有點緊張」「我很好奇」這種標籤。"
            "每一句都要有可朗讀的起伏：先鋪陳，再轉折，再落點；避免每句都是同一種平直資訊句。"
        ),
        "tts": (
            "Speak Traditional Chinese like a warm, intelligent podcast host having a focused one-on-one conversation. "
            "Use a clearly expressive but controlled emotional range: thoughtful concern when discussing risk, "
            "genuine curiosity on transitions, and quiet confidence on takeaways. "
            "Sound engaged and alive, as if the host really cares about helping the listener understand the stakes. "
            "Every sentence should have a noticeable pitch contour: rise slightly when introducing a new idea, "
            "dip for serious implications, and land with confidence on the final phrase. "
            "Avoid flat, monotone delivery. Vary intonation more actively than neutral narration, add gentle emphasis to turning points, "
            "use short purposeful pauses before important ideas, and let conclusions breathe briefly even at the faster pace. "
            "Do not sound like a news anchor. Do not be theatrical or hyped."
        ),
    },
}


def _spoken_char_count(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


def _fetch_latest_production_script(source_url: str) -> tuple[dict, str]:
    context = _default_ssl_context()
    with urllib.request.urlopen(source_url, timeout=30, context=context) as response:
        payload = json.loads(response.read().decode("utf-8"))
    scripts = payload.get("scripts") or []
    if not scripts:
        raise ValueError(f"No podcast script found from {source_url}")
    script_doc = scripts[0]
    script = str(script_doc.get("script") or "").strip()
    if not script:
        raise ValueError(f"Latest podcast script is empty: {script_doc.get('script_id')}")
    return script_doc, script


def _default_ssl_context() -> ssl.SSLContext | None:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


def _preview_excerpt(script: str, seconds: int, chars_per_minute: int) -> str:
    target_chars = max(180, int(seconds * chars_per_minute / 60))
    normalized = re.sub(r"\r\n?", "\n", script).strip()
    sentences = re.findall(r"[^。！？!?]+[。！？!?]?", normalized)
    if not sentences:
        return normalized[:target_chars]

    parts: list[str] = []
    total = 0
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        parts.append(sentence)
        total += _spoken_char_count(sentence)
        if total >= target_chars:
            break
    return "\n".join(parts).strip()


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:text|markdown)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _normalize_traditional_chinese(text: str) -> str:
    normalized = text
    for simplified, traditional in TRADITIONAL_REPLACEMENTS.items():
        normalized = normalized.replace(simplified, traditional)
    normalized = normalized.replace("妳", "你")
    normalized = normalized.replace("Informative AI.", "Informative AI。")
    return normalized


def _style_preset(name: str) -> dict[str, str]:
    if name not in STYLE_PRESETS:
        known = ", ".join(sorted(STYLE_PRESETS))
        raise ValueError(f"Unknown style preset: {name}. Expected one of: {known}")
    return STYLE_PRESETS[name]


def _rewrite_as_natural_host(excerpt: str, model: str, style_preset: str) -> str:
    style = _style_preset(style_preset)
    prompt = f"""請把下面這段 Informative AI podcast 文稿，改寫成 60 秒左右的「單人自然主持」口語稿。

硬性規則：
- 保留第一句「歡迎回到 Informative AI。」
- 使用繁體中文，絕對不要混入簡體字。
- 保留原本事實與決策者語氣，但不要新增未提供的新事實。
- {style["rewrite"]}
- 絕對不要出現：發生什麼：、為什麼重要：、影響誰：、接下來看什麼：、接下來看：
- 不要條列、不要 Markdown、不要像簡報大綱。
- 不要說「請關注」或「值得關注的是」；改成「我們接下來要盯的是」、「真正要聽的是」。
- 不要只是把原文拆短；要加入主持人的承接，例如「換句話說」、「問題在於」、「先抓住這一點」。
- 句子要短，適合 TTS 念出來；要有自然承接，像主持人帶聽眾看懂。
- 輸出只有改寫後文稿，不要解釋。

原文：
{excerpt}
"""
    rewritten, _, _ = openai_client.generate_text(
        prompt,
        model=model,
        temperature=0.5,
        reasoning_effort="low",
    )
    return _normalize_traditional_chinese(_strip_code_fence(rewritten))


def _write_openai_tts_mp3(
    text: str,
    output_path: Path,
    model: str,
    voice: str,
    instructions: str,
    speed: float = 1.0,
) -> None:
    if not openai_client.is_ready:
        raise RuntimeError("OpenAI client is not ready; OPENAI_API_KEY is required")
    response = openai_client.client.audio.speech.create(
        model=model,
        voice=voice,
        input=text,
        instructions=instructions,
        speed=speed,
        response_format="mp3",
    )
    if hasattr(response, "write_to_file"):
        response.write_to_file(output_path)
    else:
        output_path.write_bytes(response.content)


def _text_to_google_ssml(text: str) -> str:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text.strip()) if p.strip()]
    parts: list[str] = []
    for paragraph in paragraphs:
        lines = [html.escape(line.strip(), quote=False) for line in paragraph.splitlines() if line.strip()]
        parts.append('<break time="350ms"/>'.join(lines))
    return "<speak>" + '<break time="700ms"/>'.join(parts) + "</speak>"


def _write_google_tts_wav(text: str, output_path: Path, use_ssml: bool = False) -> None:
    from google.cloud import texttospeech

    client = texttospeech.TextToSpeechClient()
    synthesis_input = (
        texttospeech.SynthesisInput(ssml=_text_to_google_ssml(text))
        if use_ssml
        else texttospeech.SynthesisInput(text=text)
    )
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=texttospeech.VoiceSelectionParams(
            language_code=settings.PODCAST_TTS_LANGUAGE_CODE,
            name=settings.PODCAST_TTS_VOICE,
        ),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        ),
    )
    output_path.write_bytes(response.audio_content)


def generate_preview(args: argparse.Namespace) -> dict[str, object]:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    style = _style_preset(args.style_preset)

    script_doc, script = _fetch_latest_production_script(args.source_url)
    before_text = _preview_excerpt(script, args.seconds, args.chars_per_minute)
    after_text = _rewrite_as_natural_host(before_text, args.rewrite_model, args.style_preset)
    after_suffix = "" if args.style_preset == "natural" else f"_{args.style_preset}"

    before_text_path = out_dir / "before_current.txt"
    after_text_path = out_dir / f"after_natural_host{after_suffix}.txt"
    before_mp3_path = out_dir / "before_current.mp3"
    after_mp3_path = out_dir / f"after_natural_host{after_suffix}.mp3"

    before_text_path.write_text(before_text, encoding="utf-8")
    after_text_path.write_text(after_text, encoding="utf-8")

    if not args.skip_tts:
        _write_openai_tts_mp3(
            before_text,
            before_mp3_path,
            args.tts_model,
            args.voice,
            STYLE_PRESETS["natural"]["tts"],
            speed=1.0,
        )
        _write_openai_tts_mp3(
            after_text,
            after_mp3_path,
            args.tts_model,
            args.voice,
            style["tts"],
            speed=args.speed,
        )

    google_path = None
    if args.google_parity:
        google_path = out_dir / "after_google_parity.wav"
        _write_google_tts_wav(after_text, google_path, use_ssml=args.google_ssml)

    metadata = {
        "source_url": args.source_url,
        "source_script_id": script_doc.get("script_id"),
        "source_episode_title": script_doc.get("episode_title"),
        "source_briefing_date": script_doc.get("briefing_date"),
        "seconds": args.seconds,
        "rewrite_model": args.rewrite_model,
        "style_preset": args.style_preset,
        "openai_tts_model": args.tts_model,
        "openai_tts_voice": args.voice,
        "openai_tts_speed": args.speed,
        "openai_tts_instructions": style["tts"],
        "before_char_count": _spoken_char_count(before_text),
        "after_char_count": _spoken_char_count(after_text),
        "after_contains_rigid_labels": [label for label in RIGID_LABELS if label in after_text],
        "files": {
            "before_text": str(before_text_path),
            "after_text": str(after_text_path),
            "before_mp3": str(before_mp3_path) if not args.skip_tts else None,
            "after_mp3": str(after_mp3_path) if not args.skip_tts else None,
            "google_parity_wav": str(google_path) if google_path else None,
        },
    }
    (out_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--seconds", type=int, default=DEFAULT_SECONDS)
    parser.add_argument("--chars-per-minute", type=int, default=DEFAULT_CHARS_PER_MINUTE)
    parser.add_argument("--rewrite-model", default=DEFAULT_REWRITE_MODEL)
    parser.add_argument("--tts-model", default=DEFAULT_OPENAI_TTS_MODEL)
    parser.add_argument("--voice", default=DEFAULT_OPENAI_TTS_VOICE)
    parser.add_argument("--speed", type=float, default=DEFAULT_OPENAI_TTS_SPEED)
    parser.add_argument("--style-preset", choices=sorted(STYLE_PRESETS), default=DEFAULT_STYLE_PRESET)
    parser.add_argument("--skip-tts", action="store_true")
    parser.add_argument("--google-parity", action="store_true")
    parser.add_argument("--google-ssml", action="store_true")
    return parser.parse_args()


def main() -> None:
    metadata = generate_preview(parse_args())
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
