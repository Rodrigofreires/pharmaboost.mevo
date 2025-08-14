# seo_analyzer.py
import re
from bs4 import BeautifulSoup

# --- Módulo de Análise de SEO para Conteúdo Farmacêutico ---
# Este módulo traduz o checklist de copywriting para funções que avaliam
# o conteúdo HTML gerado pela IA.

def check_title_and_meta(soup: BeautifulSoup, product_name: str) -> dict:
    """
    Verifica o Título H1 e simula a análise de uma meta descrição.
    """
    score = 0
    feedback = []
    
    h1_tag = soup.find('h1')
    if h1_tag:
        h1_text = h1_tag.get_text(strip=True).lower()
        # 1.1. Palavra-chave (nome do produto) no título
        if product_name.lower() in h1_text:
            score += 15
        else:
            feedback.append("O H1 não contém o nome exato do produto.")
            
        # 1.2. Tamanho do título
        if len(h1_text) < 60:
            score += 5
        else:
            feedback.append("O H1 é muito longo, pode ser cortado no Google.")
    else:
        feedback.append("Conteúdo não possui uma tag H1 principal.")
        score = 0

    # Simula meta descrição a partir do primeiro parágrafo
    first_p = soup.find('p')
    if first_p:
        meta_desc = first_p.get_text(strip=True)
        # 1.3. Tamanho da meta descrição
        if 120 < len(meta_desc) < 160:
            score += 10
        else:
            feedback.append("O primeiro parágrafo (usado como meta descrição) está fora do tamanho ideal (120-160 caracteres).")
    
    return {"score": score, "max_score": 30, "feedback": feedback}

def check_body_structure_and_semantics(soup: BeautifulSoup, product_info: dict) -> dict:
    """
    Verifica a estrutura de cabeçalhos (H2, H3) e a cobertura do tópico.
    """
    score = 0
    feedback = []
    
    # 2.1. Estrutura de Cabeçalhos
    h2_tags = soup.find_all('h2')
    if len(h2_tags) > 1:
        score += 15
    else:
        feedback.append("O texto usa poucos subtítulos (H2), dificultando a escaneabilidade.")
        
    # 2.2. Cobertura Holística do Tópico (semântica)
    # Verifica se os pontos-chave do product_info foram mencionados
    lower_content = soup.get_text().lower()
    info_covered = 0
    for key, value in product_info.items():
        if isinstance(value, list):
            if any(item.lower() in lower_content for item in value):
                info_covered += 1
        elif isinstance(value, str):
            # Procura por palavras-chave do valor no texto
            keywords = value.lower().split()
            if any(keyword in lower_content for keyword in keywords):
                info_covered += 1
    
    coverage_ratio = info_covered / len(product_info) if product_info else 0
    if coverage_ratio > 0.7:
        score += 20
    elif coverage_ratio > 0.4:
        score += 10
    else:
        feedback.append("O conteúdo não cobre todos os pontos importantes fornecidos no 'product_info'.")

    # 2.3. Legibilidade (parágrafos curtos)
    paragraphs = [p.get_text() for p in soup.find_all('p')]
    long_paragraphs = [p for p in paragraphs if len(p.split()) > 100]
    if not long_paragraphs:
        score += 5
    else:
        feedback.append(f"{len(long_paragraphs)} parágrafos são muito longos, prejudicando a leitura.")
        
    return {"score": score, "max_score": 40, "feedback": feedback}

def check_eeat_and_trust(soup: BeautifulSoup) -> dict:
    """
    Verifica sinais de Experiência, Especialidade, Autoridade e Confiança (E-E-A-T).
    """
    score = 0
    feedback = []
    lower_content = soup.get_text().lower()
    
    # 3.1. Transparência e Confiança (simulado)
    # Procura por termos que indicam responsabilidade e fontes
    if "consulte um médico" in lower_content or "leia a bula" in lower_content:
        score += 15
    else:
        feedback.append("Faltam avisos de confiança importantes (ex: 'consulte um médico').")
        
    # 3.2. Demonstração de Experiência (simulado)
    # Procura por seções que aprofundam o conhecimento
    if "como funciona" in lower_content or "tecnologia por trás" in lower_content:
        score += 15
    else:
        feedback.append("O texto não aprofunda em 'como o produto funciona', o que demonstra menos especialidade.")
        
    return {"score": score, "max_score": 30, "feedback": feedback}


def analyze_seo_performance(html_content: str, product_name: str, product_info: dict) -> dict:
    """
    Função principal que orquestra todas as verificações de SEO e retorna um score
    total e um feedback detalhado.
    """
    if not html_content or not isinstance(html_content, str):
        return {"total_score": 0, "breakdown": {"error": "Conteúdo inválido ou vazio."}}

    soup = BeautifulSoup(html_content, 'html.parser')
    
    title_results = check_title_and_meta(soup, product_name)
    structure_results = check_body_structure_and_semantics(soup, product_info)
    eeat_results = check_eeat_and_trust(soup)
    
    total_score = title_results['score'] + structure_results['score'] + eeat_results['score']
    
    breakdown = {
        "Título e Meta Descrição": title_results,
        "Estrutura e Semântica": structure_results,
        "Confiança (E-E-A-T)": eeat_results
    }
    
    return {"total_score": total_score, "breakdown": breakdown}

