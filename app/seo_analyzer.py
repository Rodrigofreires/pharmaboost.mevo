# app/seo_analyzer.py (Versão com Análise Granular)
import re
from bs4 import BeautifulSoup

def check_title_and_meta(soup: BeautifulSoup, product_name: str) -> dict:
    """
    Regra 1: Verifica o Título H1 e o primeiro parágrafo (meta descrição).
    """
    score = 0
    feedback = []
    max_score = 25 # Total de pontos para esta regra

    h1_tag = soup.find('h1')
    if h1_tag:
        h1_text = h1_tag.get_text(strip=True)
        if product_name.lower() in h1_text.lower():
            score += 15
        else:
            feedback.append("- O título H1 não contém o nome exato do produto.")

        if len(h1_text) > 70:
            feedback.append("- O título H1 é muito longo (ideal: até 70 caracteres).")
        
    else:
        feedback.append("- Conteúdo não possui uma tag H1 principal.")

    first_p = soup.find('p')
    if first_p:
        meta_desc = first_p.get_text(strip=True)
        if not (120 <= len(meta_desc) <= 160):
            feedback.append(f"- O primeiro parágrafo (usado como meta descrição) está fora do tamanho ideal de 120-160 caracteres (tamanho atual: {len(meta_desc)}).")
        else:
            score += 10
    else:
        feedback.append("- Não foi encontrado um primeiro parágrafo para servir como meta descrição.")
        
    return {"score": score, "max_score": max_score, "feedback": feedback}

def check_structure_and_readability(soup: BeautifulSoup) -> dict:
    """
    Regra 2: Verifica a estrutura de subtítulos (H2) e a legibilidade (listas e parágrafos).
    """
    score = 0
    feedback = []
    max_score = 30 # Total de pontos para esta regra

    # Subtítulos H2
    h2_tags = soup.find_all('h2')
    if len(h2_tags) >= 3:
        score += 20
    else:
        feedback.append(f"- O texto usa poucos subtítulos H2 ({len(h2_tags)} encontrados, mínimo: 3) para uma boa escaneabilidade.")

    # Uso de listas
    ul_ol_tags = soup.find_all(['ul', 'ol'])
    if ul_ol_tags:
        score += 10
    else:
        feedback.append("- O texto não utiliza listas (`<ul>` ou `<ol>`) para organizar a informação.")

    return {"score": score, "max_score": max_score, "feedback": feedback}

def check_authority_and_geo(soup: BeautifulSoup, product_name: str) -> dict:
    """
    Regra 4 (A mais importante): Verifica os sinais de Autoridade e GEO.
    """
    score = 0
    feedback = []
    max_score = 80 # Total de pontos para esta regra
    lower_content = soup.get_text().lower()

    # Data de Revisão e Nota de Transparência
    if "nota de transparência" in lower_content and "informações revisadas em" in lower_content:
        score += 20
    else:
        feedback.append("- Falta a 'Nota de Transparência' com data de revisão no topo do conteúdo.")

    # Citação Ativa da Fonte
    if "conforme a bula oficial aprovada pela anvisa" in lower_content:
        score += 20
    else:
        feedback.append("- Falta a citação ativa da fonte (ex: 'Conforme a bula oficial aprovada pela ANVISA...').")

    # Dados Verificáveis
    if "registro anvisa" in lower_content and "fabricante" in lower_content:
        score += 25
    else:
        if "registro anvisa" not in lower_content:
            feedback.append("- Faltam os Dados Verificáveis: 'Registro ANVISA' não encontrado.")
        if "fabricante" not in lower_content:
            feedback.append("- Faltam os Dados Verificáveis: 'Fabricante' não encontrado.")
    
    # Explicação de como funciona / Composição
    if "como funciona" in lower_content or "composição" in lower_content:
        score += 15
    else:
        feedback.append("- O texto não explica 'Como funciona' o produto ou sua 'Composição'.")

    return {"score": score, "max_score": max_score, "feedback": feedback}

def check_faq_section(soup: BeautifulSoup) -> dict:
    """
    Regra 5: Verifica a presença e estrutura da seção de FAQ.
    """
    score = 0
    feedback = []
    max_score = 15 # Total de pontos para esta regra

    faq_section = soup.find('div', class_='faq-section')
    if faq_section:
        details_tags = faq_section.find_all('details')
        if len(details_tags) >= 2:
            score += 15
        else:
            feedback.append(f"- A seção de FAQ tem apenas {len(details_tags)} pergunta(s) (mínimo: 2).")
    else:
        feedback.append("- O conteúdo não possui uma seção de FAQ (`<div class=\"faq-section\">...</div>`).")

    return {"score": score, "max_score": max_score, "feedback": feedback}


def analyze_seo_performance(html_content: str, product_name: str, product_info: dict) -> dict:
    """
    Função principal que orquestra todas as verificações de SEO e retorna um score
    total e um feedback detalhado e granular.
    """
    if not html_content or not isinstance(html_content, str):
        return {"total_score": 0, "breakdown": {"error": "Conteúdo inválido ou vazio."}}

    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Executa todas as novas funções de verificação
    title_results = check_title_and_meta(soup, product_name)
    structure_results = check_structure_and_readability(soup)
    authority_results = check_authority_and_geo(soup, product_name)
    faq_results = check_faq_section(soup)
    
    total_score = title_results['score'] + structure_results['score'] + authority_results['score'] + faq_results['score']
    
    # Combina todos os feedbacks em um único local para o refinador
    all_feedback = (title_results['feedback'] + 
                    structure_results['feedback'] + 
                    authority_results['feedback'] + 
                    faq_results['feedback'])

    breakdown = {
        "score_total": total_score,
        "feedback_detalhado": "\n".join(all_feedback) if all_feedback else "Nenhum ponto de melhoria encontrado."
    }
    
    return {"total_score": total_score, "breakdown": breakdown}