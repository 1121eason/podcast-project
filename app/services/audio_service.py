from app.clients.gemini_client import gemini_client
from app.core.logging import logger
from app.services.script_service import generate_podcast_script

def generate_podcast_audio(briefing_text: str) -> bytes:
    logger.info("Starting podcast pipeline: script -> audio")
    script = generate_podcast_script(briefing_text)
    return generate_podcast_audio_from_script(script)


def generate_podcast_audio_from_script(script_text: str) -> bytes:
    logger.info("Generating audio via TTS")
    return gemini_client.generate_tts(script_text)
