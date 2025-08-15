import json
from typing import Dict, Any

# --- Inicialização Preguiçosa (Lazy Initialization) ---
# Estas variáveis globais guardarão as instâncias dos nossos serviços.
# Elas começam como None e serão criadas na primeira vez que uma função as solicitar.
# Esta abordagem evita os erros de importação circular.

_prompt_manager = None
_gemini_client = None
_seo_optimizer_agent = None

def _get_prompt_manager():
    """Retorna uma instância única (singleton) do PromptManager."""
    global _prompt_manager
    if _prompt_manager is None:
        # A importação é feita aqui, dentro da função, para quebrar o ciclo.
        from .prompt_manager import PromptManager
        _prompt_manager = PromptManager()
    return _prompt_manager

def _get_gemini_client():
    """Retorna uma instância única (singleton) do GeminiClient."""
    global _gemini_client
    if _gemini_client is None:
        # A importação é feita aqui, dentro da função.
        from .gemini_client import GeminiClient
        _gemini_client = GeminiClient()
    return _gemini_client

def _get_seo_optimizer_agent():
    """Retorna uma instância única (singleton) do SeoOptimizerAgent."""
    global _seo_optimizer_agent
    if _seo_optimizer_agent is None:
        # A importação é feita aqui, dentro da função.
        from .pharma_seo_optimizer import SeoOptimizerAgent
        # O agente precisa das outras instâncias, que também são obtidas de forma preguiçosa.
        prompt_manager = _get_prompt_manager()
        gemini_client = _get_gemini_client()
        _seo_optimizer_agent = SeoOptimizerAgent(prompt_manager, gemini_client)
    return _seo_optimizer_agent

def generate_medicine_content(product_name: str, bula_text: str) -> Dict[str, str]:
    """
    Gera a descrição completa para um medicamento a partir do texto da sua bula.
    """
    # Obtém as instâncias necessárias. Elas serão criadas apenas na primeira chamada.
    prompt_manager = _get_prompt_manager()
    gemini_client = _get_gemini_client()

    print(f"Gerando conteúdo para o medicamento: {product_name}...")
    
    final_prompt = prompt_manager.render(
        "medicamento_generator", 
        product_name=product_name,
        bula_text=bula_text
    )
    
    response_raw = gemini_client.execute_prompt(final_prompt)

    try:
        # Lógica robusta para extrair JSON da resposta da IA
        json_start = response_raw.find('{')
        json_end = response_raw.rfind('}') + 1

        if json_start == -1 or json_end == 0:
            raise json.JSONDecodeError("Nenhum objeto JSON válido encontrado na resposta da IA.", response_raw, 0)
        
        json_str = response_raw[json_start:json_end]
        content_data = json.loads(json_str)

        if all(k in content_data for k in ["html_content", "seo_title", "meta_description"]):
            print(f"SUCESSO: Conteúdo para '{product_name}' gerado e validado.")
            return content_data
        else:
            raise KeyError("A resposta da IA é um JSON válido, mas não contém as chaves esperadas.")

    except (json.JSONDecodeError, KeyError) as e:
        error_msg = f"Erro ao processar a resposta da IA para '{product_name}': {e}"
        print(error_msg)
        return {"error": error_msg, "raw_response_for_debug": response_raw}
    except Exception as e:
        error_msg = f"Erro inesperado ao processar '{product_name}': {str(e)}"
        print(error_msg)
        return {"error": error_msg}

def run_seo_optimization_stream(product_type: str, product_name: str, product_info: Dict[str, Any]):
    """
    Executa o fluxo de otimização de SEO e retorna um gerador para o stream de eventos.
    """
    # Obtém a instância do agente otimizador.
    seo_optimizer_agent = _get_seo_optimizer_agent()
    
    return seo_optimizer_agent.run_optimization(
        product_type=product_type,
        product_name=product_name,
        product_info=product_info
    )
