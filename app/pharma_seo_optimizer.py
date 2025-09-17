# app/pharma_seo_optimizer.py (Versão Final - Sem Estilos Injetados)

import re
from bs4 import BeautifulSoup

class SeoOptimizerAgent:
    """
    Classe de utilidades para o processo de otimização, incluindo a finalização para V-TEX.
    """

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
    def _enrich_faq_structure(soup: BeautifulSoup) -> BeautifulSoup:
        """
        Encontra a seção de FAQ e envolve as perguntas (h3) e respostas (p)
        em tags <details open> e <summary> para criar um accordion aberto por padrão.
        """
        faq_h2 = soup.find('h2', string=re.compile(r'Perguntas Frequentes', re.IGNORECASE))
        if not faq_h2:
            return soup

        for element in faq_h2.find_next_siblings():
            if element.name == 'h2' or element.name == 'div':
                break
            
            if element.name == 'h3':
                p_tag = element.find_next_sibling('p')
                if p_tag:
                    details_tag = soup.new_tag('details')
                    details_tag['open'] = True
                    summary_tag = soup.new_tag('summary')
                    
                    summary_tag.append(element.extract()) 
                    
                    details_tag.append(summary_tag)
                    details_tag.append(p_tag.extract())
                    
                    faq_h2.insert_after(details_tag)
        
        return soup

    @staticmethod
    def _finalize_for_vtex(html_content: str, product_name: str) -> str:
        """
        Garante que o HTML final seja um fragmento único para a V-TEX, 
        sem estilos, mas com a estrutura de classes correta.
        """
        if not isinstance(html_content, str):
            return ""

        clean_html = SeoOptimizerAgent._clean_and_correct_html(html_content)
        
        clean_html = re.sub(r'<!DOCTYPE[^>]*>', '', clean_html, re.IGNORECASE)

        soup = BeautifulSoup(clean_html, 'html.parser')

        for tag in soup.find_all(['html', 'body', 'head']):
            tag.unwrap()

        soup = SeoOptimizerAgent._enrich_faq_structure(soup)

        content_string = "".join(str(c) for c in soup.contents)

        # O HTML agora é envolvido apenas na div principal, sem o <style>.
        # As outras classes, como 'legal-notice-box', são geradas pelo prompt da IA.
        final_html = f'''<div class="descricao-produto">
{content_string.strip()}
</div>'''

        return final_html