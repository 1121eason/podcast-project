from app.clients.docs_client import docs_client
from app.clients.gemini_client import gemini_client
from app.core.logging import logger
import os

def generate_and_write_briefing(run_date: str, research_data: dict) -> tuple[str, str, str]:
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "editorial_v1.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    logger.info("Generating briefing text from research data using Gemini")
    briefing_text = gemini_client.generate_briefing(research_data, prompt_template)
    
    logger.info(f"Creating Google Doc for {run_date}")
    title = f"{run_date}_global-intelligence-briefing"
    document = docs_client.create_document(title=title)
    doc_id = document.get("documentId")
    
    if doc_id:
        logger.info(f"Writing to Google Doc {doc_id}")
        docs_client.insert_text(doc_id, briefing_text)
        return f"https://docs.google.com/document/d/{doc_id}/edit", doc_id, briefing_text
    else:
        raise Exception("Failed to create document")
