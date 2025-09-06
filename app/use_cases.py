# app/use_cases.py (Versão 18.1 - Feedback Explícito)
import json
from typing import Dict, Any, AsyncGenerator, Optional
import asyncio
import traceback
import time
import re
from bs4 import BeautifulSoup
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from .pharma_seo_optimizer import SeoOptimizerAgent

# --- Funções Singleton ---
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
        except json.JSONDecodeError as e:
            print(f"ERROR: Falha ao decodificar JSON extraído: {e}")
            print(f"JSON com erro: {json_str[:500]}...")
            return None
    print("ERROR: Nenhum bloco JSON válido encontrado na resposta da IA.")
    return None

def _execute_prompt_with_backoff(prompt: str, max_retries: int = 5) -> str | None:
    wait_time = 2
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
    for attempt in range(max_retries):
        try:
            response = _get_gemini_client().model.generate_content(
                prompt,
                safety_settings=safety_settings
            )
            if response and hasattr(response, 'text') and response.text:
                return response.text
            else:
                 print(f"WARN: API retornou resposta vazia na tentativa {attempt + 1}/{max_retries}.")
                 raise ServiceUnavailable("Resposta vazia recebida.")
        except (ResourceExhausted, ServiceUnavailable) as e:
            error_type = "Rate limit (429)" if isinstance(e, ResourceExhausted) else "Servidor sobrecarregado (503) ou resposta vazia"
            print(f"WARN: {error_type} (tentativa {attempt + 1}/{max_retries}). Aguardando {wait_time}s...")
            time.sleep(wait_time)
            wait_time = min(wait_time * 2, 60)
        except Exception as e:
            print(f"ERROR: Erro irrecuperável na chamada da API, não haverá nova tentativa: {e}")
            traceback.print_exc()
            return None
    print("ERROR: Limite máximo de tentativas atingido. A API continua indisponível.")
    return None

# --- Funções dos Agentes ---
def _run_master_generator_agent(product_name: str, product_info: dict) -> Dict[str, Any] | None:
    print(f"PIPELINE: Executing Master Generator for '{product_name}'...")
    prompt = _get_prompt_manager().render("medicamento_generator", product_name=product_name, product_info=product_info.get("bula_text", ""))
    response_raw = _execute_prompt_with_backoff(prompt)
    if response_raw is None:
        print(f"ERROR: Master Generator não recebeu resposta da API.")
        return None
    data = _extract_json_from_string(response_raw)
    if data and data.get("html_content") and len(data["html_content"]) > 50:
        return data
    print(f"ERROR: Master Generator falhou na extração do JSON ou gerou conteúdo muito curto.")
    return None

def _run_refiner_agent(product_name: str, product_info: dict, previous_json: dict, feedback_data: dict) -> Dict[str, Any]:
    print(f"PIPELINE: Executing Refiner Agent for '{product_name}'...")
    # ATUALIZAÇÃO: Passa as chaves do dicionário de feedback como argumentos nomeados explícitos.
    prompt = _get_prompt_manager().render(
        "refinador_qualidade",
        product_name=product_name,
        bula_text=product_info.get("bula_text", ""),
        previous_json=json.dumps(previous_json, ensure_ascii=False),
        feedback_usuario=feedback_data.get("feedback_usuario"),
        instrucao_prioritaria_usuario=feedback_data.get("instrucao_prioritaria_usuario"),
        analise_automatica_anterior=json.dumps(feedback_data.get("analise_automatica_anterior"), ensure_ascii=False) if feedback_data.get("analise_automatica_anterior") else None
    )
    response_raw = _execute_prompt_with_backoff(prompt)
    if response_raw is None:
        print(f"ERROR: Refiner Agent não recebeu resposta da API. Retornando JSON anterior.")
        return previous_json
    data = _extract_json_from_string(response_raw)
    if data:
        return data
    print(f"ERROR: Refiner Agent falhou na extração do JSON. Retornando JSON anterior.")
    return previous_json

def _run_essentials_generator_agent(product_name: str, product_info: dict) -> Dict[str, Any]:
    print(f"PIPELINE: All attempts failed. Executing Essentials Fallback Agent for '{product_name}'...")
    prompt = _get_prompt_manager().render("essentials_generator", product_name=product_name, product_info=product_info.get("bula_text", ""))
    html_content = _execute_prompt_with_backoff(prompt)
    if html_content is None or len(html_content) < 20:
        html_content = "<p>Falha crítica na geração de conteúdo.</p>"
    seo_title = f"{product_name} - Para que serve e como usar"
    meta_description = f"Encontre aqui informações essenciais sobre {product_name}: para que serve, como funciona, como usar e mais. Consulte a bula e um profissional de saúde."
    return {"seo_title": seo_title, "meta_description": meta_description, "html_content": html_content}

def _run_seo_auditor_agent(full_page_json: dict) -> Dict[str, Any]:
    print(f"PIPELINE: Executing Master Auditor...")
    prompt = _get_prompt_manager().render("auditor_seo_tecnico", full_page_json=json.dumps(full_page_json, ensure_ascii=False))
    response_raw = _execute_prompt_with_backoff(prompt)
    if response_raw is None:
        return {"seo_score": 0, "score_breakdown": {"error": {"feedback": "Falha crítica na auditoria - sem resposta da API."}}}
    data = _extract_json_from_string(response_raw)
    if data:
        return data
    return {"seo_score": 0, "score_breakdown": {"error": {"feedback": "Falha crítica na auditoria - JSON inválido."}}}

# --- Orquestrador Principal da Pipeline ---
async def run_seo_pipeline_stream(
    product_type: str,
    product_name: str,
    product_info: Dict[str, Any],
    previous_content: Optional[Dict[str, Any]] = None,
    feedback_text: Optional[str] = None
) -> AsyncGenerator[str, None]:
    MIN_SCORE_TARGET = 95
    MAX_ATTEMPTS = 2

    async def _send_event(event_type: str, data: dict) -> str:
        await asyncio.sleep(0.05)
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    try:
        bula_text = product_info.get("bula_text", "")
        if not bula_text: raise ValueError("Texto da bula não fornecido.")

        yield await _send_event("log", {"message": f"<b>Iniciando Processo para '{product_name}'...</b>", "type": "info"})

        current_content_data = None
        final_score = 0
        audit_results = {}
        is_reprocessing_with_feedback = previous_content and feedback_text and feedback_text.strip()

        for attempt in range(1, MAX_ATTEMPTS + 1):
            yield await _send_event("log", {"message": f"<b>--- Ciclo de Qualidade {attempt}/{MAX_ATTEMPTS} ---</b>", "type": "info"})

            if is_reprocessing_with_feedback:
                content_to_refine = previous_content if attempt == 1 else current_content_data
                if attempt > 1:
                    yield await _send_event("log", {"message": "⚠️ Score baixo. Refinando novamente com feedback original + auditoria...", "type": "warning"})
                    feedback_for_refiner = {
                        "instrucao_prioritaria_usuario": feedback_text,
                        "analise_automatica_anterior": audit_results
                    }
                else:
                    yield await _send_event("log", {"message": "♻️ <b>Reprocessando:</b> Usando seu feedback para acionar o Agente Refinador...", "type": "warning"})
                    feedback_for_refiner = {"feedback_usuario": feedback_text}
                current_content_data = await asyncio.to_thread(_run_refiner_agent, product_name, product_info, content_to_refine, feedback_for_refiner)
            elif attempt == 1:
                yield await _send_event("log", {"message": "<b>Etapa 1:</b> Agente Mestre (Master Generator) criando conteúdo...", "type": "info"})
                current_content_data = await asyncio.to_thread(_run_master_generator_agent, product_name, product_info)
            else:
                yield await _send_event("log", {"message": "⚠️ Score baixo. Acionando <b>Agente Refinador (Auto-Correção)</b>...", "type": "warning"})
                current_content_data = await asyncio.to_thread(_run_refiner_agent, product_name, product_info, current_content_data, audit_results)

            if current_content_data is None:
                yield await _send_event("log", {"message": "❌ Falha crítica do Agente. Acionando plano de contingência.", "type": "error"})
                break

            yield await _send_event("log", {"message": "<b>Etapa 2:</b> Agente de Qualidade (Auditor) inspecionando...", "type": "info"})
            audit_results = await asyncio.to_thread(_run_seo_auditor_agent, current_content_data)
            final_score = audit_results.get("seo_score", 0)

            score_breakdown = audit_results.get("score_breakdown", {})
            for key, value in score_breakdown.items():
                if isinstance(value, dict):
                    feedback = value.get("feedback", "N/A")
                    status_emoji = "✅" if value.get("score", 0) == value.get("max_score", -1) else "⚠️"
                    yield await _send_event("log", {"message": f"{status_emoji} [{key.replace('_', ' ').title()}]: {feedback}", "type": "success" if status_emoji == "✅" else "warning"})

            yield await _send_event("log", {"message": f"<b>Score da Tentativa {attempt}: {final_score}/100</b>", "type": "info"})

            if final_score >= MIN_SCORE_TARGET and not is_reprocessing_with_feedback:
                yield await _send_event("log", {"message": "<b>Qualidade Aprovada!</b>", "type": "success"})
                break

        if current_content_data is None:
            yield await _send_event("log", {"message": "⚠️ <b>Aviso:</b> Geração principal falhou. Acionando Agente Essencial (Fallback)...", "type": "warning"})
            current_content_data = await asyncio.to_thread(_run_essentials_generator_agent, product_name, product_info)
            audit_results = await asyncio.to_thread(_run_seo_auditor_agent, current_content_data)
            final_score = audit_results.get("seo_score", 0)
            yield await _send_event("log", {"message": f"<b>Score do Conteúdo Essencial: {final_score}/100</b>", "type": "info"})

        yield await _send_event("log", {"message": f"<b>Ciclos finalizados para '{product_name}'. Score máximo: {final_score}/100.</b>", "type": "info"})

        final_html_vtex_safe = SeoOptimizerAgent._finalize_for_vtex(current_content_data.get("html_content", "<p>Conteúdo não gerado.</p>"), product_name)

        final_data_for_review = {
            "final_score": final_score,
            "final_content": final_html_vtex_safe,
            "seo_title": str(current_content_data.get("seo_title", product_name)),
            "meta_description": str(current_content_data.get("meta_description", "Descrição não gerada.")),
            "raw_json_content": current_content_data
        }
        yield await _send_event("done", final_data_for_review)

    except Exception as e:
        traceback.print_exc()
        yield await _send_event("error", {"message": f"Erro crítico na pipeline para '{product_name}': {str(e)}", "type": "error"})