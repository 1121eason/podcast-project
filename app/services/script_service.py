from app.clients.gemini_client import gemini_client
from app.core.logging import logger
import os

def generate_podcast_script(briefing_text: str) -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "podcast_v1.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    logger.info("Generating podcast script from briefing text")
    script_text = gemini_client.generate_podcast_script(briefing_text, prompt_template)
    return script_text
