# app/use_cases.py (Versão 31.0 - Correção de Import Circular)
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

# --- Funções Utilitárias ---
def _extract_json_from_string(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        logging.error("Texto de entrada para extração de JSON está vazio.")
        return None
    json_match = re.search(r'```json\s*(\{[\s\S]*?\})\s*```', text, re.DOTALL)
    json_str = ""
    if json_match:
        json_str = json_match.group(1)
    else:
        start_index = text.find('{')
        end_index = text.rfind('}')
        if start_index != -1 and end_index != -1 and end_index > start_index:
            json_str = text[start_index:end_index + 1]
        else:
            logging.error("Nenhum bloco JSON válido (delimitado por '{' e '}') encontrado na resposta da IA.")
            return None
    try:
        json_str_cleaned = "".join(char for char in json_str if 31 < ord(char) or char in "\n\t\r")
        return json.loads(json_str_cleaned)
    except json.JSONDecodeError as e:
        logging.error(f"Falha ao decodificar JSON extraído: {e}")
        return None

def _execute_prompt_with_backoff(prompt: str, max_retries: int = 5, timeout: int = 60) -> Optional[str]:
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
        except (DeadlineExceeded, ResourceExhausted, ServiceUnavailable):
            logging.warning(f"Tentativa {attempt + 1} falhou. Aguardando {wait_time}s...")
            time.sleep(wait_time)
            wait_time = min(wait_time * 2, 60)
        except Exception as e:
            logging.error(f"Erro inesperado na chamada da API: {e}")
            return None
    logging.error("Limite máximo de tentativas atingido. A API continua indisponível.")
    return None

# --- Agentes de Geração e Refinamento ---
def _run_master_generator_agent(product_name: str, product_info: dict) -> Optional[Dict[str, Any]]:
    prompt = prompt_manager.render("medicamento_generator", product_name=product_name, product_info=product_info.get("bula_text", ""))
    response_raw = _execute_prompt_with_backoff(prompt, timeout=120)
    if response_raw:
        return _extract_json_from_string(response_raw)
    return None

def _run_refiner_agent(product_name: str, product_info: dict, previous_json: dict, feedback_data: dict) -> Dict[str, Any]:
    prompt = prompt_manager.render("refinador_qualidade", product_name=product_name, bula_text=product_info.get("bula_text", ""), previous_json=json.dumps(previous_json, ensure_ascii=False), feedback_usuario=feedback_data.get("feedback_usuario"), analise_automatica_anterior=json.dumps(feedback_data.get("analise_automatica_anterior"), ensure_ascii=False) if feedback_data.get("analise_automatica_anterior") else None)
    response_raw = _execute_prompt_with_backoff(prompt, timeout=120)
    if response_raw:
        data = _extract_json_from_string(response_raw)
        return data if data else previous_json
    return previous_json

def _run_seo_auditor_agent(full_page_json: dict) -> Dict[str, Any]:
    prompt = prompt_manager.render("auditor_seo_tecnico", full_page_json=json.dumps(full_page_json, ensure_ascii=False))
    response_raw = _execute_prompt_with_backoff(prompt, timeout=120)
    if response_raw:
        data = _extract_json_from_string(response_raw)
        return data if data else {"total_score": 0}
    return {"total_score": 0}

def _run_beauty_generator_agent(product_name: str, product_info: dict) -> Optional[Dict[str, Any]]:
    logging.info(f"BUSCA (Beauty): Pesquisando tópicos e FAQs para '{product_name}'...")
    try:
        faq_research = SeoOptimizerAgent.search_people_also_ask(product_name)
        keyword_research = SeoOptimizerAgent.search_related_topics(product_name)
        logging.info("BUSCA (Beauty): Pesquisas concluídas com sucesso.")
    except Exception as e:
        logging.error(f"Erro durante a busca SEO para '{product_name}': {e}")
        faq_research, keyword_research = "Falha na busca por perguntas.", "Falha na busca por palavras-chave."
        
    prompt = prompt_manager.render("beleza_e_cuidado_generator", product_name=product_name, seo_title=product_info.get("seo_title", ""), meta_description=product_info.get("meta_description", ""), product_info=product_info.get("context_text", "Nenhuma informação adicional fornecida."), faq_research_context=faq_research, keyword_research_context=keyword_research)
    response_raw = _execute_prompt_with_backoff(prompt, timeout=120)
    if response_raw:
        return _extract_json_from_string(response_raw)
    return None

def _run_beauty_auditor_agent(full_page_json: dict) -> Dict[str, Any]:
    prompt = prompt_manager.render("auditor_beleza_e_cuidado", full_page_json=json.dumps(full_page_json, ensure_ascii=False))
    response_raw = _execute_prompt_with_backoff(prompt, timeout=120)
    if response_raw:
        data = _extract_json_from_string(response_raw)
        return data if data else {"total_score": 0}
    return {"total_score": 0}

def _run_beauty_refiner_agent(product_name: str, product_info: dict, previous_json: dict, feedback_data: dict) -> Dict[str, Any]:
    prompt = prompt_manager.render("refinador_beleza_e_cuidado", product_name=product_name, product_info=product_info.get("context_text", "Nenhuma informação adicional fornecida."), previous_json=json.dumps(previous_json, ensure_ascii=False), feedback_usuario=feedback_data.get("feedback_usuario"), analise_automatica_anterior=json.dumps(feedback_data.get("analise_automatica_anterior"), ensure_ascii=False) if feedback_data.get("analise_automatica_anterior") else None)
    response_raw = _execute_prompt_with_backoff(prompt, timeout=120)
    if response_raw:
        data = _extract_json_from_string(response_raw)
        return data if data else previous_json
    return previous_json

# --- Orquestrador de Pipeline (Com Visualização Garantida) ---
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
        if product_type.lower() == 'medicine':
            generator_agent, auditor_agent, refiner_agent = _run_master_generator_agent, _run_seo_auditor_agent, _run_refiner_agent
        elif product_type.lower() == 'beauty':
            generator_agent, auditor_agent, refiner_agent = _run_beauty_generator_agent, _run_beauty_auditor_agent, _run_beauty_refiner_agent
        else:
            raise ValueError(f"Tipo de produto '{product_type}' desconhecido.")
        
        yield await _send_event("log", {"message": f"<b>Iniciando Processo ({product_type.title()}) para '{product_name}'...</b>", "type": "info"})

        current_content_data = None
        best_attempt_content = None
        highest_score = -1
        
        is_reprocessing_with_feedback = previous_content and feedback_text and feedback_text.strip()
        
        for attempt in range(1, MAX_ATTEMPTS + 1):
            yield await _send_event("log", {"message": f"<b>--- Ciclo de Qualidade {attempt}/{MAX_ATTEMPTS} ---</b>", "type": "info"})

            if is_reprocessing_with_feedback:
                yield await _send_event("log", {"message": f"<b>Etapa 1:</b> Agente Refinador processando com feedback...", "type": "info"})
                content_to_refine = previous_content if attempt == 1 else current_content_data
                feedback = {"feedback_usuario": feedback_text} if attempt == 1 else {"analise_automatica_anterior": audit_results, "feedback_usuario": feedback_text}
                current_content_data = await asyncio.to_thread(refiner_agent, product_name, product_info, content_to_refine, feedback)
            elif attempt == 1:
                yield await _send_event("log", {"message": f"<b>Etapa 1:</b> Agente Gerador criando conteúdo...", "type": "info"})
                current_content_data = await asyncio.to_thread(generator_agent, product_name, product_info)
            else:
                yield await _send_event("log", {"message": f"⚠️ Score baixo ({highest_score}/{MIN_SCORE_TARGET}). Acionando <b>Agente Refinador...</b>", "type": "warning"})
                current_content_data = await asyncio.to_thread(refiner_agent, product_name, product_info, current_content_data, {"analise_automatica_anterior": audit_results})

            if not current_content_data:
                yield await _send_event("log", {"message": "❌ Falha crítica do Agente na geração. Pulando para a próxima tentativa.", "type": "error"})
                continue

            yield await _send_event("log", {"message": f"<b>Etapa 2:</b> Auditor inspecionando...", "type": "info"})
            audit_results = await asyncio.to_thread(auditor_agent, current_content_data)
            final_score = audit_results.get("total_score", 0)

            if final_score > highest_score:
                highest_score = final_score
                best_attempt_content = current_content_data

            yield await _send_event("log", {"message": f"<b>Score da Tentativa {attempt}: {final_score}/100</b>", "type": "info"})

            if final_score >= MIN_SCORE_TARGET:
                yield await _send_event("log", {"message": "<b>Qualidade Aprovada!</b>", "type": "success"})
                break
        
        if final_score < MIN_SCORE_TARGET:
            yield await _send_event("log", {"message": f"⚠️ <b>Aviso:</b> Score final ({highest_score}) abaixo da meta ({MIN_SCORE_TARGET}). Retornando a melhor versão gerada.", "type": "warning"})
            current_content_data = best_attempt_content

        if not current_content_data:
            current_content_data = {"seo_title": product_name, "meta_description": "Descrição não gerada.", "html_content": "<p>Falha na geração de conteúdo.</p>"}
        
        final_html_vtex_safe = await asyncio.to_thread(SeoOptimizerAgent._finalize_for_vtex, current_content_data.get("html_content", ""), product_name)

        final_data_for_review = {
            "final_score": highest_score,
            "final_content": final_html_vtex_safe,
            "seo_title": str(current_content_data.get("seo_title", product_name)),
            "meta_description": str(current_content_data.get("meta_description", "Descrição não gerada.")),
            "raw_json_content": current_content_data
        }
        yield await _send_event("done", final_data_for_review)

    except Exception as e:
        traceback.print_exc()
        yield await _send_event("error", {"message": f"Erro crítico na pipeline: {str(e)}", "type": "error"})