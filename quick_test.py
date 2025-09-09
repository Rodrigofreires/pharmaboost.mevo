import os
import io
import pandas as pd
import asyncio
import aiohttp
from pypdf import PdfReader, errors
from dotenv import load_dotenv
import time
import re

# Importa o caso de uso que utiliza nosso prompt aprimorado
from app.use_cases import run_bula_extraction_agent

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# --- Constantes e Caminhos dos Arquivos ---
CATALOGO_PATH = '/Users/rodrigofreiressoares/Documents/prompt_planilhas/dados_bula_extraidos/catalogo_produtos_bula_filtro_final_3500.xlsx'
OUTPUT_PATH = '/Users/rodrigofreiressoares/Documents/prompt_planilhas/dados_bula_extraidos/dados_estruturados_bula_final].xlsx'

# --- MUDANÇA CRÍTICA: Colunas finais ajustadas para refletir a fonte da verdade ---
COLUNAS_FINAIS = [
    'Número da Regularização (Registro MS)', # Virá do CODIGO_BARRAS
    'Nome Comercial',                      # Virá da coluna NOME
    'Princípio Ativo',
    'Apresentações',
    'Forma Farmacêutica',
    'Concentração',
    'Excipientes'
]

# --- AJUSTES DE ROBUSTEZ E TESTE ---
LIMITE_DE_ITENS_PARA_TESTE = 3500
MAX_CONCURRENCY = 10
MAX_RETRIES = 3

def clean_and_truncate_text(full_text: str) -> str:
    if not full_text:
        return ""
    
    text_normalized = re.sub(r'\s+', ' ', full_text).strip()
    end_markers = ["DIZERES LEGAIS", "MS –", "Reg. MS", "Farm. Resp."]
    
    end_index = -1
    # Procura pela última ocorrência dos marcadores para pegar o final da bula principal
    for marker in end_markers:
        found_pos = text_normalized.lower().rfind(marker.lower())
        if found_pos != -1:
            period_pos = text_normalized.find('.', found_pos)
            if period_pos != -1:
                current_end = period_pos + 1
                if current_end > end_index:
                    end_index = current_end
    
    if end_index != -1:
        print("  -> INFO: Múltiplas bulas detectadas. Processando apenas a primeira.")
        return text_normalized[:end_index]
    else:
        return text_normalized

async def get_bula_text_from_link_async(session: aiohttp.ClientSession, link_bula: str) -> str:
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(link_bula, headers=headers, timeout=120) as response:
                response.raise_for_status()
                content = await response.read()
                
                with io.BytesIO(content) as f:
                    reader = PdfReader(f)
                    if reader.is_encrypted:
                        print(f"  -> AVISO: PDF protegido por senha.")
                    
                    full_text = "".join(page.extract_text() for page in reader.pages if page.extract_text())
                    return clean_and_truncate_text(full_text)

        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            print(f"  -> AVISO: Tentativa {attempt + 1}/{MAX_RETRIES} falhou. Erro: {type(e).__name__}.")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(5)
            else:
                print(f"  -> ERRO: Todas as {MAX_RETRIES} tentativas de download falharam.")
                return ""
        except Exception as e:
            print(f"  -> ERRO inesperado ao processar PDF: {type(e).__name__} - {e}")
            return ""
    
    return ""

async def process_item(session: aiohttp.ClientSession, row_data, total_items: int):
    index, row = row_data
    item_num = index + 1
    # Captura os dados do catálogo que serão a fonte da verdade
    ean_catalogo = row.get('CODIGO_BARRAS', 'N/A')
    nome_catalogo = row.get('NOME', 'N/A')
    link_bula = row.get('BULA')
    
    print(f"\n[Iniciando {item_num}/{total_items}] SKU: {ean_catalogo}")

    if pd.isna(link_bula) or not str(link_bula).startswith('http'):
        print(f"  -> AVISO: Link da bula ausente ou inválido para SKU {ean_catalogo}. Pulando.")
        return None

    bula_text = await get_bula_text_from_link_async(session, str(link_bula))

    if not bula_text or not bula_text.strip():
        print(f"  -> FALHA: Conteúdo da bula não extraído para SKU {ean_catalogo}. Pulando.")
        return None

    dados_extraidos = await asyncio.to_thread(run_bula_extraction_agent, bula_text)

    if dados_extraidos:
        print(f"  -> SUCESSO: Dados extraídos para o SKU {ean_catalogo}.")
        # --- MUDANÇA CRÍTICA: O dicionário de resultados agora usa os dados do catálogo ---
        # para as colunas de identificação, como você solicitou.
        return {
            'Número da Regularização (Registro MS)': ean_catalogo, # Fonte: Sua coluna CODIGO_BARRAS
            'Nome Comercial': nome_catalogo,                      # Fonte: Sua coluna NOME
            'Princípio Ativo': dados_extraidos.get('principio_ativo', 'Não encontrado'),
            'Apresentações': dados_extraidos.get('apresentacoes', 'Não encontrado'),
            'Forma Farmacêutica': dados_extraidos.get('forma_farmaceutica', 'Não encontrado'),
            'Concentração': dados_extraidos.get('concentracao', 'Não encontrado'),
            'Excipientes': dados_extraidos.get('excipientes', 'Não encontrado'),
        }
    else:
        print(f"  -> FALHA: Agente de IA não retornou dados para o SKU {ean_catalogo}.")
        return None

async def main():
    """Função principal para orquestrar o processo de extração assíncrona."""
    print("--- Iniciando Processo de Extração Estruturada (v7 - TESTE COM VÍNCULO DE DADOS) ---")
    start_time = time.time()

    try:
        df_catalogo = pd.read_excel(CATALOGO_PATH)
    except FileNotFoundError:
        print(f"ERRO CRÍTICO: Arquivo de catálogo não encontrado em '{CATALOGO_PATH}'.")
        return
    
    df_validos = df_catalogo[df_catalogo['LINK_VALIDACAO'].astype(str).str.lower() == 'sim'].copy()
    if df_validos.empty:
        print("AVISO: Nenhum produto com 'LINK_VALIDACAO' = 'sim' encontrado.")
        return
        
    df_para_processar = df_validos.head(LIMITE_DE_ITENS_PARA_TESTE)
    total_items = len(df_para_processar)
    print(f"Encontrados {len(df_validos)} produtos válidos. Processando um limite de {total_items} para teste.")
    
    tasks = []
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def process_with_semaphore(session, row_data, total):
        async with sem:
            return await process_item(session, row_data, total)

    async with aiohttp.ClientSession() as session:
        for row_data in df_para_processar.iterrows():
            tasks.append(process_with_semaphore(session, row_data, total_items))
        
        resultados_brutos = await asyncio.gather(*tasks)

    resultados = [r for r in resultados_brutos if r is not None]

    if not resultados:
        print("\n--- Processo Finalizado: Nenhum dado foi extraído com sucesso. ---")
        return

    print(f"\n--- Processo Finalizado: {len(resultados)} de {total_items} itens processados com sucesso. ---")
    df_final = pd.DataFrame(resultados, columns=COLUNAS_FINAIS)

    try:
        df_final.to_excel(OUTPUT_PATH, index=False)
        print(f"Resultados salvos com sucesso em: '{OUTPUT_PATH}'")
    except Exception as e:
        print(f"ERRO CRÍTICO ao salvar a planilha de resultados: {e}")

    end_time = time.time()
    print(f"Tempo total de execução: {end_time - start_time:.2f} segundos.")

if __name__ == "__main__":
    asyncio.run(main())