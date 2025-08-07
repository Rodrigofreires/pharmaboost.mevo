# app/gemini_client.py
import os
from google import genai
from config import settings # Supondo que você tenha um arquivo config.py

class GeminiClient:
    """
    Uma classe wrapper para interagir com a API do Google Gemini,
    utilizando a nova estrutura de cliente.
    Abstrai os detalhes do SDK e centraliza a configuração e as chamadas.
    """
    def __init__(self, model_name: str = settings.DEFAULT_MODEL):
        """
        Inicializa o cliente Gemini.

        Args:
            model_name (str): O nome do modelo a ser usado para as gerações.
                              O padrão é obtido de 'settings.DEFAULT_MODEL'.
        
        Raises:
            ValueError: Se a chave da API Gemini não for encontrada nas configurações.
        """
        if not settings.API_KEY:
            raise ValueError("A chave da API Gemini não foi configurada.")
        
        # Inicializa o cliente principal, passando a chave da API diretamente.
        self.client = genai.Client(api_key=settings.API_KEY)
        
        # Armazena o nome do modelo para ser usado nas chamadas.
        self.model_name = model_name

    def execute_prompt(self, prompt_text: str) -> str:
        """
        Envia um prompt para a API Gemini e retorna a resposta de texto.
        
        Args:
            prompt_text: O prompt a ser enviado para o modelo.

        Returns:
            A resposta de texto gerada pelo modelo ou uma mensagem de erro.
        """
        try:
            # Faz a chamada à API usando a nova estrutura: client.models.generate_content()
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt_text
            )
            return response.text
        except Exception as e:
            # Um tratamento de erro mais robusto pode ser adicionado aqui.
            print(f"Erro ao chamar a API Gemini: {e}")
            return "Ocorreu um erro ao processar sua solicitação."