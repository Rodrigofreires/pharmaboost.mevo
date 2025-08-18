import re

class SeoOptimizerAgent:
    """
    Classe de utilidades para o processo de otimização.
    A lógica principal de orquestração foi movida para use_cases.py.
    """
    MEVO_STYLE_BLOCK = """<style>
    .faq-section, .content-section { 
        font-family: 'Inter', sans-serif; 
        color: #1f2937; 
        line-height: 1.6; 
    }
    .content-section p, .content-section ul, .faq-section p {
        font-size: 16px;
        font-weight: 400; /* Garante que o texto comum não seja negrito */
    }
    .content-section h1, .content-section h2, .content-section h3, .faq-section h2, .faq-section summary {
        color: #3d0e6b;
        font-weight: 700;
        line-height: 110%;
    }
    .content-section h1 { 
        font-size: 2.2em; /* 36px */
        margin-bottom: 0.5em; 
    }
    .content-section h2, .faq-section h2 { 
        font-size: 1.8em; /* 28px */
        margin-top: 1.5em; 
        margin-bottom: 0.75em; 
        border-bottom: 2px solid #e5e7eb; 
        padding-bottom: 0.3em; 
    }
    .content-section h3 { 
        font-size: 1.4em; /* 22px */
        margin-top: 1.2em; 
        margin-bottom: 0.5em; 
    }
    .content-section p, .content-section ul { 
        margin-bottom: 1em; 
    }
    .content-section ul { 
        list-style-position: inside; 
        padding-left: 1em; 
    }
    .faq-section details { 
        background-color: #f9fafb; 
        border: 1px solid #e5e7eb; 
        border-radius: 8px; 
        margin-bottom: 0.5em; 
        padding: 0.75em 1.25em; 
    }
    .faq-section summary { 
        cursor: pointer; 
        font-size: 1.2em; /* 19px */
    }
</style>"""

    # O construtor __init__ não é necessário se os métodos da classe são estáticos
    # e não manipulam o estado da instância.
    
    # CORREÇÃO 1: O método foi convertido para um método estático (@staticmethod),
    # pois não depende de nenhuma instância específica da classe (self).
    @staticmethod
    def _clean_and_correct_html(html_content: str) -> str:
        """
        Limpa, corrige e estiliza o HTML final antes de enviá-lo.
        """
        if not isinstance(html_content, str):
            html_content = ""
        
        # CORREÇÃO 2: As operações de limpeza agora são encadeadas corretamente.
        # O segundo re.sub() opera no resultado do primeiro, garantindo que
        # ambas as remoções de marcadores de código funcionem.
        cleaned_html = html_content.strip()
        cleaned_html = re.sub(r'^```html\s*', '', cleaned_html)
        cleaned_html = re.sub(r'\s*```$', '', cleaned_html)
        
        # Garante que todas as tags <details> estejam abertas por padrão
        # Esta linha já estava correta.
        corrected_html = re.sub(r'<details(?! open)>', '<details open>', cleaned_html)
        
        # CORREÇÃO 3: Acessa o atributo de classe diretamente via `SeoOptimizerAgent`
        # no contexto de um método estático.
        final_html = SeoOptimizerAgent.MEVO_STYLE_BLOCK + "\n" + corrected_html
        return final_html