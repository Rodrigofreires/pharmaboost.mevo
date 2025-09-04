# app/gemini_client.py (Corrected Version)
import os
from config import settings
from google import genai
from google.genai import types # Import the types module
from google.api_core import exceptions

class GeminiClient:
    """
    Cliente wrapper para a API Gemini, usando a arquitetura stateless do SDK unificado 'google-genai'.
    """
    def __init__(self):
        if not settings.API_KEY:
            raise ValueError("A variável de ambiente GEMINI_API_KEY não foi encontrada.")

        # A autenticação é feita APENAS aqui, no construtor do Client.
        self.client = genai.Client(api_key=settings.API_KEY)

        print(f"Cliente Gemini (google-genai SDK) inicializado com sucesso.")

    def execute_prompt_sync(self, prompt_text: str) -> str:
        """
        Executa um prompt de forma síncrona.
        """
        try:
            # CORREÇÃO DEFINITIVA: A chamada é feita através do serviço 'models' do cliente.
            # O nome do modelo e as configurações são passados como argumentos aqui.
            response = self.client.models.generate_content(
                model=f"models/{settings.DEFAULT_MODEL}",
                contents=prompt_text,
                # CORREÇÃO: Bundled generation_config and safety_settings
                generation_config=types.GenerationConfig(
                    **settings.GENERATION_CONFIG,
                    safety_settings=settings.SAFETY_SETTINGS
                )
            )

            if response and hasattr(response, 'text') and response.text:
                return response.text
            else:
                print("API Gemini retornou uma resposta síncrona vazia.")
                return '{"error": "A API do Gemini retornou uma resposta vazia ou nula."}'
        except Exception as e:
            print(f"Erro inesperado no cliente Gemini: {e}")
            # Propaga o erro para que o worker possa capturá-lo e reportá-lo.
            raise RuntimeError(f"Ocorreu um erro inesperado no cliente: {str(e)}") from e