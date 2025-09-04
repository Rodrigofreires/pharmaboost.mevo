# worker.py (Versão Final Robusta com Padrão Singleton Seguro)
import json
import time
import random
import traceback
from celery import Celery
from app.gemini_client import GeminiClient
from app.prompt_manager import PromptManager
from app.pharma_seo_optimizer import SeoOptimizerAgent

celery_app = Celery('pharmaBoost.worker', broker='redis://redis:6379/0', backend='redis://redis:6379/0')

# --- Instâncias Singleton para Eficiência ---
# Usamos um padrão para garantir que os clientes sejam criados apenas uma vez por processo worker.
celery_app.gemini_client = None
celery_app.prompt_manager = None

def get_gemini_client():
    if celery_app.gemini_client is None:
        celery_app.gemini_client = GeminiClient()
    return celery_app.gemini_client

def get_prompt_manager():
    if celery_app.prompt_manager is None:
        celery_app.prompt_manager = PromptManager()
    return celery_app.prompt_manager


@celery_app.task(name="pharmaBoost.worker.process_single_item")
def process_single_item(ean_sku: str, product_name: str, bula_text: str):
    """
    Tarefa Celery que processa UM único item de forma síncrona e robusta.
    """
    try:
        gemini_client = get_gemini_client()
        prompt_manager = get_prompt_manager()

        time.sleep(random.uniform(1, 3)) # Pequeno delay para distribuir a carga

        # Etapa 1: Gerar o conteúdo base
        prompt = prompt_manager.render("medicamento_generator", product_name=product_name, product_info=bula_text)
        response_raw = gemini_client.execute_prompt_sync(prompt)
        json_content = json.loads(response_raw) if response_raw and response_raw.strip().startswith('{') else None

        if not json_content or "error" in json_content:
            raise ValueError(f"Falha na geração inicial do conteúdo. Resposta: {response_raw}")

        # Etapa 2: Auditar o conteúdo gerado
        auditor_prompt = prompt_manager.render("auditor_seo_tecnico", full_page_json=json.dumps(json_content))
        audit_response_raw = gemini_client.execute_prompt_sync(auditor_prompt)
        audit_results = json.loads(audit_response_raw) if audit_response_raw and audit_response_raw.strip().startswith('{') else {}
        final_score = audit_results.get("seo_score", 0)

        # Etapa 3: Finalizar o HTML
        final_html = SeoOptimizerAgent._finalize_for_vtex(html_content=json_content.get("html_content", ""), product_name=product_name)
        
        return {
            "status": "SUCCESS",
            "ean_sku": ean_sku,
            "product_name": product_name,
            "final_score": final_score,
            "final_content": final_html,
            "seo_title": json_content.get("seo_title", product_name),
            "meta_description": json_content.get("meta_description", "Descrição não gerada.")
        }

    except Exception as e:
        print(f"ERRO CRÍTICO NO WORKER (SKU: {ean_sku}): {traceback.format_exc()}")
        return { "status": "CRITICAL_FAILURE", "ean_sku": ean_sku, "product_name": product_name, "error": str(e) }