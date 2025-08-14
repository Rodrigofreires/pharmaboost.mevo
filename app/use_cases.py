import json
from typing import List, Dict, Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import requests
from .prompt_manager import PromptManager
from .gemini_client import GeminiClient

# Instancia os componentes centrais que serão usados pelos casos de uso.
prompt_manager = PromptManager()
gemini_client = GeminiClient()

# --- FUNÇÃO CORRIGIDA ---
def generate_medicine_content(product_name: str, bula_text: str) -> Dict[str, str]:
    """
    Gera a descrição completa para um medicamento a partir do texto da sua bula.
    VERSÃO ROBUSTA: Inclui lógica aprimorada para extrair JSON da resposta da IA.
    """
    print(f"Gerando conteúdo para o medicamento: {product_name}...")
    
    # Renderiza o prompt atualizado
    final_prompt = prompt_manager.render(
        "medicamento_generator", 
        product_name=product_name,
        bula_text=bula_text
    )
    
    # Executa o prompt
    response_raw = gemini_client.execute_prompt(final_prompt)

    try:
        # Lógica de extração de JSON aprimorada e mais robusta
        # Encontra o primeiro '{' e o último '}' na resposta.
        json_start = response_raw.find('{')
        json_end = response_raw.rfind('}') + 1

        if json_start == -1 or json_end == 0:
            # Se não encontrar um JSON, lança um erro claro.
            raise json.JSONDecodeError("Nenhum objeto JSON válido encontrado na resposta da IA.", response_raw, 0)
        
        # Extrai a substring que provavelmente é o JSON
        json_str = response_raw[json_start:json_end]
        
        # Tenta decodificar o JSON
        content_data = json.loads(json_str)

        # Validação para garantir que as chaves esperadas estão presentes
        if all(k in content_data for k in ["html_content", "seo_title", "meta_description"]):
            print(f"SUCESSO: Conteúdo para '{product_name}' gerado e validado.")
            return content_data
        else:
            # Se o JSON for válido mas não tiver as chaves, é um erro de conteúdo.
            raise KeyError("A resposta da IA é um JSON válido, mas não contém as chaves esperadas (html_content, seo_title, meta_description).")

    except json.JSONDecodeError:
        error_msg = f"Erro de JSON ao processar '{product_name}'. A IA não retornou um JSON válido."
        print(error_msg)
        # Retorna a resposta crua da IA para facilitar a depuração
        return {"error": error_msg, "raw_response_for_debug": response_raw}
    except Exception as e:
        error_msg = f"Erro inesperado ao processar '{product_name}': {str(e)}"
        print(error_msg)
        return {"error": error_msg}


# --- OUTRAS FUNÇÕES (MANTIDAS COMO ESTAVAM) ---

def summarize_text(text: str, length: int = 50) -> str:
    final_prompt = prompt_manager.render("summarizer", text_to_summarize=text, length=length)
    return gemini_client.execute_prompt(final_prompt)

def classify_sentiment(text: str) -> str:
    final_prompt = prompt_manager.render("sentiment_classifier", user_text=text)
    return gemini_client.execute_prompt(final_prompt).strip().lower()

def generate_formal_email(recipient_name: str, sender_name: str, tone: str, key_points: List[str]) -> str:
    final_prompt = prompt_manager.render("email_generator", recipient_name=recipient_name, sender_name=sender_name, tone=tone, key_points=key_points)
    return gemini_client.execute_prompt(final_prompt)

def analyze_news_from_url(url: str) -> dict:
    try:
        page = requests.get(url, timeout=10)
        page.raise_for_status()
        soup = BeautifulSoup(page.content, 'html.parser')
        paragraphs = soup.find_all('p')
        news_text = "\n".join([p.get_text() for p in paragraphs])
        if not news_text:
            return {"error": "A notícia está protegida por paywall ou não foi possível extrair o conteúdo."}
    except requests.RequestException as e:
        return {"error": f"Não foi possível acessar a URL: {e}"}

    parsed_url = urlparse(url)
    news_source = parsed_url.netloc.replace("www.", "")
    analyzer_prompt = prompt_manager.render("news_analyzer", news_text=news_text, news_source=news_source)
    analysis_raw = gemini_client.execute_prompt(analyzer_prompt)

    try:
        json_start = analysis_raw.find('{')
        json_end = analysis_raw.rfind('}') + 1
        if json_start != -1 and json_end != 0:
            json_str = analysis_raw[json_start:json_end]
            analysis_data = json.loads(json_str)
            if 'error' in analysis_data: return {"error": analysis_data['error']}
        else:
            raise json.JSONDecodeError("Nenhum objeto JSON encontrado na resposta.", analysis_raw, 0)
    except json.JSONDecodeError:
        return {"error": "O modelo não retornou uma análise em formato JSON válido."}
 
    rewriter_prompt = prompt_manager.render("news_rewriter", news_text=news_text, analysis_json=json.dumps(analysis_data, indent=2, ensure_ascii=False))
    materia_veritare = gemini_client.execute_prompt(rewriter_prompt)
    por_tras_do_texto = analysis_data.get("subjective_fragments", [])
    return {"materia_veritare": materia_veritare, "por_tras_do_texto": por_tras_do_texto}

def generate_vitamin_content(product_name: str, product_info: dict) -> str:
    final_prompt = prompt_manager.render("vitamina_suplemento_generator", product_name=product_name, **product_info)
    return gemini_client.execute_prompt(final_prompt)

def generate_dermocosmetic_content(product_name: str, product_info: dict) -> str:
    final_prompt = prompt_manager.render("dermocosmetico_generator", product_name=product_name, **product_info)
    return gemini_client.execute_prompt(final_prompt)
