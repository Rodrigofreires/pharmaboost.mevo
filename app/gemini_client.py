# app/gemini_client.py
import os
from google import genai
from config import settings

class GeminiClient:
    """
    Uma classe wrapper para interagir com a API do Google Gemini,
    utilizando a nova estrutura de cliente.
    Abstrai os detalhes do SDK e centraliza a configuração e as chamadas.
    """
    def __init__(self, model_name: str = settings.DEFAULT_MODEL):
        """
        Inicializa o cliente Gemini.
        """
        if not settings.API_KEY:
            raise ValueError("A chave da API Gemini não foi configurada.")
        
        self.client = genai.Client(api_key=settings.API_KEY)
        self.model_name = model_name

    def execute_prompt(self, prompt_text: str) -> str:
        """
        Envia um prompt para a API Gemini e retorna a resposta de texto,
        garantindo que nunca retorne um valor Nulo.
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt_text
            )
            
            # --- INÍCIO DA CORREÇÃO ---
            if response and response.text:
                return response.text
            else:
                print("API Gemini retornou uma resposta vazia.")
                return '{"error": "A API do Gemini retornou uma resposta vazia ou nula."}'

        except Exception as e:
            # Em caso de erro na chamada, também retorna um JSON de erro.
            print(f"Erro ao chamar a API Gemini: {e}")
            return f'{{"error": "Ocorreu um erro ao chamar a API Gemini: {str(e)}"}}'