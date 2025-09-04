# app/seo_analyzer.py (Atualizado para refletir as regras do Agente Auditor de IA)
import re
from bs4 import BeautifulSoup
from typing import Dict, Any

def check_headings_structure(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Verifica a hierarquia de títulos.
    REGRA: É proibido usar <h1>. A estrutura deve começar com <h2>.
    """
    score = 0
    feedback = []
    max_score = 10

    if soup.find('h1'):
        feedback.append("Hierarquia de headings incorreta: A tag <h1> é proibida no conteúdo.")
    elif not soup.find_all('h2'):
        feedback.append("Hierarquia de headings incorreta: A estrutura deve conter pelo menos uma tag <h2>.")
    else:
        score = 10
        feedback.append("Hierarquia de headings (começando com H2) está correta.")

    return {"score": score, "max_score": max_score, "feedback": feedback}

def check_readability(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Verifica a legibilidade através do uso de listas.
    """
    score = 0
    feedback = []
    max_score = 10

    if soup.find_all(['ul', 'ol']):
        score = 10
        feedback.append("Boa legibilidade, utilizando parágrafos curtos e listas (`<ul>`).")
    else:
        feedback.append("O texto não utiliza listas (`<ul>` ou `<ol>`) para organizar a informação.")

    return {"score": score, "max_score": max_score, "feedback": feedback}

def check_faq_structure(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Verifica a presença e estrutura da seção de FAQ.
    """
    score = 0
    feedback = []
    max_score = 10

    faq_section = soup.find('div', class_='faq-section')
    if faq_section and faq_section.find_all('details') and faq_section.find_all('summary'):
        score = 10
        feedback.append("A seção de FAQ utiliza `<details>` e `<summary>` conforme recomendado.")
    else:
        feedback.append("A seção de FAQ está ausente ou não utiliza as tags `<details>` e `<summary>`.")

    return {"score": score, "max_score": max_score, "feedback": feedback}

def check_authority_signals(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Verifica os sinais de Autoridade e Confiança (GEO, Dados, Links).
    """
    geo_score, verifiable_data_score, external_links_score = 0, 0, 0
    feedback = []
    lower_content = soup.get_text().lower()

    # GEO Signals
    if "nota de transparência" in lower_content and "anvisa" in lower_content:
        geo_score = 10
    else:
        feedback.append("Sinais de autoridade (Nota de Transparência e Citação ANVISA) ausentes.")

    # Verifiable Data
    if "registro anvisa" in lower_content and "fabricante" in lower_content:
        verifiable_data_score = 10
    else:
        feedback.append("Dados verificáveis (Registro ANVISA e Fabricante) não incluídos.")

    # External Links
    if soup.find('a', href=re.compile(r"gov\.br")):
        external_links_score = 10
    else:
        feedback.append("Link externo para fonte de autoridade (gov.br) não encontrado.")

    return {
        "geo_signals": {"score": geo_score, "max_score": 10},
        "verifiable_data": {"score": verifiable_data_score, "max_score": 10},
        "external_links": {"score": external_links_score, "max_score": 10},
        "feedback": feedback
    }

def analyze_seo_performance_from_html(html_content: str) -> Dict[str, Any]:
    """
    Função principal que orquestra todas as verificações de SEO baseadas no HTML.
    Esta é uma implementação em Python para fins de teste e validação,
    o sistema principal usa o Agente de IA.
    """
    if not html_content or not isinstance(html_content, str):
        return {"total_score": 0, "breakdown": {"error": "Conteúdo inválido ou vazio."}}

    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Executa todas as funções de verificação
    headings_results = check_headings_structure(soup)
    readability_results = check_readability(soup)
    faq_results = check_faq_structure(soup)
    authority_results = check_authority_signals(soup)
    
    # Consolida os resultados em um breakdown similar ao do Agente de IA
    breakdown = {
        "headings": headings_results,
        "readability": readability_results,
        "faq_structure": faq_results,
        "geo_signals": authority_results["geo_signals"],
        "verifiable_data": authority_results["verifiable_data"],
        "external_links": authority_results["external_links"],
    }

    # Calcula o score total
    total_score = sum(result.get("score", 0) for result in breakdown.values())

    # Combina todos os feedbacks
    all_feedback = (
        headings_results['feedback'] + 
        readability_results['feedback'] + 
        faq_results['feedback'] + 
        authority_results['feedback']
    )

    return {
        "total_score": total_score,
        "breakdown": breakdown,
        "feedback_geral": all_feedback
    }
