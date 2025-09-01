import json
from typing import Dict, Any, AsyncGenerator
import asyncio
import traceback
from bs4 import BeautifulSoup

from .pharma_seo_optimizer import SeoOptimizerAgent

# --- Funções Singleton ---
# (sem alterações)
_prompt_manager = None
_gemini_client = None

def _get_prompt_manager():
    global _prompt_manager
    if _prompt_manager is None:
        from .prompt_manager import PromptManager
        _prompt_manager = PromptManager()
    return _prompt_manager

def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from .gemini_client import GeminiClient
        _gemini_client = GeminiClient()
    return _gemini_client

# --- Funções dos Agentes ---

def _run_master_generator_agent(product_name: str, product_info: dict) -> Dict[str, Any]:
    """AGENTE PRINCIPAL: Tenta gerar o conteúdo completo."""
    print(f"PIPELINE: Executing Master Generator for '{product_name}'...")
    # ... (código do agente permanece o mesmo)
    prompt = _get_prompt_manager().render(
        "medicamento_generator",
        product_name=product_name,
        product_info=product_info.get("bula_text", "")
    )
    response_raw = _get_gemini_client().execute_prompt(prompt)
    try:
        json_start = response_raw.find('{')
        json_end = response_raw.rfind('}') + 1
        if json_start == -1: raise ValueError("JSON not found.")
        data = json.loads(response_raw[json_start:json_end])
        if not data.get("html_content") or len(data["html_content"]) < 50:
            raise ValueError("HTML content too short.")
        return data
    except Exception as e:
        print(f"ERROR: Master Generator failed: {e}")
        return None

def _run_refiner_agent(product_name: str, product_info: dict, previous_json: dict, qa_feedback: dict) -> Dict[str, Any]:
    """AGENTE REFINADOR: Tenta corrigir um JSON falhado."""
    print(f"PIPELINE: Executing Refiner Agent for '{product_name}'...")
    prompt = _get_prompt_manager().render(
        "refinador_qualidade",
        product_name=product_name,
        bula_text=product_info.get("bula_text", ""),
        previous_json=json.dumps(previous_json, ensure_ascii=False),
        qa_feedback=json.dumps(qa_feedback, ensure_ascii=False)
    )
    response_raw = _get_gemini_client().execute_prompt(prompt)
    try:
        json_start = response_raw.find('{')
        json_end = response_raw.rfind('}') + 1
        if json_start == -1: raise ValueError("JSON not found.")
        return json.loads(response_raw[json_start:json_end])
    except Exception as e:
        print(f"ERROR: Refiner Agent failed: {e}")
        return previous_json # Retorna o anterior em caso de falha

def _run_essentials_generator_agent(product_name: str, product_info: dict) -> Dict[str, Any]:
    """AGENTE FALLBACK: Gera um HTML simples como último recurso."""
    print(f"PIPELINE: All attempts failed. Executing Essentials Fallback Agent for '{product_name}'...")
    # ... (código do agente permanece o mesmo)
    prompt = _get_prompt_manager().render(
        "essentials_generator",
        product_name=product_name,
        product_info=product_info.get("bula_text", "")
    )
    html_content = _get_gemini_client().execute_prompt(prompt)
    return {
        "seo_title": f"{product_name} - Bula, Preço e Para Que Serve",
        "meta_description": f"Encontre aqui informações essenciais sobre {product_name}: para que serve, como funciona e como usar.",
        "html_content": html_content if len(html_content) > 20 else "<p>Falha na extração de conteúdo essencial.</p>"
    }


def _run_seo_auditor_agent(full_page_json: dict) -> Dict[str, Any]:
    """AGENTE DE QUALIDADE: Audita o JSON gerado."""
    # ... (código do agente permanece o mesmo)
    print(f"PIPELINE: Executing Master Auditor...")
    prompt = _get_prompt_manager().render(
        "auditor_seo_tecnico",
        full_page_json=json.dumps(full_page_json, ensure_ascii=False)
    )
    response_raw = _get_gemini_client().execute_prompt(prompt)
    try:
        json_start = response_raw.find('{')
        json_end = response_raw.rfind('}') + 1
        if json_start == -1: raise ValueError("JSON not found in auditor response.")
        return json.loads(response_raw[json_start:json_end])
    except Exception as e:
        print(f"ERROR: Auditor Agent failed: {e}")
        return {"seo_score": 0, "score_breakdown": {"error": {"feedback": "Falha crítica na auditoria."}}}

# --- Orquestrador Principal da Pipeline ---

async def run_seo_pipeline_stream(product_type: str, product_name: str, product_info: Dict[str, Any]) -> AsyncGenerator[str, None]:
    MIN_SCORE_TARGET = 95
    MAX_ATTEMPTS = 2 # 1 tentativa inicial + 1 tentativa de refinamento

    async def _send_event(event_type: str, data: dict) -> str:
        await asyncio.sleep(0.05)
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    try:
        bula_text = product_info.get("bula_text", "")
        if not bula_text: raise ValueError("Texto da bula não fornecido.")

        yield await _send_event("log", {"message": "<b>Iniciando Sistema de Geração Inteligente...</b>", "type": "info"})
        
        current_content_data = None
        final_score = 0

        # --- CICLO DE GERAÇÃO E REFINAMENTO ---
        for attempt in range(1, MAX_ATTEMPTS + 1):
            yield await _send_event("log", {"message": f"<b>--- Ciclo de Qualidade {attempt}/{MAX_ATTEMPTS} ---</b>", "type": "info"})
            
            # Tenta gerar ou refinar o conteúdo
            if attempt == 1:
                yield await _send_event("log", {"message": "<b>Etapa 1:</b> Agente Mestre criando conteúdo...", "type": "info"})
                current_content_data = _run_master_generator_agent(product_name, product_info)
            else:
                yield await _send_event("log", {"message": "⚠️ Score abaixo da meta. Acionando <b>Agente Refinador</b>...", "type": "warning"})
                current_content_data = _run_refiner_agent(product_name, product_info, current_content_data, audit_results)

            # Se a geração/refinamento falhar catastroficamente, sai do ciclo para o fallback
            if current_content_data is None:
                break
            
            # Audita o resultado da tentativa atual
            yield await _send_event("log", {"message": "<b>Etapa 2:</b> Agente de Qualidade inspecionando...", "type": "info"})
            audit_results = _run_seo_auditor_agent(current_content_data)
            final_score = audit_results.get("seo_score", 0)

            # Envia o feedback detalhado para o frontend
            # ... (código de log do score_breakdown permanece o mesmo)
            score_breakdown = audit_results.get("score_breakdown", {})
            for key, value in score_breakdown.items():
                if isinstance(value, dict):
                    feedback = value.get("feedback", "N/A")
                    status_emoji = "✅" if value.get("score") == value.get("max_score") else "⚠️"
                    yield await _send_event("log", {"message": f"{status_emoji} [{key.replace('_', ' ').title()}]: {feedback}", "type": "success" if status_emoji == "✅" else "warning"})


            yield await _send_event("log", {"message": f"<b>Score da Tentativa {attempt}: {final_score}/100</b>", "type": "info"})
            
            # Se atingir a meta, termina o ciclo
            if final_score >= MIN_SCORE_TARGET:
                yield await _send_event("log", {"message": "<b>Qualidade Aprovada!</b>", "type": "success"})
                break

        # --- REDE DE SEGURANÇA (FALLBACK) ---
        if current_content_data is None:
            yield await _send_event("log", {"message": "⚠️ <b>Aviso:</b> Geração e Refinamento falharam. Acionando Agente de Extração Essencial...", "type": "warning"})
            current_content_data = _run_essentials_generator_agent(product_name, product_info)
            # Re-audita o conteúdo do fallback para ter um score final
            audit_results = _run_seo_auditor_agent(current_content_data)
            final_score = audit_results.get("seo_score", 0)
            yield await _send_event("log", {"message": f"<b>Score do Conteúdo Essencial: {final_score}/100</b>", "type": "info"})

        yield await _send_event("log", {"message": f"<b>Ciclos de qualidade finalizados. Score máximo atingido: {final_score}/100.</b>", "type": "info"})

        # --- ETAPA FINAL: EMPACOTAMENTO PARA V-TEX ---
        yield await _send_event("log", {"message": "<b>Etapa Final:</b> Empacotando HTML para V-TEX...", "type": "info"})
        final_html_vtex_safe = SeoOptimizerAgent._finalize_for_vtex(
            current_content_data.get("html_content", "<p>Conteúdo não gerado.</p>")
        )
        
        # --- ENVIO PARA REVISÃO HUMANA ---
        final_data_for_review = {
            "final_score": final_score,
            "final_content": final_html_vtex_safe,
            "seo_title": str(current_content_data.get("seo_title", product_name)),
            "meta_description": str(current_content_data.get("meta_description", "Descrição não gerada."))
        }
        yield await _send_event("done", final_data_for_review)

    except Exception as e:
        traceback.print_exc()
        yield await _send_event("error", {"message": f"Erro crítico na pipeline: {str(e)}", "type": "error"})