import re

class SeoOptimizerAgent:
    """
    Classe de utilidades para o processo de otimização.
    """
    MEVO_STYLE_BLOCK = """<style>
    /* --- ESTILO VISUAL MEVOFARMA (COM ESCOPO) --- */
    @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap');

    .descricao-customizada {
        font-family: 'Nunito', sans-serif; 
        color: #333; 
        line-height: 1.7; 
        padding: 1em; /* Adiciona um respiro nas bordas */
    }
    .descricao-customizada .content-section p, 
    .descricao-customizada .content-section ul, 
    .descricao-customizada .faq-section p,
    .descricao-customizada p {
        font-size: 16px;
        font-weight: 400;
        margin-bottom: 1.25em; 
    }
    .descricao-customizada h2, 
    .descricao-customizada h3, 
    .descricao-customizada h4, 
    .descricao-customizada summary {
        color: #3d0e6b; /* Roxo Mevofarma */
        font-weight: 800;
        line-height: 1.2;
        margin-bottom: 0.5em; 
    }
    .descricao-customizada .content-section h2, 
    .descricao-customizada .faq-section h2 { 
        font-size: 1.75em;
        margin-top: 1.5em; 
        border-bottom: 2px solid #f0f0f0; 
        padding-bottom: 0.4em; 
    }
    .descricao-customizada .content-section h3 { 
        font-size: 1.4em;
        font-weight: 700;
        margin-top: 1.5em; 
    }
    .descricao-customizada .faq-section h4 {
        font-size: 1.15em;
        font-weight: 700;
        margin: 0;
        padding-left: 0.5em;
    }
    .descricao-customizada ul { 
        list-style-position: inside; 
        padding-left: 1em; 
    }
    .descricao-customizada a {
        color: #d63384; /* Pink Mevofarma */
        text-decoration: none;
        font-weight: 600;
    }
    .descricao-customizada a:hover {
        text-decoration: underline;
    }
    .descricao-customizada strong {
        font-weight: 700;
        color: #3d0e6b;
    }

    /* --- FAQ --- */
    .descricao-customizada .faq-section details,
    .descricao-customizada details { 
        background-color: #f8f9fa; 
        border: 1px solid #dee2e6; 
        border-radius: 8px; 
        margin-bottom: 0.75em; 
        padding: 1em 1.25em; 
    }
    .descricao-customizada .faq-section summary,
    .descricao-customizada summary { 
        cursor: pointer;
        display: flex;
        align-items: center;
        list-style-position: inside;
    }
    .descricao-customizada .faq-section summary::-webkit-details-marker,
    .descricao-customizada summary::-webkit-details-marker { display: none; }
    .descricao-customizada .faq-section summary::before,
    .descricao-customizada summary::before {
        content: '▼';
        font-size: 0.8em;
        margin-right: 0.75em;
        transition: transform 0.2s;
        color: #3d0e6b;
    }
    .descricao-customizada .faq-section details[open] > summary::before,
    .descricao-customizada details[open] > summary::before {
        transform: rotate(180deg);
    }
    
    /* --- Tabela de Informações --- */
    .descricao-customizada .info-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 1.5em;
        font-size: 15px;
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid #dee2e6;
    }
    .descricao-customizada .info-table td {
        padding: 0.8em 1em;
        border-bottom: 1px solid #dee2e6;
    }
    .descricao-customizada .info-table tr:last-child td { border-bottom: none; }
    .descricao-customizada .info-table tr:nth-child(even) { background-color: #f8f9fa; }
    .descricao-customizada .info-table td:first-child {
        font-weight: 700;
        color: #3d0e6b;
        width: 30%;
    }

    /* --- Aviso Legal Final (Tons de Cinza) --- */
    .descricao-customizada .legal-notice-box {
        background-color: #f8f9fa; /* Cinza bem claro */
        color: #495057; /* Cinza escuro */
        border: 1px solid #dee2e6;
        border-radius: 8px;
        padding: 1.5em;
        margin-top: 2em;
        text-align: center;
        font-size: 0.9em;
        line-height: 1.6;
    }
    .descricao-customizada .legal-notice-box strong {
        color: #212529;
    }

    /* --- Nota de Transparência (Final) --- */
    .descricao-customizada .transparency-note-final {
        font-size: 0.85em;
        color: #6c757d;
        text-align: center;
        margin-top: 2.5em;
        padding-top: 1.5em;
        border-top: 1px solid #dee2e6;
    }
</style>"""

    @staticmethod
    def _clean_and_correct_html(html_content: str) -> str:
        """
        Limpa, corrige, estiliza e garante que o HTML final seja um fragmento autônomo,
        ideal para ser inserido em outras páginas, sem `<html>` ou `<body>`.
        """
        if not isinstance(html_content, str):
            html_content = ""
        
        # Limpa o conteúdo recebido da IA
        cleaned_html = html_content.strip()
        cleaned_html = re.sub(r'^```html\s*', '', cleaned_html)
        cleaned_html = re.sub(r'\s*```$', '', cleaned_html)
        
        # Garante que todas as tags <details> estejam abertas por padrão
        corrected_html = re.sub(r'<details(?! open)>', '<details open>', cleaned_html)
        
        # Monta o bloco de código final apenas com o estilo e o conteúdo,
        # sem a estrutura de documento completo (DOCTYPE, html, head, body).
        final_html = f"""
{SeoOptimizerAgent.MEVO_STYLE_BLOCK}
{corrected_html}
"""
        return final_html
''