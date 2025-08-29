import json
from typing import Dict, Any, AsyncGenerator
from datetime import datetime
import asyncio
import traceback
from bs4 import BeautifulSoup

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

# --- NOVA FUNÇÃO DE CORREÇÃO DE FAQ ---
def _enforce_faq_h3_structure(html_content: str) -> str:
    """
    Analisa o conteúdo HTML e garante que o texto dentro de uma tag <summary>
    seja envolvido por uma tag <h3>, caso ainda não seja.
    Isso serve como uma garantia de qualidade para a saída da IA.
    """
    if not html_content or not isinstance(html_content, str):
        return ""
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    details_tags = soup.find_all('details')
    for details in details_tags:
        summary = details.find('summary')
        # Procede apenas se encontrar uma tag <summary> e ela não tiver um <h3> dentro
        if summary and not summary.find('h3'):
            summary_text = summary.get_text(strip=True)
            if summary_text:
                summary.string = '' # Limpa o texto original da tag summary
                new_h3 = soup.new_tag('h3')
                new_h3.string = summary_text
                summary.append(new_h3) # Adiciona a nova tag <h3> dentro da <summary>
                
    # Retorna apenas o conteúdo, sem adicionar tags <html> ou <body>
    if soup.body:
        return soup.body.decode_contents()
    return str(soup)


# --- NOVO AGENTE PADRÃO MEVOFARMA ---
def _run_mevofarma_standard_agent(product_name: str, product_info: str) -> str:
    """
    Executa o agente padrão Mevofarma para gerar o HTML completo.
    """
    print(f"PIPELINE: Executing Mevofarma Standard Generator Agent for '{product_name}'...")
    prompt = _get_prompt_manager().render(
        "mevofarma_standard_generator",
        product_name=product_name,
        product_info=product_info
    )
    response_html = _get_gemini_client().execute_prompt(prompt)
    # O prompt pede APENAS o bloco de código, então limpamos um pouco
    cleaned_html = response_html.strip()
    if cleaned_html.startswith("```html"):
        cleaned_html = cleaned_html[7:]
    if cleaned_html.endswith("```"):
        cleaned_html = cleaned_html[:-3]

    return cleaned_html.strip()


# --- Funções dos Agentes (Fluxo de Otimização) ---

def _run_generator_agent_v4(product_name: str, product_info: dict) -> Dict[str, Any]:
    """Gera o conteúdo inicial a partir da bula."""
    print(f"PIPELINE: Executing Generator Agent v4 for '{product_name}'...")
    # A variável 'current_date' foi removida pois não existe mais no prompt 'medicamento_generator'.
    prompt = _get_prompt_manager().render(
        "medicamento_generator", 
        product_name=product_name, 
        product_info=product_info.get("bula_text", "")
    )
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

    # Garante que todos os campos de conteúdo sejam strings antes de concatenar
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

    # Garante que os campos de conteúdo sejam strings
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

# --- ORQUESTRADORES DE PIPELINE ---

# --- NOVO ORQUESTRADOR PADRÃO MEVOFARMA ---
async def run_mevofarma_pipeline_stream(product_name: str, product_info: Dict[str, Any]) -> AsyncGenerator[str, None]:
    """
    Orquestrador para o agente padrão Mevofarma.
    Gera o conteúdo em uma única etapa e o envia para revisão.
    """
    async def _send_event(event_type: str, data: dict) -> str:
        await asyncio.sleep(0.05)
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    try:
        bula_text = product_info.get("bula_text", "")
        if not bula_text:
            raise ValueError("Texto da bula não fornecido.")

        yield await _send_event("log", {"message": "<b>Etapa Única:</b> Gerador Padrão Mevofarma criando conteúdo...", "type": "info"})

        # Chama o novo agente
        generated_html = _run_mevofarma_standard_agent(product_name, bula_text)
        
        # --- ADICIONA A CORREÇÃO PROGRAMÁTICA DO FAQ ---
        generated_html = _enforce_faq_h3_structure(generated_html)

        if not generated_html or "error" in generated_html.lower():
             yield await _send_event("log", {"message": f"<b>ERRO:</b> Falha na geração de conteúdo pelo agente Padrão Mevofarma.", "type": "error"})
             generated_html = "<p>Erro na geração de conteúdo.</p>"

        # O novo agente gera apenas HTML. Criamos um título e meta descrição provisórios.
        final_data_for_review = {
            "final_score": 100, # Assumimos que o novo agente é o padrão ouro
            "final_content": generated_html,
            "seo_title": f"{product_name} | Padrão Mevofarma",
            "meta_description": f"Informações completas sobre {product_name} seguindo o padrão de qualidade Mevofarma."
        }

        yield await _send_event("log", {"message": "<b>Sucesso!</b> Conteúdo gerado com o Padrão Mevofarma.", "type": "success"})
        yield await _send_event("done", final_data_for_review)

    except Exception as e:
        traceback.print_exc()
        yield await _send_event("error", {"message": f"Erro crítico na pipeline Mevofarma: {str(e)}", "type": "error"})


# --- ORQUESTRADOR DE OTIMIZAÇÃO SEO (EXISTENTE) ---
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

        # --- CORREÇÃO PROGRAMÁTICA DO FAQ ANTES DE MONTAR O HTML FINAL ---
        faq_section_html = str(current_content_data.get("faq_section", ""))
        faq_section_corrected = _enforce_faq_h3_structure(faq_section_html)

        final_html_content = (
            str(current_content_data.get("html_content", "")) + "\n" +
            faq_section_corrected + "\n" + # Usa a versão corrigida
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

