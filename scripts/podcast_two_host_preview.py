#!/usr/bin/env python3
"""Generate a local two-host podcast preview without touching production state."""

from __future__ import annotations

import argparse
import json
import re
import sys
import wave
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.clients.openai_client import openai_client
from scripts.podcast_style_preview import (
    DEFAULT_OPENAI_TTS_MODEL,
    DEFAULT_REWRITE_MODEL,
    DEFAULT_SOURCE_URL,
    _fetch_latest_production_script,
    _normalize_traditional_chinese,
    _preview_excerpt,
    _spoken_char_count,
    _strip_code_fence,
)

DEFAULT_OUT_DIR = Path("/private/tmp/podcast_previews/two_host_onyx_shimmer")
DEFAULT_SECONDS = 75
DEFAULT_CHARS_PER_MINUTE = 390
DEFAULT_MALE_VOICE = "cedar"
DEFAULT_FEMALE_VOICE = "shimmer"
DEFAULT_SPEED = 1.25
DEFAULT_EMOTION_STYLE = "expressive"
TURN_PAUSE_MS = 220
SEGMENT_PAUSE_MS = 420
EMOTION_STYLES = {
    "expressive": {
        "dialogue": (
            "每一句都要帶情緒目的：不是平鋪直敘。風險處有關切，轉折處有好奇，提醒處有一點急迫，結論處穩定。"
            "加入更多自然短反應和語氣墊，例如「對，這裡很關鍵」「嗯，這就麻煩了」「好，這句話要聽仔細」「所以節奏要快一點」。"
            "但不要戲劇化，不要綜藝感，不要故作驚訝。"
        ),
        "male_tts": (
            "Add more emotional color sentence by sentence: concern for risk, urgency for action points, "
            "and calm confidence for conclusions. Emphasize key words naturally, with small pauses before the most important phrases. "
            "Warm, analytical, not theatrical."
        ),
        "female_tts": (
            "Use lively but controlled intonation in every sentence: brighter lift when asking or reframing, "
            "softer concern when risks appear, and energetic clarity when summarizing. "
            "Emphasize contrast words and turning points, and avoid flat delivery."
        ),
    },
    "max_drama": {
        "dialogue": (
            "這是一版找上限的浮誇測試。每一句都要有明顯情緒曲線：開頭抓注意、轉折拉高、風險句下沉、結論重落點。"
            "可以更像 high-energy podcast：更強的驚訝、急迫、好奇和提醒感，但仍不要新增事實。"
            "多用自然短句和反應，例如「等一下，這裡很關鍵」「這就不是小事了」「好，這句話真的要聽仔細」「所以，節奏要立刻調整」。"
            "允許比正式節目更戲劇化，但不要變綜藝，不要尖叫，不要失控。"
        ),
        "male_tts": (
            "This is a deliberately exaggerated emotional range test. Use maximum controlled pitch variation in every sentence: "
            "rise strongly on setup, dip noticeably on risk, add urgency on action points, and land hard on takeaways. "
            "Use dramatic but still professional emphasis, stronger pauses before key phrases, and more animated delivery than a normal podcast. "
            "Do not shout, but push the performance close to the upper limit of expressive podcast narration."
        ),
        "female_tts": (
            "This is a deliberately exaggerated emotional range test. Use bright, high-energy, expressive intonation in every sentence: "
            "strong upward lift on reactions, warmer concern on risk, and vivid emphasis on contrast words. "
            "Sound animated and genuinely engaged, close to the upper limit of a professional podcast co-host. "
            "Do not shout and do not become comedic, but avoid any flat delivery."
        ),
    },
    "flow_max": {
        "dialogue": (
            "這是一版『自然流動優先』的高情緒測試。重點不是每句都塞情緒詞，而是讓聲音有一條連續的語氣弧線。"
            "請寫 10 到 12 個 turns；每個 turn 以 2 句左右為主，讓同一位主持人在同一段裡完成鋪陳、轉折、落點。"
            "不要切成太多短句，否則聲音會變平；也不要一問一答。要像兩位主持人真的在錄音室聊天：接住上一句、補一個觀察、再把主線推進。"
            "可以用更口語的節奏詞，例如「你看」「等一下」「這裡先停一下」「我會這樣想」「這句話其實很重」。"
            "每一句都要有情緒意圖：提醒句帶一點急迫，風險句帶一點壓力，轉折句帶好奇，收束句要穩。"
            "每段要有明顯起伏：開頭拉起注意，風險句壓低，關鍵詞加重，最後一句收穩。"
            "保持聊天感：HOST_B 可以短反應，但短反應後要補一個聽眾會在意的角度；HOST_A 要接住 HOST_B，而不是直接換下一題。"
            "可以用「對，這就是重點」「沒錯，而且下一層是」「先把這句放大」，但不要變成逐題問答。"
            "可以比正式節目更有情緒，但不要綜藝化，不要尖叫。"
        ),
        "male_tts": (
            "Use a flowing, continuous emotional arc across the whole turn, not isolated sentence-by-sentence reading. "
            "Start with attention, build through the middle, dip lower for risk, and land firmly on the final phrase. "
            "Every sentence needs emotional intent: urgency for action, concern for risk, curiosity for transitions, and confidence for conclusions. "
            "Use expressive pitch variation, stronger emphasis on key market terms, and natural micro-pauses. "
            "Sound like a mature host thinking out loud with conviction, not reading a script."
        ),
        "female_tts": (
            "Use a flowing conversational arc across the whole turn, with bright energy and natural reactions. "
            "Let the voice rise when reframing, soften when acknowledging risk, and land clearly on summary phrases. "
            "Every sentence should carry a small emotional move: surprise, concern, curiosity, or confident summary. "
            "Make the delivery feel spontaneous, connected to the male host, and emotionally alive. "
            "Avoid flat assistant-like narration."
        ),
    },
}


def _emotion_style(name: str) -> dict[str, str]:
    if name not in EMOTION_STYLES:
        known = ", ".join(sorted(EMOTION_STYLES))
        raise ValueError(f"Unknown emotion style: {name}. Expected one of: {known}")
    return EMOTION_STYLES[name]


def _rewrite_as_two_host_dialogue(excerpt: str, model: str, emotion_style: str) -> str:
    style = _emotion_style(emotion_style)
    prompt = f"""請把下面 Informative AI podcast 文稿改寫成 75 秒左右的雙主持對談。

主持人設定：
- HOST_A：男聲，成熟、穩重、有情緒起伏，負責主線判斷。
- HOST_B：女聲，自然、聰明、有好奇感，負責追問、轉折、幫聽眾把重點講白。

硬性規則：
- 第一行必須由 HOST_A 說：「歡迎回到 Informative AI。」
- 每一行只能是 `HOST_A: ...` 或 `HOST_B: ...`
- 使用繁體中文，絕對不要混入簡體字。
- 保留原本事實，不要新增未提供的新事實。
- 不要出現：發生什麼：、為什麼重要：、影響誰：、接下來看什麼：、接下來看：
- 不要條列、不要 Markdown、不要括號舞台指示。
- 兩位主持人要像真正在同一個錄音室聊天，不要一問一答，不要像訪談逐字稿。
- HOST_A 不要每次都說「沒錯」「正確」「是的」；要自然接續、推進主線。
- HOST_B 不要一直提問；她可以用反應、補充、短句轉場來讓節奏更自然，例如「這裡很關鍵」、「這其實會牽動一整串資產」、「好，那我會先看兩個地方」。
- 每個 turn 以 1-2 句為主，偶爾一句短反應即可；不要每行都像完整論述。
- 每句要短，有上下起伏；讓語氣像自然 podcast 對談，而不是輪流朗讀。
- {style["dialogue"]}
- 輸出只有對談稿，不要解釋。

原文：
{excerpt}
"""
    rewritten, _, _ = openai_client.generate_text(
        prompt,
        model=model,
        temperature=0.6,
        reasoning_effort="low",
    )
    return _normalize_traditional_chinese(_strip_code_fence(rewritten))


def _parse_dialogue(dialogue: str) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    for raw_line in dialogue.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^(HOST_[AB])\s*[:：]\s*(.+)$", line)
        if not match:
            continue
        speaker, text = match.groups()
        text = text.strip()
        if text:
            turns.append((speaker, text))
    if not turns:
        raise ValueError("No HOST_A/HOST_B dialogue turns found")
    return turns


def _tts_instructions(speaker: str, emotion_style: str) -> str:
    style = _emotion_style(emotion_style)
    if speaker == "HOST_A":
        return (
            "Speak Traditional Chinese as a mature male podcast host with a low, steady, expressive voice. "
            "Use clear pitch contour in every sentence: rise slightly for setup, dip for serious implications, "
            "and land confidently on the final phrase. "
            + style["male_tts"]
        )
    return (
        "Speak Traditional Chinese as a brighter, higher-pitched female podcast co-host with warm curiosity and natural energy. "
        "Sound spontaneous and conversational, like you are reacting in real time rather than reading a script. "
        + style["female_tts"]
        + " "
        "Do not sound like a news anchor, assistant, or commercial voice-over."
    )


def _write_tts_wav(
    text: str,
    output_path: Path,
    voice: str,
    speed: float,
    speaker: str,
    emotion_style: str,
) -> None:
    if not openai_client.is_ready:
        raise RuntimeError("OpenAI client is not ready; OPENAI_API_KEY is required")
    response = openai_client.client.audio.speech.create(
        model=DEFAULT_OPENAI_TTS_MODEL,
        voice=voice,
        input=text,
        instructions=_tts_instructions(speaker, emotion_style),
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
        # OpenAI WAV responses use streaming-friendly RIFF sizes (0xFFFFFFFF),
        # so do not copy nframes from the source header. Let wave.py calculate
        # the final length from the bytes we actually write.
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
                pause = SEGMENT_PAUSE_MS if idx % 2 else TURN_PAUSE_MS
                out.writeframes(_silence(params, pause))


def generate_two_host_preview(args: argparse.Namespace) -> dict[str, object]:
    out_dir = Path(args.out_dir)
    turns_dir = out_dir / "turns"
    turns_dir.mkdir(parents=True, exist_ok=True)

    script_doc, script = _fetch_latest_production_script(args.source_url)
    excerpt = _preview_excerpt(script, args.seconds, args.chars_per_minute)
    dialogue = _rewrite_as_two_host_dialogue(excerpt, args.rewrite_model, args.emotion_style)
    turns = _parse_dialogue(dialogue)
    dialogue_path = out_dir / "two_host_dialogue.txt"
    dialogue_path.write_text(dialogue, encoding="utf-8")

    segment_paths: list[Path] = []
    for idx, (speaker, text) in enumerate(turns, start=1):
        voice = args.male_voice if speaker == "HOST_A" else args.female_voice
        path = turns_dir / f"{idx:02d}_{speaker}_{voice}.wav"
        _write_tts_wav(
            text,
            path,
            voice=voice,
            speed=args.speed,
            speaker=speaker,
            emotion_style=args.emotion_style,
        )
        segment_paths.append(path)

    output_wav = out_dir / f"two_host_{args.male_voice}_{args.female_voice}.wav"
    _concat_wavs(segment_paths, output_wav)

    metadata = {
        "source_url": args.source_url,
        "source_script_id": script_doc.get("script_id"),
        "source_episode_title": script_doc.get("episode_title"),
        "source_briefing_date": script_doc.get("briefing_date"),
        "seconds": args.seconds,
        "rewrite_model": args.rewrite_model,
        "tts_model": DEFAULT_OPENAI_TTS_MODEL,
        "male_voice": args.male_voice,
        "female_voice": args.female_voice,
        "speed": args.speed,
        "emotion_style": args.emotion_style,
        "turn_count": len(turns),
        "dialogue_char_count": _spoken_char_count(dialogue),
        "files": {
            "dialogue": str(dialogue_path),
            "combined_wav": str(output_wav),
            "turns_dir": str(turns_dir),
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
    parser.add_argument("--male-voice", default=DEFAULT_MALE_VOICE)
    parser.add_argument("--female-voice", default=DEFAULT_FEMALE_VOICE)
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED)
    parser.add_argument("--emotion-style", choices=sorted(EMOTION_STYLES), default=DEFAULT_EMOTION_STYLE)
    return parser.parse_args()


def main() -> None:
    metadata = generate_two_host_preview(parse_args())
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
