from pydantic import BaseModel
from typing import Dict, List, Literal

class TopDevelopment(BaseModel):
    rank: int
    title: str
    what_happened: str
    why_it_matters: str
    business_implication: str
    who_is_affected: str
    what_to_watch_next: str
    confidence_level: Literal["high", "medium", "low"]
    sources: List[str]

class ResearchOutputSchema(BaseModel):
    date: str
    global_mood: str
    macro_themes: List[str]
    top_developments: List[TopDevelopment]
    watch_next: List[str]
    source_categories: Dict[str, List[str]]
