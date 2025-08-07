# app/prompt_manager.py
import yaml
from jinja2 import Environment, FileSystemLoader, Template
from config import settings

class PromptManager:
    """
    Gerencia o carregamento e a renderização de templates de prompt a partir de arquivos YAML.
    """
    def __init__(self, prompt_dir: str = settings.PROMPTS_DIR):
        self.prompt_dir = prompt_dir
        self.env = Environment(loader=FileSystemLoader(self.prompt_dir))
        self.prompts = self._load_prompts()

    def _load_prompts(self) -> dict:
        """
        Carrega todos os arquivos.yaml do diretório de prompts para um dicionário.
        """
        loaded_prompts = {}
        for filepath in self.prompt_dir.glob("*.yaml"):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    prompt_data = yaml.safe_load(f)
                    prompt_name = filepath.stem  # Nome do arquivo sem extensão
                    loaded_prompts[prompt_name] = prompt_data
            except yaml.YAMLError as e:
                print(f"Erro ao carregar o arquivo de prompt {filepath}: {e}")
            except Exception as e:
                print(f"Erro inesperado ao processar {filepath}: {e}")
        return loaded_prompts

    def render(self, prompt_name: str, **kwargs) -> str:
        """
        Renderiza um prompt específico com as variáveis fornecidas.

        Args:
            prompt_name: O nome do prompt a ser renderizado (corresponde ao nome do arquivo).
            **kwargs: Variáveis dinâmicas para injetar no template.

        Returns:
            A string do prompt final, pronta para ser enviada à API.
        
        Raises:
            ValueError: Se o nome do prompt não for encontrado.
        """
        prompt_data = self.prompts.get(prompt_name)
        if not prompt_data:
            raise ValueError(f"Prompt '{prompt_name}' não encontrado.")

        template_string = prompt_data.get('template')
        if not template_string:
            raise ValueError(f"O prompt '{prompt_name}' não contém uma chave 'template'.")

        # Passa os dados do próprio YAML para o template, além dos kwargs
        # Isso permite usar chaves do YAML como {{ persona }} ou {{ instructions }}
        render_context = {**prompt_data, **kwargs}
        
        template = self.env.from_string(template_string)
        return template.render(render_context)