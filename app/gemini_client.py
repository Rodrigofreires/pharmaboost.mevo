# app/gemini_client.py (Versão Definitiva - Corrigida com base na documentação)
import os
from config import settings
from google import genai
from google.genai import types

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
        
        # Padrão da documentação mais recente
        self.client = genai.Client(api_key=api_key)

    def execute_prompt(self, prompt_text: str, **kwargs) -> str:
        """
        Envia um prompt para a API Gemini e retorna a resposta de texto.
        """
        try:
            model_name = settings.DEFAULT_MODEL
            
            config = types.GenerateContentConfig(**kwargs) if kwargs else None

            response = self.client.models.generate_content(
                model=f'models/{model_name}',
                contents=prompt_text,
                config=config  
            )
            
            if response and hasattr(response, 'text') and response.text:
                return response.text
            else:
                print("API Gemini retornou uma resposta vazia.")
                return '{"error": "A API do Gemini retornou uma resposta vazia ou nula."}'

        except Exception as e:
            print(f"Erro ao chamar a API Gemini: {e}")
            return f'{{"error": "Ocorreu um erro ao chamar a API Gemini: {str(e)}"}}'