# app/pharma_seo_optimizer.py

import re
from bs4 import BeautifulSoup

class SeoOptimizerAgent:
    """
    Classe de utilidades para o processo de otimização, incluindo a finalização para V-TEX.
    """
    # O MEVO_STYLE_BLOCK continua o mesmo, sem alterações.
    MEVO_STYLE_BLOCK = """<style>
    /* --- ESTILO VISUAL MEVOFARMA (COM ESCOPO) --- */
    @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;700;800&display=swap');

    .descricao-produto {
        font-family: 'Nunito', sans-serif;
        color: #333;
        line-height: 1.6;
        max-width: 800px;
        margin: 0 auto;
        padding: 20px;
    }
    .descricao-produto h2 {
        color: #3d0e6b;
        font-size: 24px;
        font-weight: 800;
        margin-top: 30px;
        margin-bottom: 15px;
        border-bottom: 2px solid #f0f0f0;
        padding-bottom: 10px;
    }
    .descricao-produto h3 {
        color: #3d0e6b;
        font-size: 20px;
        font-weight: 700;
        margin-top: 25px;
        margin-bottom: 10px;
    }
    .descricao-produto p,
    .descricao-produto ul {
        margin-bottom: 15px;
        text-align: justify;
        font-size: 16px;
    }
    .descricao-produto ul {
        list-style-type: disc;
        margin-left: 20px;
    }
    .descricao-produto ul li {
        margin-bottom: 8px;
    }
    .descricao-produto table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 20px;
        margin-bottom: 20px;
        font-size: 15px;
    }
    .descricao-produto table td {
        border: 1px solid #dee2e6;
        padding: 12px;
        text-align: left;
    }
    .descricao-produto table tr td:first-child {
        font-weight: bold;
        color: #3d0e6b;
        background-color: #f8f9fa;
        width: 30%;
    }

    /* --- ESTILOS MELHORADOS PARA A FAQ (ACCORDION) --- */
    .descricao-produto details {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 8px;
        margin-bottom: 10px;
        transition: background-color 0.2s ease;
    }
    .descricao-produto summary {
        display: flex; /* Alinha o marcador com o texto */
        align-items: center;
        padding: 15px;
        cursor: pointer;
        outline: none;
        font-weight: bold; /* Garante que o texto dentro do summary seja negrito */
    }
    .descricao-produto summary h2 {
        font-size: 20px; /* Ajusta o tamanho do H2 dentro do accordion */
        font-weight: 700;
        margin: 0; /* Remove margens do H2 para alinhar corretamente */
        border: none; /* Remove a borda do H2 dentro do accordion */
        padding: 0;
    }
    .descricao-produto summary::-webkit-details-marker {
        display: none; /* Esconde o marcador padrão */
    }
    .descricao-produto summary::before {
        content: '▼'; /* Adiciona nosso próprio marcador */
        margin-right: 15px;
        font-size: 0.8em;
        transition: transform 0.2s ease;
    }
    .descricao-produto details[open] > summary::before {
        transform: rotate(180deg);
    }
    .descricao-produto details[open] {
        background-color: #f1e4ff;
    }
    .descricao-produto details p {
        padding: 0 15px 15px 15px; /* Adiciona padding à resposta */
        margin: 0;
        background-color: #fff;
        border-top: 1px solid #dee2e6; /* Linha separadora */
    }

    .descricao-produto .legal-notice-box {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 8px;
        padding: 20px;
        margin-top: 30px;
        margin-bottom: 20px;
        color: #495057;
        text-align: center;
        font-size: 14px;
        line-height: 1.6;
    }
    .descricao-produto .transparency-note-final {
        font-size: 13px;
        color: #6c757d;
        text-align: center;
        margin-top: 25px;
        padding-top: 15px;
        border-top: 1px solid #dee2e6;
    }
</style>"""

    @staticmethod
    def _clean_and_correct_html(html_content: str) -> str:
        """
        Limpa o HTML recebido da IA, removendo marcações de código como ```html.
        """
        if not isinstance(html_content, str):
            return ""
        
        cleaned_html = html_content.strip()
        cleaned_html = re.sub(r'^```html\s*', '', cleaned_html, flags=re.IGNORECASE)
        cleaned_html = re.sub(r'\s*```$', '', cleaned_html)
        
        return cleaned_html

    @staticmethod
    def _finalize_for_vtex(html_content: str, product_name: str) -> str:
        """
        Garante que o HTML final seja um fragmento único, seguro para a V-TEX.
        Remove tags globais e envolve todo o conteúdo na div pai com o CSS.
        O 'product_name' é mantido para futuras lógicas, mas a correção de título
        agora é feita diretamente pelo prompt.
        """
        if not isinstance(html_content, str):
            return ""

        # A lógica de correção de título foi removida daqui, pois agora é
        # responsabilidade do prompt.
        clean_html = SeoOptimizerAgent._clean_and_correct_html(html_content)
        
        soup = BeautifulSoup(clean_html, 'html.parser')

        for tag in soup.find_all(['html', 'body', 'head', 'header', 'footer']):
            tag.unwrap()

        content_string = "".join(str(c) for c in soup.contents)

        final_html = f'''{SeoOptimizerAgent.MEVO_STYLE_BLOCK}
<div class="descricao-produto">
{content_string.strip()}
</div>'''

        return final_html