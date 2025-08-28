import re

class SeoOptimizerAgent:
    """
    Classe de utilidades para o processo de otimização.
    """
    MEVO_STYLE_BLOCK = """<style>
    /* --- ESTILO VISUAL MEVOFARMA --- */
    @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap');

    body {
        font-family: 'Nunito', sans-serif; 
        color: #333; 
        line-height: 1.7; 
        padding: 1em; /* Adiciona um respiro nas bordas */
    }
    .content-section p, .content-section ul, .faq-section p {
        font-size: 16px;
        font-weight: 400;
        margin-bottom: 1.25em; 
    }
    h2, h3, h4, summary {
        color: #3d0e6b; /* Roxo Mevofarma */
        font-weight: 800;
        line-height: 1.2;
        margin-bottom: 0.5em; 
    }
    .content-section h2, .faq-section h2 { 
        font-size: 1.75em;
        margin-top: 1.5em; 
        border-bottom: 2px solid #f0f0f0; 
        padding-bottom: 0.4em; 
    }
    .content-section h3 { 
        font-size: 1.4em;
        font-weight: 700;
        margin-top: 1.5em; 
    }
    .faq-section h4 {
        font-size: 1.15em;
        font-weight: 700;
        margin: 0;
        padding-left: 0.5em;
    }
    ul { 
        list-style-position: inside; 
        padding-left: 1em; 
    }
    a {
        color: #d63384; /* Pink Mevofarma */
        text-decoration: none;
        font-weight: 600;
    }
    a:hover {
        text-decoration: underline;
    }
    strong {
        font-weight: 700;
        color: #3d0e6b;
    }

    /* --- FAQ --- */
    .faq-section details { 
        background-color: #f8f9fa; 
        border: 1px solid #dee2e6; 
        border-radius: 8px; 
        margin-bottom: 0.75em; 
        padding: 1em 1.25em; 
    }
    .faq-section summary { 
        cursor: pointer;
        display: flex;
        align-items: center;
        list-style-position: inside;
    }
    .faq-section summary::-webkit-details-marker { display: none; }
    .faq-section summary::before {
        content: '▼';
        font-size: 0.8em;
        margin-right: 0.75em;
        transition: transform 0.2s;
        color: #3d0e6b;
    }
    .faq-section details[open] > summary::before {
        transform: rotate(180deg);
    }
    
    /* --- Tabela de Informações --- */
    .info-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 1.5em;
        font-size: 15px;
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid #dee2e6;
    }
    .info-table td {
        padding: 0.8em 1em;
        border-bottom: 1px solid #dee2e6;
    }
    .info-table tr:last-child td { border-bottom: none; }
    .info-table tr:nth-child(even) { background-color: #f8f9fa; }
    .info-table td:first-child {
        font-weight: 700;
        color: #3d0e6b;
        width: 30%;
    }

    /* --- Aviso Legal Final (Tons de Cinza) --- */
    .legal-notice-box {
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
    .legal-notice-box strong {
        color: #212529;
    }

    /* --- Nota de Transparência (Final) --- */
    .transparency-note-final {
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
        Limpa, corrige, estiliza e envolve o HTML final em uma estrutura de documento completa.
        """
        if not isinstance(html_content, str):
            html_content = ""
        
        # Limpa o conteúdo recebido da IA
        cleaned_html = html_content.strip()
        cleaned_html = re.sub(r'^```html\s*', '', cleaned_html)
        cleaned_html = re.sub(r'\s*```$', '', cleaned_html)
        
        # Garante que todas as tags <details> estejam abertas por padrão
        corrected_html = re.sub(r'<details(?! open)>', '<details open>', cleaned_html)
        
        # --- CORREÇÃO APLICADA AQUI ---
        # Envolve o conteúdo em uma estrutura HTML completa para o iframe
        final_html = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Preview de Conteúdo</title>
    {SeoOptimizerAgent.MEVO_STYLE_BLOCK}
</head>
<body>
    {corrected_html}
</body>
</html>
"""
        return final_html
