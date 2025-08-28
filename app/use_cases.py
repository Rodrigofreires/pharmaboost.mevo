# app/use_cases.py (Versão com correção de TypeError)

import json
from typing import Dict, Any, AsyncGenerator
from datetime import datetime
import asyncio
import traceback

# --- Funções Singleton (sem alterações) ---
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

def _run_generator_agent_v4(product_name: str, product_info: dict) -> Dict[str, Any]:
    """Gera o conteúdo inicial a partir da bula."""
    print(f"PIPELINE: Executing Generator Agent v4 for '{product_name}'...")
    prompt = _get_prompt_manager().render("medicamento_generator", product_name=product_name, current_date=datetime.now().strftime("%B/%Y"), **product_info)
    response_raw = _get_gemini_client().execute_prompt(prompt)
    try:
        json_start = response_raw.find('{')
        json_end = response_raw.rfind('}') + 1
        if json_start == -1: raise ValueError("JSON object not found.")
        return json.loads(response_raw[json_start:json_end])
    except (ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: Generator Agent v4 failed: {e}")
        return {
            "seo_title": product_name, 
            "meta_description": "Erro na geração.", 
            "html_content": f"<h1>{product_name}</h1><p>Erro na geração.</p>", 
            "faq_section": "", 
            "schema_markup": {}
        }

def _run_seo_auditor_agent(product_name: str, current_html_data: dict) -> Dict[str, Any]:
    """
    Executa o agente de auditoria de SEO, tratando os tipos de dados de forma robusta.
    """
    print(f"PIPELINE: Executing SEO Auditor Agent for '{product_name}'...")
    
    # --- CORREÇÃO: Garante que todos os campos de conteúdo sejam strings antes de concatenar ---
    html_content = str(current_html_data.get("html_content", ""))
    faq_section = str(current_html_data.get("faq_section", ""))
    schema_content = current_html_data.get("schema_markup", "")
    
    schema_script = ""
    if isinstance(schema_content, dict) and schema_content:
        schema_script = f'<script type="application/ld+json">{json.dumps(schema_content, ensure_ascii=False)}</script>'
    elif isinstance(schema_content, str):
        if schema_content.strip() and not schema_content.strip().startswith('<script'):
            schema_script = f'<script type="application/ld+json">{schema_content}</script>'
        else:
            schema_script = schema_content
    
    full_html_content = html_content + "\n" + faq_section + "\n" + schema_script
    
    prompt = _get_prompt_manager().render(
        "auditor_seo_tecnico", 
        product_name=product_name, 
        seo_title=str(current_html_data.get("seo_title", "")), 
        meta_description=str(current_html_data.get("meta_description", "")), 
        full_html_content=full_html_content
    )
    
    response_raw = _get_gemini_client().execute_prompt(prompt)
    try:
        json_start = response_raw.find('{')
        json_end = response_raw.rfind('}') + 1
        if json_start == -1: raise ValueError("JSON object not found in auditor response.")
        return json.loads(response_raw[json_start:json_end])
    except (ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: SEO Auditor Agent failed to return valid JSON: {e}")
        return {"seo_score": 0, "score_breakdown": {"error": {"score":0, "max_score": 100, "feedback": "Falha na análise."}}}

def _run_refiner_agent(product_name: str, product_info: dict, current_data: dict, audit_results: dict) -> Dict[str, Any]:
    """
    Executa o agente de refinamento, que agora corrige a página inteira e retorna um JSON completo.
    """
    print(f"PIPELINE: Low score detected. Executing Refiner Agent for '{product_name}'...")
    
    # --- CORREÇÃO: Garante que os campos de conteúdo sejam strings ---
    html_content = str(current_data.get("html_content", ""))
    faq_section = str(current_data.get("faq_section", ""))
    current_html_content_for_refiner = html_content + "\n" + faq_section
    
    feedback_for_refiner = json.dumps(audit_results.get("score_breakdown", {}), indent=2)

    prompt = _get_prompt_manager().render(
        "refinador_qualidade",
        product_name=product_name,
        bula_text=product_info.get("bula_text", ""),
        current_seo_title=str(current_data.get("seo_title", "")),
        current_meta_description=str(current_data.get("meta_description", "")),
        current_html_content=current_html_content_for_refiner,
        current_score=audit_results.get("seo_score", 0),
        qa_feedback=feedback_for_refiner
    )
    
    response_raw = _get_gemini_client().execute_prompt(prompt)
    try:
        json_start = response_raw.find('{')
        json_end = response_raw.rfind('}') + 1
        if json_start == -1: raise ValueError("JSON object not found in refiner response.")
        refined_data = json.loads(response_raw[json_start:json_end])
        return refined_data
    except (ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: Refiner Agent failed to return valid JSON: {e}")
        return current_data

# --- O ORQUESTRADOR PRINCIPAL ---

async def run_seo_pipeline_stream(product_type: str, product_name: str, product_info: Dict[str, Any]) -> AsyncGenerator[str, None]:
    from .pharma_seo_optimizer import SeoOptimizerAgent
    MIN_SCORE_TARGET = 85
    MAX_ATTEMPTS = 3

    async def _send_event(event_type: str, data: dict) -> str:
        await asyncio.sleep(0.05)
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    try:
        bula_text = product_info.get("bula_text", "")
        if not bula_text: raise ValueError("Texto da bula não fornecido.")

        yield await _send_event("log", {"message": "<b>Etapa 1:</b> Gerador v4 criando conteúdo inicial...", "type": "info"})
        current_content_data = _run_generator_agent_v4(product_name, product_info)
        final_score = 0

        for attempt in range(1, MAX_ATTEMPTS + 1):
            yield await _send_event("log", {"message": f"<b>--- Tentativa de Otimização {attempt}/{MAX_ATTEMPTS} ---</b>", "type": "info"})
            
            audit_results = _run_seo_auditor_agent(product_name, current_content_data)
            final_score = audit_results.get("seo_score", 0)
            score_breakdown = audit_results.get("score_breakdown", {})

            yield await _send_event("log", {"message": "<b>Auditoria em andamento...</b>", "type": "info"})
            
            for key, value in score_breakdown.items():
                score = value.get("score", 0); max_score = value.get("max_score", 0)
                feedback = value.get("feedback", "N/A"); status_emoji = "✅" if score == max_score else "⚠️"
                yield await _send_event("log", {"message": f"{status_emoji} [{key.replace('_', ' ').title()}]: {score}/{max_score} pts. <i>({feedback})</i>", "type": "success" if score == max_score else "warning"})
            
            yield await _send_event("log", {"message": f"<b>Score Final da Tentativa {attempt}: {final_score}/100</b>", "type": "info"})

            if final_score >= MIN_SCORE_TARGET:
                yield await _send_event("log", {"message": "<b>Sucesso!</b> Meta de score atingida.", "type": "success"})
                break

            if attempt < MAX_ATTEMPTS:
                yield await _send_event("log", {"message": "Score abaixo da meta. Acionando <b>Agente de Refinamento...</b>", "type": "warning"})
                current_content_data = _run_refiner_agent(product_name, product_info, current_content_data, audit_results)
            else:
                yield await _send_event("log", {"message": f"<b>Tentativas finalizadas.</b> Score máximo atingido: {final_score}/100.", "type": "warning"})

        # Lógica final de formatação do schema
        schema_data = current_content_data.get("schema_markup", "")
        schema_script = ""
        if isinstance(schema_data, (dict, list)) and schema_data:
             schema_script = f'<script type="application/ld+json">\n{json.dumps(schema_data, indent=2, ensure_ascii=False)}\n</script>'
        elif isinstance(schema_data, str) and schema_data.strip().startswith(('{', '[')):
             schema_script = f'<script type="application/ld+json">\n{schema_data}\n</script>'

        final_html_content = (
            str(current_content_data.get("html_content", "")) + "\n" +
            str(current_content_data.get("faq_section", "")) + "\n" +
            schema_script
        )
        final_html_clean = SeoOptimizerAgent._clean_and_correct_html(final_html_content)
        
        final_data_for_review = {
            "final_score": final_score, 
            "final_content": final_html_clean, 
            "seo_title": str(current_content_data.get("seo_title", product_name)), 
            "meta_description": str(current_content_data.get("meta_description", "Descrição otimizada."))
        }
        yield await _send_event("done", final_data_for_review)

    except Exception as e:
        traceback.print_exc()
        yield await _send_event("error", {"message": f"Erro crítico na pipeline: {str(e)}", "type": "error"})
