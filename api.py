# api.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict
from app import use_cases
from data.analyze_news_models import AnalyzeNewsRequest, AnalyzeNewsResponse

app = FastAPI(
    title="Gemini Application API",
    description="API para acessar casos de uso baseados no Gemini, incluindo geração de conteúdo para e-commerce farma.",
    version="1.2.0"
)

# --- Configuração do CORS ---
origins = [
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "null"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Modelos de Requisição e Resposta ---

class SummarizeRequest(BaseModel):
    text: str
    length: int = 50

class SummarizeResponse(BaseModel):
    summary: str

class GenerateContentRequest(BaseModel):
    product_name: str
    product_info: Dict

class ContentResponse(BaseModel):
    content: str

# --- Endpoints ---

@app.post("/summarize", response_model=SummarizeResponse, tags=["Análise de Texto"])
def summarize_endpoint(request: SummarizeRequest):
    try:
        summary_text = use_cases.summarize_text(request.text, request.length)
        return {"summary": summary_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {str(e)}")

@app.post("/analyze-news", response_model=AnalyzeNewsResponse, tags=["Análise de Texto"])
def analyze_news_endpoint(request: AnalyzeNewsRequest):
    try:
        analysis_result = use_cases.analyze_news_from_url(request.url)
        return analysis_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {str(e)}")

@app.post("/generate-medicine-content", response_model=ContentResponse, tags=["Geração de Conteúdo Farma"])
def generate_medicine_endpoint(request: GenerateContentRequest):
    try:
        generated_content = use_cases.generate_medicine_content(
            product_name=request.product_name,
            product_info=request.product_info
        )
        return {"content": generated_content}
    except Exception as e:
        print(f"Error in generate_medicine_endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {str(e)}")

@app.post("/generate-vitamin-content", response_model=ContentResponse, tags=["Geração de Conteúdo Farma"])
def generate_vitamin_endpoint(request: GenerateContentRequest):
    try:
        generated_content = use_cases.generate_vitamin_content(
            product_name=request.product_name,
            product_info=request.product_info
        )
        return {"content": generated_content}
    except Exception as e:
        print(f"Error in generate_vitamin_endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {str(e)}")

@app.post("/generate-dermocosmetic-content", response_model=ContentResponse, tags=["Geração de Conteúdo Farma"])
def generate_dermocosmetic_endpoint(request: GenerateContentRequest):
    try:
        generated_content = use_cases.generate_dermocosmetic_content(
            product_name=request.product_name,
            product_info=request.product_info
        )
        return {"content": generated_content}
    except Exception as e:
        print(f"Error in generate_dermocosmetic_endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {str(e)}")

