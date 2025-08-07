# quick_test.py
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Carrega as variáveis do arquivo .env para o ambiente
load_dotenv()

# Bloco try-except para um tratamento de erros robusto
try:
    # Pega a chave da API do ambiente
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("A variável de ambiente GEMINI_API_KEY não foi encontrada.")
    
    # --- Início da Adaptação ---

    # 1. Inicializa o cliente, passando a chave da API diretamente.
    #    Esta é a principal mudança da solução que você encontrou.
    client = genai.Client(api_key=api_key)
    
    # 2. Define o modelo e o prompt a serem usados.
    model_name = 'gemini-2.5-flash' 
    prompt_text = "Explique o que é engenharia de prompt em uma frase."
    
    # 3. Faz a chamada à API usando o cliente.
    #    Note a estrutura: client.models.generate_content()
    response = client.models.generate_content(
        model=model_name,
        contents=prompt_text
    )

    # Imprime a resposta de texto
    print("Conexão bem-sucedida!")
    print("Resposta do Gemini:", response.text)

except Exception as e:
    print(f"Ocorreu um erro: {e}")