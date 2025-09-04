# config/settings.py
import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo.env
# A base_dir aponta para a raiz do projeto
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Configurações da API Gemini
API_KEY = os.getenv("GEMINI_API_KEY")
DEFAULT_MODEL = "gemini-2.5-flash"
REQUEST_TIMEOUT = 120

# Caminhos de diretório
PROMPTS_DIR = BASE_DIR / "prompts"
LOGS_DIR = BASE_DIR / "logs"