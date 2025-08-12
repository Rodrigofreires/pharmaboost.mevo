# --- Modelos para Análise de Notícia ---
from typing import List, Optional
from pydantic import BaseModel


class AnalyzeNewsRequest(BaseModel):
    url: str

class SubjectiveFragment(BaseModel):
    original_text: str
    classification: str
    justification: str

class AnalyzeNewsResponse(BaseModel):
    materia_veritare: Optional[str] = None
    por_tras_do_texto: Optional[List[SubjectiveFragment]] = None
    error: Optional[str] = None