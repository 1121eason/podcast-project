from pydantic import BaseModel
from typing import Optional

class BriefingData(BaseModel):
    date: str
    title: str
    briefing_text: str
    script_text: Optional[str] = None
