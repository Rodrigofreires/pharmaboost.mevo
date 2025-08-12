# app/use_cases.py
import json
from typing import List
from urllib.parse import urlparse # Import para extrair a fonte do URL

from bs4 import BeautifulSoup
import requests
from.prompt_manager import PromptManager
from.gemini_client import GeminiClient

# Instancia os componentes centrais que serão usados pelos casos de uso.
# Em uma aplicação maior, isso poderia ser gerenciado por um container de injeção de dependência.
prompt_manager = PromptManager()
gemini_client = GeminiClient()

def summarize_text(text: str, length: int = 50) -> str:
    """
    Gera um resumo de um texto com um comprimento alvo.

    Args:
        text: O texto a ser resumido.
        length: O comprimento aproximado desejado para o resumo (em palavras).

    Returns:
        O texto resumido.
    """
    print(f"Gerando resumo para o texto com {len(text.split())} palavras...")
    final_prompt = prompt_manager.render(
        "summarizer",
        text_to_summarize=text,
        length=length
    )
    summary = gemini_client.execute_prompt(final_prompt)
    print("Resumo gerado com sucesso.")
    return summary

def classify_sentiment(text: str) -> str:
    """
    Classifica o sentimento de um texto usando um prompt few-shot.

    Args:
        text: O texto a ser classificado.

    Returns:
        A classificação de sentimento ("positive", "negative", ou "neutral").
    """
    print(f"Classificando sentimento para o texto: '{text[:50]}...'")
    final_prompt = prompt_manager.render(
        "sentiment_classifier",
        user_text=text
    )

    sentiment = gemini_client.execute_prompt(final_prompt).strip().lower()
    print(f"Sentimento classificado como: {sentiment}")
    return sentiment

def generate_formal_email(recipient_name: str, sender_name: str, tone: str, key_points: List[str]) -> str:
    """
    Gera um e-mail formal usando um prompt complexo.

    Args:
        recipient_name: O nome do destinatário.
        sender_name: O nome do remetente.
        tone: O tom desejado para o e-mail (ex: "persuasivo", "informativo").
        key_points: Uma lista de pontos-chave a serem incluídos no e-mail.

    Returns:
        O texto completo do e-mail gerado.
    """
    print("Gerando e-mail formal...")
    final_prompt = prompt_manager.render(
        "email_generator",
        recipient_name=recipient_name,
        sender_name=sender_name,
        tone=tone,
        key_points=key_points
    )

    email_content = gemini_client.execute_prompt(final_prompt)
    print("E-mail gerado com sucesso.")
    return email_content

def analyze_news_from_url(url: str) -> dict:
    """
    Orquestra o processo completo de análise de notícias a partir de uma URL.
    1. Busca o conteúdo da URL.
    2. Usa o 'news_analyzer' para identificar subjetividade.
    3. Usa o 'news_rewriter' para criar a versão final da matéria.


    Args:
        url: A URL da notícia a ser analisada.

    Returns:
        Um dicionário contendo a matéria final e a análise detalhada.
    """
    # ETAPA 1: Extração de Conteúdo
    try:
        page = requests.get(url, timeout=10)
        page.raise_for_status() # Lança um erro para status ruins (4xx, 5xx)
        soup = BeautifulSoup(page.content, 'html.parser')

        # Lógica simples para extrair texto de parágrafos. Pode ser aprimorada.
        paragraphs = soup.find_all('p')
        news_text = "\n".join([p.get_text() for p in paragraphs])

        if not news_text:
            # Simulação de detecção de paywall
            return {"error": "A notícia está protegida por paywall ou não foi possível extrair o conteúdo. Por favor, forneça o texto completo."}

    except requests.RequestException as e:
        return {"error": f"Não foi possível acessar a URL: {e}"}

    # ETAPA 1.5: Extração da Fonte da Notícia
    parsed_url = urlparse(url)
    news_source = parsed_url.netloc.replace("www.", "")

    # ETAPA 2: Análise com o primeiro prompt
    analyzer_prompt = prompt_manager.render("news_analyzer", news_text=news_text, news_source=news_source)
    analysis_raw = gemini_client.execute_prompt(analyzer_prompt)

    # --- INÍCIO DA CORREÇÃO ---
    # Bloco try-except aprimorado para extrair o JSON da resposta do modelo
    try:
        # Encontra o início e o fim do bloco JSON na string de resposta
        json_start = analysis_raw.find('{')
        json_end = analysis_raw.rfind('}') + 1
        
        if json_start != -1 and json_end != 0:
            json_str = analysis_raw[json_start:json_end]
            analysis_data = json.loads(json_str)
            if 'error' in analysis_data:
                return {"error": analysis_data['error']}
        else:
            # Se não encontrar um JSON, lança um erro
            raise json.JSONDecodeError("Nenhum objeto JSON encontrado na resposta.", analysis_raw, 0)
            
    except json.JSONDecodeError:
        # Se a extração ou o parsing falharem, retorna o erro
        return {"error": "O modelo não retornou uma análise em formato JSON válido, mesmo após as verificações."}
 
    # ETAPA 3: Reescrita com o segundo prompt
    rewriter_prompt = prompt_manager.render(
        "news_rewriter",
        news_text=news_text,
        analysis_json=json.dumps(analysis_data, indent=2, ensure_ascii=False)
    )
    materia_veritare = gemini_client.execute_prompt(rewriter_prompt)

    # ETAPA 4: Montagem da Resposta Final
    por_tras_do_texto = analysis_data.get("subjective_fragments", [])

    return {
        "materia_veritare": materia_veritare,
        "por_tras_do_texto": por_tras_do_texto
    }


def generate_medicine_content(product_name: str, product_info: dict) -> str:
    """
    Gera a descrição completa para um medicamento.

    Args:
        product_name: O nome do medicamento.
        product_info: Um dicionário com as informações do produto.

    Returns:
        O conteúdo gerado para a página do produto.
    """
    print(f"Gerando conteúdo para o medicamento: {product_name}...")
    final_prompt = prompt_manager.render(
        "medicamento_generator",
        product_name=product_name,
        **product_info
    )
    content = gemini_client.execute_prompt(final_prompt)
    print("Conteúdo para medicamento gerado com sucesso.")
    return content

def generate_vitamin_content(product_name: str, product_info: dict) -> str:
    """
    Gera a descrição completa para uma vitamina ou suplemento.

    Args:
        product_name: O nome da vitamina/suplemento.
        product_info: Um dicionário com as informações do produto.

    Returns:
        O conteúdo gerado para a página do produto.
    """
    print(f"Gerando conteúdo para a vitamina: {product_name}...")
    final_prompt = prompt_manager.render(
        "vitamina_suplemento_generator",
        product_name=product_name,
        **product_info
    )
    content = gemini_client.execute_prompt(final_prompt)
    print("Conteúdo para vitamina gerado com sucesso.")
    return content

def generate_dermocosmetic_content(product_name: str, product_info: dict) -> str:
    """
    Gera a descrição completa para um dermocosmético.

    Args:
        product_name: O nome do dermocosmético.
        product_info: Um dicionário com as informações do produto.

    Returns:
        O conteúdo gerado para a página do produto.
    """
    print(f"Gerando conteúdo para o dermocosmético: {product_name}...")
    final_prompt = prompt_manager.render(
        "dermocosmetico_generator",
        product_name=product_name,
        **product_info
    )
    content = gemini_client.execute_prompt(final_prompt)
    print("Conteúdo para dermocosmético gerado com sucesso.")
    return content