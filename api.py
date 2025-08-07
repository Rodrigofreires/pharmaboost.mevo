# api.py
from fastapi import FastAPI
from pydantic import BaseModel
from app import use_cases

app = FastAPI(
    title="Gemini Application API",
    description="API para acessar casos de uso baseados no Gemini.",
    version="1.0.0"
)

class SummarizeRequest(BaseModel):
    text: str
    length: int = 50

class SummarizeResponse(BaseModel):
    summary: str

@app.post("/summarize", response_model=SummarizeResponse)
def summarize_endpoint(request: SummarizeRequest):
    """
    Endpoint para sumarizar um texto.
    """
    summary_text = use_cases.summarize_text(request.text, request.length)
    return {"summary": summary_text}

# Para executar: uvicorn api:app --reload