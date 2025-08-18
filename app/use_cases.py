# app/use_cases.py (Versão com Loop de Qualidade)

import json
from typing import Dict, Any, AsyncGenerator
from . import seo_analyzer

# --- Funções Singleton (sem alterações) ---
_prompt_manager = None
_gemini_client = None
_strategy_manager = None

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

def _get_strategy_manager():
    global _strategy_manager
    if _strategy_manager is None:
        from .strategy_manager import StrategyManager
        _strategy_manager = StrategyManager()
    return _strategy_manager

# --- Funções dos Agentes ---

def _run_generator_agent(product_type: str, product_name: str, product_info: dict) -> Dict[str, Any]:
    """AGENTE 1: Gera o conteúdo inicial (v1.0)."""
    print(f"PIPELINE: Executing Generator Agent for '{product_name}'...")
    generator_prompt_name = {
        "medicine": "medicamento_generator",
        "vitamin": "vitamina_suplemento_generator",
        "cosmetic": "dermocosmetico_generator"
    }.get(product_type, "medicamento_generator")
    
    prompt = _get_prompt_manager().render(generator_prompt_name, product_name=product_name, **product_info)
    response_raw = _get_gemini_client().execute_prompt(prompt)

    try:
        json_start = response_raw.find('{')
        json_end = response_raw.rfind('}') + 1
        if json_start == -1: raise ValueError("JSON not found in generator response.")
        json_str = response_raw[json_start:json_end]
        return json.loads(json_str)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: Generator Agent failed: {e}")
        return {"html_content": f"<h1>{product_name}</h1><p>Erro na geração inicial.</p>", "seo_title": product_name, "meta_description": "", "faq_section": ""}

def _run_refiner_agent(product_name: str, current_html: str, analysis: dict, product_info: dict) -> str:
    """AGENTE DE REFINAMENTO: Corrige o conteúdo com base no feedback do QA."""
    print(f"PIPELINE: Executing Refiner Agent for '{product_name}'...")
    
    prompt = _get_prompt_manager().render(
        "refinador_qualidade", # Usando o novo prompt
        product_name=product_name,
        bula_text=product_info.get("bula_text", ""),
        current_version_html=current_html,
        current_score=analysis.get("total_score", 0),
        qa_feedback=json.dumps(analysis.get("breakdown"), indent=2, ensure_ascii=False)
    )
    return _get_gemini_client().execute_prompt(prompt)


# --- O ORQUESTRADOR PRINCIPAL COM O LOOP ---

async def run_seo_pipeline_stream(product_type: str, product_name: str, product_info: Dict[str, Any]) -> AsyncGenerator[str, None]:
    """
    Orquestra a linha de produção com um loop de garantia de qualidade para atingir a meta de score.
    """
    from .pharma_seo_optimizer import SeoOptimizerAgent

    MIN_SCORE_TARGET = 85
    MAX_ATTEMPTS = 20

    async def _send_event(event_type: str, data: dict) -> str:
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    try:
        bula_text = product_info.get("bula_text", "")
        if not bula_text:
            raise ValueError("Texto da bula não fornecido.")

        # ETAPA 1: GERAÇÃO INICIAL (v1.0)
        yield await _send_event("log", {"message": "<b>Etapa 1/2:</b> Agente Gerador criando conteúdo v1.0...", "type": "info"})
        content_v1_data = _run_generator_agent(product_type, product_name, product_info)
        
        current_html = content_v1_data.get("html_content", "") + "\n" + content_v1_data.get("faq_section", "")
        
        # ETAPA 2: LOOP DE QUALIDADE E REFINAMENTO
        yield await _send_event("log", {"message": "<b>Etapa 2/2:</b> Iniciando ciclo de qualidade e refinamento...", "type": "info"})

        current_score = 0
        analysis = {}
        
        for attempt in range(1, MAX_ATTEMPTS + 1):
            yield await _send_event("log", {"message": f"<b>Tentativa {attempt}/{MAX_ATTEMPTS}:</b> Agente de QA analisando conteúdo...", "type": "info"})
            analysis = seo_analyzer.analyze_seo_performance(current_html, product_name, product_info)
            current_score = analysis.get("total_score", 0)
            
            yield await _send_event("update", {"score": current_score, "attempt": attempt, "max_attempts": MAX_ATTEMPTS})
            yield await _send_event("log", {"message": f"Análise completa. Score atual: {current_score}", "type": "info"})

            if current_score >= MIN_SCORE_TARGET:
                yield await _send_event("log", {"message": f"Meta de score ({MIN_SCORE_TARGET}) atingida! Concluindo...", "type": "success"})
                break # Sai do loop se a meta for atingida

            if attempt < MAX_ATTEMPTS:
                yield await _send_event("log", {"message": f"Score abaixo da meta. Acionando Agente de Refinamento...", "type": "warning"})
                
                refined_html = _run_refiner_agent(product_name, current_html, analysis, product_info)
                current_html = refined_html # Atualiza o HTML para a próxima iteração
        
        # FINALIZAÇÃO
        final_score = current_score
        final_html_clean = SeoOptimizerAgent._clean_and_correct_html(current_html)
        
        final_data = {
            "final_score": final_score,
            "final_content": final_html_clean,
            "seo_title": content_v1_data.get("seo_title", product_name),
            "meta_description": content_v1_data.get("meta_description", "Descrição otimizada.")
        }
        yield await _send_event("done", final_data)

    except Exception as e:
        yield await _send_event("error", {"message": f"Erro crítico na pipeline: {str(e)}", "type": "error"})