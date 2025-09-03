# app/gemini_client.py (Versão Robusta)
import os
from config import settings
from google import genai
from google.api_core import exceptions

class GeminiClient:
    """
    Uma classe wrapper para interagir com a API do Google Gemini,
    utilizando o padrão de cliente mais recente.
    """
    def __init__(self):
        """
        Inicializa o cliente Gemini. A API Key é carregada a partir
        das configurações e passada diretamente para o cliente.
        """
        api_key = settings.API_KEY
        if not api_key:
            raise ValueError("A variável de ambiente GEMINI_API_KEY não foi encontrada. Verifique seu arquivo .env.")
        
        self.client = genai.Client(api_key=api_key)

    def execute_prompt(self, prompt_text: str, **kwargs) -> str:
        """
        Envia um prompt para a API Gemini e retorna a resposta de texto.
        Agora, propaga exceções da API para tratamento superior.
        """
        try:
            model_name = settings.DEFAULT_MODEL
            response = self.client.models.generate_content(
                model=model_name,
                contents=prompt_text,
            )
            
            if response and hasattr(response, 'text') and response.text:
                return response.text
            else:
                print("API Gemini retornou uma resposta vazia.")
                return '{"error": "A API do Gemini retornou uma resposta vazia ou nula."}'

        except exceptions.GoogleAPICallError as e:
            # Propaga exceções da API para que a camada de use_cases possa tratá-las
            print(f"Erro na API Gemini detectado no cliente: {e.message}")
            raise e # Re-lança a exceção específica da API
        except Exception as e:
            print(f"Erro inesperado no cliente Gemini: {e}")
            # Retorna um JSON de erro formatado para erros não relacionados à API
            return f'{{"error": "Ocorreu um erro inesperado no cliente: {str(e)}"}}'