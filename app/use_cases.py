# app/use_cases.py (Versão 22.1 - Parser de JSON Robusto e sem Pytrends)
import json
from typing import Dict, Any, AsyncGenerator, Optional
import asyncio
import traceback
import time
import re
import logging
from bs4 import BeautifulSoup
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable, DeadlineExceeded
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import pandas as pd

from .pharma_seo_optimizer import SeoOptimizerAgent
from .prompt_manager import PromptManager
from .gemini_client import GeminiClient

prompt_manager = PromptManager()
gemini_client = GeminiClient()

# --- INÍCIO DA SOLUÇÃO ATUALIZADA (JSON PARSER) ---
def _extract_json_from_string(text: str) -> Dict[str, Any]:
    """
    Extrai um objeto JSON de uma string, mesmo que esteja dentro de um bloco de código markdown
    ou tenha pequenos erros de formatação.
    """
    if not text:
        logging.error("Texto de entrada para extração de JSON está vazio.")
        return None

    # Tenta encontrar JSON dentro de um bloco de código markdown. É mais específico.
    json_match = re.search(r'```json\s*(\{[\s\S]*?\})\s*```', text, re.DOTALL)
    
    json_str = ""
    if json_match:
        json_str = json_match.group(1)
    else:
        # Fallback: se não encontrar o bloco markdown, procura o primeiro '{' e o último '}'
        start_index = text.find('{')
        end_index = text.rfind('}')
        if start_index != -1 and end_index != -1 and end_index > start_index:
            json_str = text[start_index:end_index + 1]
        else:
            logging.error("Nenhum bloco JSON válido (delimitado por '{' e '}') encontrado na resposta da IA.")
            return None

    try:
        # Remove caracteres de controlo que podem quebrar o parser
        json_str_cleaned = "".join(char for char in json_str if 31 < ord(char) or char in "\n\t\r")
        return json.loads(json_str_cleaned)
    except json.JSONDecodeError as e:
        logging.error(f"Falha ao decodificar JSON extraído: {e}")
        # Loga a vizinhança do erro para facilitar a depuração
        error_pos = e.pos
        start = max(0, error_pos - 70)
        end = min(len(json_str), error_pos + 70)
        logging.error(f"Contexto do erro no JSON: ...{json_str[start:end]}...")
        return None
# --- FIM DA SOLUÇÃO ATUALIZADA (JSON PARSER) ---

def _execute_prompt_with_backoff(prompt: str, max_retries: int = 5, timeout: int = 60) -> str | None:
    wait_time = 2
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
    for attempt in range(max_retries):
        try:
            response = gemini_client.model.generate_content(
                prompt,
                safety_settings=safety_settings,
                request_options={'timeout': timeout}
            )
            if response and hasattr(response, 'text') and response.text:
                return response.text
            else:
                 logging.warning(f"API retornou resposta vazia na tentativa {attempt + 1}/{max_retries}.")
                 raise ServiceUnavailable("Resposta vazia recebida.")
        except DeadlineExceeded:
            logging.error(f"A requisição excedeu o timeout de {timeout}s na tentativa {attempt + 1}/{max_retries}.")
            time.sleep(wait_time * 2)
            wait_time = min(wait_time * 2, 60)
        except (ResourceExhausted, ServiceUnavailable) as e:
            error_type = "Rate limit (429)" if isinstance(e, ResourceExhausted) else "Servidor sobrecarregado (503) ou resposta vazia"
            logging.warning(f"WARN: {error_type} (tentativa {attempt + 1}/{max_retries}). Aguardando {wait_time}s...")
            time.sleep(wait_time)
            wait_time = min(wait_time * 2, 60)
        except Exception as e:
            logging.error(f"Erro na chamada da API: {e}")
            traceback.print_exc()
            return None
    logging.error("Limite máximo de tentativas atingido. A API continua indisponível.")
    return None

# --- Funções dos Agentes ---

def _get_base_product_name(product_name_full: str) -> str:
    logging.info(f"Extraindo nome base de '{product_name_full}'...")
    try:
        base_name = product_name_full
        patterns = [
            r'\s+\d+(\.\d+)?(mg|g|ml|l)(\s*\/\s*\d+(\.\d+)?(mg|g|ml|l))?', r'\s+-\s+Caixa.*',
            r'\s+com\s+\d+\s+.*', r'\s+\d+\s+Comprimidos.*', r'\s+\d+\s+Seringas.*',
            r'\s+Gotas.*', r'\s+Xarope.*', r'\s+\(Refil\).*'
        ]
        for pattern in patterns:
            base_name = re.sub(pattern, '', base_name, flags=re.IGNORECASE)
        base_name = base_name.strip()
        if base_name and len(base_name) > 3 and base_name.lower() != product_name_full.lower():
            logging.info(f"Nome base extraído com Regex: '{base_name}'")
            return base_name
    except Exception as e:
        logging.warning(f"Regex para extração de nome base falhou: {e}. Tentando com IA.")
    try:
        simplified_prompt = f"Extraia o nome principal do produto de '{product_name_full}'. Responda APENAS com o nome."
        response = _execute_prompt_with_backoff(simplified_prompt, max_retries=2, timeout=30)
        if response:
            base_name = response.strip().replace("**", "")
            logging.info(f"Nome base extraído com IA: '{base_name}'")
            return base_name
    except Exception as e:
        logging.error(f"Erro ao extrair nome base com IA para '{product_name_full}': {e}")
    logging.warning(f"Não foi possível extrair um nome base. Usando o nome completo como fallback.")
    return product_name_full

def _run_master_generator_agent(product_name: str, product_info: dict, faq_research_context: str | None, keyword_research_context: str | None) -> Dict[str, Any] | None:
    logging.info(f"PIPELINE: Executing Master Generator for '{product_name}'...")
    prompt = prompt_manager.render("medicamento_generator", product_name=product_name, product_info=product_info.get("bula_text", ""), faq_research_context=faq_research_context, keyword_research_context=keyword_research_context)
    response_raw = _execute_prompt_with_backoff(prompt, timeout=120)
    if response_raw is None:
        logging.error(f"Master Generator não recebeu resposta da API para '{product_name}'.")
        return None
    data = _extract_json_from_string(response_raw)
    if data and data.get("html_content") and len(data["html_content"]) > 50:
        return data
    logging.error(f"Master Generator falhou na extração do JSON ou gerou conteúdo muito curto para '{product_name}'.")
    return None

def _run_refiner_agent(product_name: str, product_info: dict, previous_json: dict, feedback_data: dict) -> Dict[str, Any]:
    logging.info(f"PIPELINE: Executing Refiner Agent for '{product_name}'...")
    prompt = prompt_manager.render(
        "refinador_qualidade",
        product_name=product_name,
        bula_text=product_info.get("bula_text", ""),
        previous_json=json.dumps(previous_json, ensure_ascii=False),
        feedback_usuario=feedback_data.get("feedback_usuario"),
        instrucao_prioritaria_usuario=feedback_data.get("instrucao_prioritaria_usuario"),
        analise_automatica_anterior=json.dumps(feedback_data.get("analise_automatica_anterior"), ensure_ascii=False) if feedback_data.get("analise_automatica_anterior") else None
    )
    response_raw = _execute_prompt_with_backoff(prompt, timeout=120)
    if response_raw is None:
        logging.error(f"Refiner Agent não recebeu resposta da API para '{product_name}'. Retornando JSON anterior.")
        return previous_json
    data = _extract_json_from_string(response_raw)
    if data:
        return data
    logging.error(f"Refiner Agent falhou na extração do JSON para '{product_name}'. Retornando JSON anterior.")
    return previous_json

def _run_essentials_generator_agent(product_name: str, product_info: dict) -> Dict[str, Any]:
    logging.warning(f"PIPELINE: All attempts failed. Executing Essentials Fallback Agent for '{product_name}'...")
    prompt = prompt_manager.render("essentials_generator", product_name=product_name, product_info=product_info.get("bula_text", ""))
    html_content = _execute_prompt_with_backoff(prompt)
    if html_content is None or len(html_content) < 20:
        html_content = "<p>Falha crítica na geração de conteúdo.</p>"
    seo_title = f"{product_name} - Para que serve e como usar"
    meta_description = f"Encontre aqui informações essenciais sobre {product_name}: para que serve, como funciona, como usar e mais."
    return {"seo_title": seo_title, "meta_description": meta_description, "html_content": html_content}

def _run_seo_auditor_agent(full_page_json: dict) -> Dict[str, Any]:
    logging.info(f"PIPELINE: Executing Master Auditor...")
    prompt = prompt_manager.render("auditor_seo_tecnico", full_page_json=json.dumps(full_page_json, ensure_ascii=False))
    response_raw = _execute_prompt_with_backoff(prompt, timeout=120)
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
    MAX_ATTEMPTS = 3

    async def _send_event(event_type: str, data: dict) -> str:
        await asyncio.sleep(0.05)
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    try:
        bula_text = product_info.get("bula_text", "")
        if not bula_text: raise ValueError("Texto da bula não fornecido.")

        yield await _send_event("log", {"message": f"<b>Iniciando Processo para '{product_name}'...</b>", "type": "info"})
        
        base_product_name = await asyncio.to_thread(_get_base_product_name, product_name)
        
        current_content_data = None
        final_score = 0
        audit_results = {}
        is_reprocessing_with_feedback = previous_content and feedback_text and feedback_text.strip()
        
        for attempt in range(1, MAX_ATTEMPTS + 1):
            yield await _send_event("log", {"message": f"<b>--- Ciclo de Qualidade {attempt}/{MAX_ATTEMPTS} ---</b>", "type": "info"})

            if is_reprocessing_with_feedback:
                content_to_refine = previous_content if attempt == 1 else current_content_data
                feedback_for_refiner = {"feedback_usuario": feedback_text} if attempt == 1 else {"analise_automatica_anterior": audit_results, "instrucao_prioritaria_usuario": feedback_text}
                current_content_data = await asyncio.to_thread(_run_refiner_agent, product_name, product_info, content_to_refine, feedback_for_refiner)
            elif attempt == 1:
                yield await _send_event("log", {"message": "<b>Etapa 1:</b> Agente Mestre criando conteúdo...", "type": "info"})
                current_content_data = await asyncio.to_thread(_run_master_generator_agent, product_name, product_info, None, None)
            else:
                yield await _send_event("log", {"message": f"⚠️ Score baixo (Tentativa {attempt-1}). Acionando <b>Agente Refinador...</b>", "type": "warning"})
                current_content_data = await asyncio.to_thread(_run_refiner_agent, product_name, product_info, current_content_data, {"analise_automatica_anterior": audit_results})

            if not current_content_data:
                yield await _send_event("log", {"message": "❌ Falha crítica do Agente. Acionando Fallback.", "type": "error"})
                break

            yield await _send_event("log", {"message": "<b>Etapa 2:</b> Auditor inspecionando...", "type": "info"})
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

        if not current_content_data:
            yield await _send_event("log", {"message": "⚠️ <b>Aviso:</b> Acionando Agente Essencial (Fallback)...", "type": "warning"})
            current_content_data = await asyncio.to_thread(_run_essentials_generator_agent, product_name, product_info)
            final_score = 0 

        yield await _send_event("log", {"message": f"<b>Ciclos finalizados para '{product_name}'. Score máximo: {final_score}/100.</b>", "type": "info"})

        final_html_vtex_safe = await asyncio.to_thread(SeoOptimizerAgent._finalize_for_vtex, current_content_data.get("html_content", "<p>Conteúdo não gerado.</p>"), product_name)

        final_data_for_review = {
            "final_score": final_score, "final_content": final_html_vtex_safe,
            "seo_title": str(current_content_data.get("seo_title", product_name)),
            "meta_description": str(current_content_data.get("meta_description", "Descrição não gerada.")),
            "raw_json_content": current_content_data
        }
        yield await _send_event("done", final_data_for_review)

    except Exception as e:
        traceback.print_exc()
        yield await _send_event("error", {"message": f"Erro crítico na pipeline para '{product_name}': {str(e)}", "type": "error"})
        return