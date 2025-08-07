# app/use_cases.py
from typing import List
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