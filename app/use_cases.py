# app/use_cases.py (Versão Final com Backoff Robusto e Validação de Agentes)
import json
import traceback
import re
import asyncio
from typing import Dict, Any, AsyncGenerator

from google.api_core import exceptions
from .pharma_seo_optimizer import SeoOptimizerAgent

# --- Funções de Gerenciamento de Instância (sem alterações) ---
_prompt_manager = None
def _get_prompt_manager():
    global _prompt_manager
    if _prompt_manager is None:
        from .prompt_manager import PromptManager
        _prompt_manager = PromptManager()
    return _prompt_manager

_gemini_client = None
def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from .gemini_client import GeminiClient
        _gemini_client = GeminiClient()
    return _gemini_client

# --- Funções Auxiliares ---
def _extract_json_from_string(text: str) -> Dict[str, Any]:
    if not text:
        print("ERROR: Texto de entrada para extração de JSON está vazio.")
        return None
    json_match = re.search(r'```json\s*(\{.*?\})\s*```|(\{.*?\})', text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1) or json_match.group(2)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None
    return None

async def _execute_prompt_async_with_backoff(prompt: str, max_retries: int = 5) -> str | None:
    wait_time = 2
    for attempt in range(max_retries):
        try:
            return await _get_gemini_client().execute_prompt_async(prompt)
        except (exceptions.ServiceUnavailable, exceptions.ResourceExhausted, RuntimeError) as e:
            if "503" in str(e) or "overloaded" in str(e).lower() or isinstance(e, exceptions.ServiceUnavailable):
                error_type = "Servidor sobrecarregado (503)"
                print(f"WARN: {error_type} (tentativa {attempt + 1}/{max_retries}). Aguardando {wait_time}s...")
                await asyncio.sleep(wait_time)
                wait_time = min(wait_time * 2, 60)
            else:
                print(f"ERROR: Erro irrecuperável na chamada da API: {e}")
                return None
        except Exception as e:
            print(f"ERROR: Erro inesperado e irrecuperável: {e}")
            return None
            
    print("ERROR: Limite máximo de tentativas atingido. A API continua indisponível.")
    return None

async def _run_master_generator_agent(product_name: str, product_info: dict) -> Dict[str, Any] | None:
    prompt = _get_prompt_manager().render("medicamento_generator", product_name=product_name, product_info=product_info.get("bula_text", ""))
    response_raw = await _execute_prompt_async_with_backoff(prompt)
    if not response_raw: return None
    return _extract_json_from_string(response_raw)

async def _run_refiner_agent(product_name: str, product_info: dict, previous_json: dict, qa_feedback: dict) -> Dict[str, Any]:
    prompt = _get_prompt_manager().render("refinador_qualidade", product_name=product_name, bula_text=product_info.get("bula_text", ""), previous_json=json.dumps(previous_json, ensure_ascii=False), qa_feedback=json.dumps(qa_feedback, ensure_ascii=False))
    response_raw = await _execute_prompt_async_with_backoff(prompt)
    if response_raw and (data := _extract_json_from_string(response_raw)):
        return data
    return previous_json

async def _run_essentials_generator_agent(product_name: str, product_info: dict) -> Dict[str, Any]:
    prompt = _get_prompt_manager().render("essentials_generator", product_name=product_name, product_info=product_info.get("bula_text", ""))
    html_content = await _execute_prompt_async_with_backoff(prompt) or "<p>Falha crítica na geração.</p>"
    return {
        "seo_title": f"{product_name} - Para que serve e como usar",
        "meta_description": f"Informações essenciais sobre {product_name}. Consulte a bula.",
        "html_content": html_content
    }

async def _run_seo_auditor_agent(full_page_json: dict) -> Dict[str, Any]:
    prompt = _get_prompt_manager().render("auditor_seo_tecnico", full_page_json=json.dumps(full_page_json, ensure_ascii=False))
    response_raw = await _execute_prompt_async_with_backoff(prompt)
    if response_raw and (data := _extract_json_from_string(response_raw)):
        return data
    return {"seo_score": 0, "score_breakdown": {"error": {"feedback": "Falha crítica na auditoria."}}}


async def run_seo_pipeline_stream(product_type: str, product_name: str, product_info: Dict[str, Any]) -> AsyncGenerator[str, None]:
    MIN_SCORE_TARGET = 95
    MAX_ATTEMPTS = 2

    async def _send_event(event_type: str, data: dict) -> str:
        await asyncio.sleep(0.05)
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    try:
        if not product_info.get("bula_text"): raise ValueError("Texto da bula não fornecido.")

        yield await _send_event("log", {"message": f"<b>Iniciando Geração para '{product_name}'...</b>", "type": "info"})
        
        current_content_data = None
        final_score = 0
        
        for attempt in range(1, MAX_ATTEMPTS + 1):
            yield await _send_event("log", {"message": f"<b>--- Ciclo de Qualidade {attempt}/{MAX_ATTEMPTS} ---</b>", "type": "info"})
            
            if attempt == 1:
                yield await _send_event("log", {"message": "<b>Etapa 1:</b> Agente Mestre criando conteúdo...", "type": "info"})
                current_content_data = await _run_master_generator_agent(product_name, product_info)
            else:
                yield await _send_event("log", {"message": "⚠️ Score baixo. Acionando <b>Agente Refinador</b>...", "type": "warning"})
                current_content_data = await _run_refiner_agent(product_name, product_info, current_content_data, audit_results)

            # --- INÍCIO DA CORREÇÃO ---
            # Validação crucial: Verifica se o agente retornou um erro ou nada.
            if not current_content_data or "error" in current_content_data:
                error_message = current_content_data.get("error", "Agente não retornou dados válidos.") if current_content_data else "Agente não retornou dados."
                yield await _send_event("log", {"message": f"❌ Falha crítica do Agente: {error_message}. Acionando plano de contingência.", "type": "error"})
                current_content_data = None # Força a queda para o modo de segurança
                break
            # --- FIM DA CORREÇÃO ---
            
            yield await _send_event("log", {"message": "<b>Etapa 2:</b> Agente Auditor inspecionando...", "type": "info"})
            audit_results = await _run_seo_auditor_agent(current_content_data)
            final_score = audit_results.get("seo_score", 0)

            for key, value in audit_results.get("score_breakdown", {}).items():
                if isinstance(value, dict):
                    feedback = value.get("feedback", "N/A")
                    status = "✅" if value.get("score", 0) == value.get("max_score", -1) else "⚠️"
                    yield await _send_event("log", {"message": f"{status} [{key.replace('_', ' ').title()}]: {feedback}", "type": "info"})

            yield await _send_event("log", {"message": f"<b>Score da Tentativa {attempt}: {final_score}/100</b>", "type": "info"})
            
            if final_score >= MIN_SCORE_TARGET:
                yield await _send_event("log", {"message": "<b>Qualidade Aprovada!</b>", "type": "success"})
                break

        if not current_content_data:
            yield await _send_event("log", {"message": "⚠️ <b>Aviso:</b> Geração principal falhou. Acionando <b>Agente Essencial (Fallback)</b>...", "type": "warning"})
            current_content_data = await _run_essentials_generator_agent(product_name, product_info)
            final_score = 40 # Score padrão para conteúdo essencial
            
        final_html = SeoOptimizerAgent._finalize_for_vtex(current_content_data.get("html_content", ""), product_name)
        
        final_data_for_review = {
            "final_score": final_score,
            "final_content": final_html,
            "seo_title": current_content_data.get("seo_title", product_name),
            "meta_description": current_content_data.get("meta_description", "Descrição não gerada.")
        }
        yield await _send_event("done", final_data_for_review)

    except Exception as e:
        traceback.print_exc()
        yield await _send_event("error", {"message": f"Erro crítico na pipeline para '{product_name}': {str(e)}", "type": "error"})
        # Garante que um evento 'done' seja enviado mesmo em caso de erro para não travar o worker
        yield await _send_event("done", {
            "final_score": 0,
            "final_content": "<p>Ocorreu um erro crítico durante o processamento deste item.</p>",
            "seo_title": product_name,
            "meta_description": "Erro no processamento."
        })