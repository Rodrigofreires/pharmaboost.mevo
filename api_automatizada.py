# api_automatizada.py (Versão 20.6 - Modelo de Colunas e Duplicatas Corrigido)
import asyncio
import io
import json
import os
import traceback
import gdown
import pandas as pd
import openpyxl
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pypdf import PdfReader
from typing import List, Optional
import base64

from app import use_cases

app = FastAPI(
    title="PharmaBoost Automation API",
    description="API para processamento com curadoria humana e feedback loop para IA.",
    version="20.6-stable-finalization"
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Constantes e Funções Auxiliares ---
COLUNA_EAN_SKU = '_EANSKU'
COLUNA_NOME_PRODUTO = '_NomeProduto (Obrigatório)'
COLUNA_TITULO_SEO = '_TituloSite'
COLUNA_META_DESC = '_DescricaoMetaTag'
COLUNA_HTML = '_DescricaoProduto'
COLUNA_CODIGO_BARRAS = 'CODIGO_BARRAS'
COLUNA_LINK_BULA = 'BULA'
COLUNA_LINK_VALIDO = 'LINK_VALIDACAO'
CHUNK_SIZE = 500

# **CORREÇÃO: Lista de colunas atualizada exatamente como fornecido pelo usuário.**
COLUNAS_MODELO_XLS = [
    '_IDSKU (Não alterável)', '_NomeSKU', '_AtivarSKUSePossível', 
    '_SKUAtivo (Não alterável)', '_EANSKU', '_Altura', '_AlturaReal', 
    '_Largura', '_LarguraReal', '_Comprimento', '_ComprimentoReal', 
    '_Peso', '_PesoReal', '_UnidadeMedida', '_MultiplicadorUnidade', 
    '_CodigoReferenciaSKU', '_ValorFidelidade', '_DataPrevisaoChegada', 
    '_CodigoFabricante', '_IDProduto (Não alterável)', '_NomeProduto (Obrigatório)', 
    '_BreveDescricaoProduto', '_ProdutoAtivo (Não alterável)', 
    '_CodigoReferenciaProduto', '_MostrarNoSite', '_LinkTexto (Não alterável)', 
    '_DescricaoProduto', '_DataLancamentoProduto', '_PalavrasChave', 
    '_TituloSite', '_DescricaoMetaTag', '_IDFornecedor', 
    '_MostrarSemEstoque', '_Kit (Não alterável)', '_IDDepartamento (Não alterável)', 
    '_NomeDepartamento', '_IDCategoria', '_NomeCategoria', '_IDMarca', 
    '_Marca', '_PesoCubico', '_CondicaoComercial', '_Lojas', 
    '_Acessorios', '_Similares', '_Sugestoes', '_ShowTogether', '_Anexos'
]


async def _send_event(event_type: str, data: dict):
    await asyncio.sleep(0.01)
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return "".join(page.extract_text() for page in reader.pages if page.extract_text())
    except Exception:
        return ""

async def get_bula_text_from_link(ean_sku: str, link_bula: str) -> str:
    os.makedirs('bulas_temp', exist_ok=True)
    output_path = f"bulas_temp/{ean_sku}.pdf"
    try:
        if not os.path.exists(output_path):
            await asyncio.to_thread(gdown.download, str(link_bula), output_path, quiet=True, fuzzy=True)
        with open(output_path, 'rb') as f:
            return extract_text_from_pdf_bytes(f.read())
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)

def read_spreadsheet(file_bytes: bytes, filename: str) -> pd.DataFrame:
    try:
        if filename.lower().endswith('.csv'):
            return pd.read_csv(io.BytesIO(file_bytes))
        else:
            return pd.read_excel(io.BytesIO(file_bytes), engine='openpyxl')
    except Exception as e:
        raise ValueError(f"Não foi possível ler a planilha '{filename}'. Verifique o formato. Erro: {e}")

# --- Endpoints ---

@app.post("/batch-process-and-generate-draft")
async def batch_process_stream(catalog_file: UploadFile = File(...), items_file: UploadFile = File(...)):
    
    try:
        catalog_bytes = await catalog_file.read()
        items_bytes = await items_file.read()
        catalog_filename = catalog_file.filename
        items_filename = items_file.filename
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler os arquivos enviados: {e}")

    async def event_stream(cat_bytes, it_bytes, cat_filename, it_filename):
        resultados_finais_dict = {}
        try:
            df_catalogo = read_spreadsheet(cat_bytes, cat_filename)
            df_processar_full = read_spreadsheet(it_bytes, it_filename)
            
            df_catalogo.columns = df_catalogo.columns.str.strip()
            if COLUNA_CODIGO_BARRAS not in df_catalogo.columns:
                raise ValueError(f"A coluna '{COLUNA_CODIGO_BARRAS}' não foi encontrada no arquivo de catálogo.")
            df_catalogo[COLUNA_CODIGO_BARRAS] = df_catalogo[COLUNA_CODIGO_BARRAS].astype(str)
            
            total_items = len(df_processar_full)
            processed_items_count = 0
            yield await _send_event("log", {"message": f"Arquivos lidos. {total_items} itens para processar.", "type": "info"})

            for i in range(0, total_items, CHUNK_SIZE):
                df_processar_chunk = df_processar_full.iloc[i:i + CHUNK_SIZE].copy()
                df_processar_chunk[COLUNA_EAN_SKU] = df_processar_chunk[COLUNA_EAN_SKU].astype(str)
                
                df_merged = pd.merge(df_processar_chunk, df_catalogo, left_on=COLUNA_EAN_SKU, right_on=COLUNA_CODIGO_BARRAS, how='left')

                for index, row in df_merged.iterrows():
                    processed_items_count += 1
                    ean_sku = str(row.get(COLUNA_EAN_SKU, 'N/A'))
                    
                    yield await _send_event("progress", {"current": processed_items_count, "total": total_items, "sku": ean_sku})

                    is_valid = str(row.get(COLUNA_LINK_VALIDO, '')).strip().lower() == 'sim'
                    if not is_valid:
                        continue
                    
                    nome_produto = row.get(COLUNA_NOME_PRODUTO)
                    link_bula = row.get(COLUNA_LINK_BULA)

                    if pd.isna(link_bula) or not str(link_bula).strip():
                        yield await _send_event("log", {"message": f"<b>[SKU: {ean_sku}]</b> Link da bula ausente. Pulando.", "type": "warning"})
                        continue
                    
                    bula_text = await get_bula_text_from_link(ean_sku, link_bula)
                    if not bula_text.strip():
                        yield await _send_event("log", {"message": f"<b>[SKU: {ean_sku}]</b> Falha ao ler o PDF da bula. Pulando.", "type": "error"})
                        continue

                    async for chunk in use_cases.run_seo_pipeline_stream("medicine", nome_produto, {"bula_text": bula_text}):
                        yield chunk
                        if "event: done" in chunk:
                            final_data = json.loads(chunk.split('data: ')[1])
                            resultados_finais_dict[ean_sku] = {
                                COLUNA_TITULO_SEO: final_data.get("seo_title", "Erro"),
                                COLUNA_META_DESC: final_data.get("meta_description", "Erro"),
                                COLUNA_HTML: final_data.get("final_content", "Erro")
                            }
                    await asyncio.sleep(1)

            if not resultados_finais_dict:
                yield await _send_event("log", {"message": "<b>AVISO:</b> Nenhum produto válido foi processado com sucesso. O processo será finalizado.", "type": "warning"})
                return

            yield await _send_event("log", {"message": "<b>Montando o rascunho para curadoria...</b>", "type": "info"})
            
            workbook = openpyxl.load_workbook(io.BytesIO(it_bytes))
            sheet = workbook.active

            header = [cell.value for cell in sheet[1]]
            try:
                sku_col_idx = header.index(COLUNA_EAN_SKU)
                title_col_idx = header.index(COLUNA_TITULO_SEO)
                meta_col_idx = header.index(COLUNA_META_DESC)
                html_col_idx = header.index(COLUNA_HTML)
            except ValueError as e:
                raise ValueError(f"Coluna obrigatória não encontrada na planilha: {e}")

            for row_idx, row in enumerate(sheet.iter_rows(min_row=2), start=2):
                sku_da_linha = str(row[sku_col_idx].value)
                
                if sku_da_linha in resultados_finais_dict:
                    updates = resultados_finais_dict[sku_da_linha]
                    sheet.cell(row=row_idx, column=title_col_idx + 1).value = updates[COLUNA_TITULO_SEO]
                    sheet.cell(row=row_idx, column=meta_col_idx + 1).value = updates[COLUNA_META_DESC]
                    sheet.cell(row=row_idx, column=html_col_idx + 1).value = updates[COLUNA_HTML]

            output_buffer = io.BytesIO()
            workbook.save(output_buffer)
            
            file_data_b64 = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
            yield await _send_event("finished", {"filename": "rascunho_para_revisao.xlsx", "file_data": file_data_b64})

        except Exception as e:
            traceback.print_exc()
            error_message = f"Erro fatal durante o processamento em lote: {e}"
            yield await _send_event("log", {"message": error_message, "type": "error"})
    
    return StreamingResponse(event_stream(catalog_bytes, items_bytes, catalog_filename, items_filename), media_type="text/event-stream")

@app.post("/process-manual-single")
async def process_manual_single_stream(product_name: str = Form(...), ean_sku: str = Form(...), bula_file: UploadFile = File(...)):
    try:
        pdf_bytes = await bula_file.read()
    except Exception as e:
        async def error_stream():
            yield await _send_event("log", {"message": f"Erro fatal ao ler o arquivo: {e}", "type": "error"})
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    async def event_stream(bytes_to_process: bytes):
        try:
            bula_text = await asyncio.to_thread(extract_text_from_pdf_bytes, bytes_to_process)
            if not bula_text.strip():
                yield await _send_event("log", {"message": "<b>Erro Crítico:</b> Não foi possível extrair texto do PDF.", "type": "error"})
                return

            yield await _send_event("log", {"message": f"PDF da bula lido com sucesso.", "type": "success"})

            async for chunk in use_cases.run_seo_pipeline_stream("medicine", product_name, {"bula_text": bula_text}):
                if "event: done" in chunk:
                    try:
                        final_data = json.loads(chunk.split('data: ')[1])
                        final_data[COLUNA_EAN_SKU] = ean_sku
                        final_data[COLUNA_NOME_PRODUTO] = product_name
                        yield await _send_event("done_manual", final_data)
                    except Exception as e:
                         yield await _send_event("log", {"message": f"Erro ao reempacotar dados: {e}", "type": "error"})
                else:
                    yield chunk

        except Exception as e:
            traceback.print_exc()
            yield await _send_event("log", {"message": f"ERRO FATAL (Manual): {e}", "type": "error"})

    return StreamingResponse(event_stream(pdf_bytes), media_type="text/event-stream")

@app.post("/finalize-spreadsheet")
async def finalize_spreadsheet(approved_data_json: str = Form(...), spreadsheet: Optional[UploadFile] = File(None)):
    """
    Recebe os dados aprovados e a planilha base, aplica as alterações e retorna o arquivo Excel finalizado.
    Esta versão foi reescrita para ser mais robusta, usando um método de merge para garantir a consistência dos dados.
    """
    try:
        approved_data = json.loads(approved_data_json)
        if not approved_data:
            raise HTTPException(status_code=400, detail="Nenhum item aprovado foi enviado.")

        if not spreadsheet:
            raise HTTPException(status_code=400, detail="A planilha base é obrigatória para finalização.")

        # --- Etapa 1: Preparar os Dados Aprovados ---
        df_updates = pd.DataFrame(approved_data)
        df_updates = df_updates.loc[:, ~df_updates.columns.duplicated()]
        
        df_updates.rename(columns={
            'sku': COLUNA_EAN_SKU,
            'seoTitle': COLUNA_TITULO_SEO,
            'metaDescription': COLUNA_META_DESC,
            'htmlContent': COLUNA_HTML
        }, inplace=True)
        
        df_updates[COLUNA_EAN_SKU] = df_updates[COLUNA_EAN_SKU].apply(lambda x: str(x).split('.')[0].strip())
        df_updates = df_updates.drop_duplicates(subset=[COLUNA_EAN_SKU], keep='last')
        
        update_columns = [COLUNA_EAN_SKU, COLUNA_TITULO_SEO, COLUNA_META_DESC, COLUNA_HTML]
        df_updates = df_updates[update_columns]

        # --- Etapa 2: Preparar a Planilha Base ---
        df_base = pd.read_excel(io.BytesIO(await spreadsheet.read()), engine='openpyxl')
        df_base = df_base.loc[:, ~df_base.columns.duplicated()]
        
        df_base[COLUNA_EAN_SKU] = df_base[COLUNA_EAN_SKU].apply(lambda x: str(x).split('.')[0].strip())
        df_base = df_base.drop_duplicates(subset=[COLUNA_EAN_SKU], keep='first')

        # --- Etapa 3: Fazer a Fusão (Merge) dos Dados ---
        df_base_sem_conteudo = df_base.drop(columns=[COLUNA_TITULO_SEO, COLUNA_META_DESC, COLUNA_HTML], errors='ignore')
        df_final = pd.merge(df_base_sem_conteudo, df_updates, on=COLUNA_EAN_SKU, how="inner")

        # --- Etapa 4: Garantir o Modelo de Colunas e Exportar ---
        for col in COLUNAS_MODELO_XLS:
            if col not in df_final.columns:
                df_final[col] = None
        
        df_final = df_final[COLUNAS_MODELO_XLS]

        output_buffer = io.BytesIO()
        with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
            df_final.to_excel(writer, index=False, sheet_name='Aprovados')

        return Response(
            content=output_buffer.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.sheet",
            headers={"Content-Disposition": "attachment; filename=planilha_aprovados.xlsx"}
        )

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao finalizar planilha de aprovados: {str(e)}")

@app.post("/finalize-disapproved-spreadsheet")
async def finalize_disapproved_spreadsheet(spreadsheet: UploadFile = File(...), disapproved_data_json: str = Form(...)):
    """
    Gera uma planilha contendo apenas as linhas dos produtos que foram reprovados.
    Versão corrigida para garantir a correspondência correta dos SKUs.
    """
    try:
        df_original = pd.read_excel(io.BytesIO(await spreadsheet.read()), engine='openpyxl')
        df_original = df_original.loc[:, ~df_original.columns.duplicated()]

        disapproved_data = json.loads(disapproved_data_json)
        if not disapproved_data:
            raise HTTPException(status_code=400, detail="Nenhum item reprovado enviado.")

        disapproved_skus = [str(item['sku']).split('.')[0].strip() for item in disapproved_data]
        
        df_original[COLUNA_EAN_SKU] = df_original[COLUNA_EAN_SKU].apply(lambda x: str(x).split('.')[0].strip())
        
        df_disapproved = df_original[df_original[COLUNA_EAN_SKU].isin(disapproved_skus)].copy()

        output_buffer = io.BytesIO()
        with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
            df_disapproved.to_excel(writer, index=False, sheet_name='Reprovados')
        
        return Response(
            content=output_buffer.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.sheet",
            headers={"Content-Disposition": "attachment; filename=planilha_reprovados.xlsx"}
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao gerar planilha de reprovados: {str(e)}")


@app.post("/reprocess-items")
async def reprocess_items(
    items_to_reprocess_json: str = Form(...),
    catalog_file: Optional[UploadFile] = File(None),
    bula_file: Optional[UploadFile] = File(None)
):
    try:
        items_to_reprocess = json.loads(items_to_reprocess_json)
        catalog_bytes = await catalog_file.read() if catalog_file else None
        bula_bytes = await bula_file.read() if bula_file else None
        catalog_filename = catalog_file.filename if catalog_file else None
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler os arquivos ou dados: {e}")

    async def event_stream(it_to_reprocess, cat_bytes, b_bytes, cat_filename):
        bula_text_manual = ""
        if b_bytes:
            bula_text_manual = await asyncio.to_thread(
                extract_text_from_pdf_bytes, b_bytes
            )

        df_catalogo = None
        if cat_bytes:
            df_catalogo = read_spreadsheet(cat_bytes, cat_filename)
            df_catalogo.columns = df_catalogo.columns.str.strip()
            df_catalogo[COLUNA_CODIGO_BARRAS] = df_catalogo[COLUNA_CODIGO_BARRAS].astype(str)

        for item in it_to_reprocess:
            ean_sku = str(item.get("sku"))
            nome_produto = item.get("productName")
            feedback = item.get("feedback")
            previous_content = item.get("rawJsonContent")
            bula_text = ""
            source_found = False

            if bula_text_manual:
                bula_text = bula_text_manual
                source_found = True
                yield await _send_event("log", {"message": f"<b>[SKU: {ean_sku}]</b> Usando bula enviada manualmente para reprocessar.", "type": "info"})
            
            elif df_catalogo is not None:
                catalog_info_row = df_catalogo[df_catalogo[COLUNA_CODIGO_BARRAS] == ean_sku]
                if catalog_info_row.empty:
                    yield await _send_event("log", {"message": f"<b>[SKU: {ean_sku}]</b> AVISO: SKU não encontrado no arquivo de catálogo. Pulando.", "type": "warning"})
                    continue
                
                link_bula = catalog_info_row.iloc[0].get(COLUNA_LINK_BULA)
                if pd.isna(link_bula) or not str(link_bula).strip():
                    yield await _send_event("log", {"message": f"<b>[SKU: {ean_sku}]</b> AVISO: Link da bula não encontrado no catálogo para este SKU. Pulando.", "type": "warning"})
                    continue
                
                yield await _send_event("log", {"message": f"<b>[SKU: {ean_sku}]</b> Buscando bula no catálogo para reprocessar...", "type": "info"})
                bula_text = await get_bula_text_from_link(ean_sku, link_bula)
                if bula_text.strip():
                    source_found = True
                else:
                    yield await _send_event("log", {"message": f"<b>[SKU: {ean_sku}]</b> ERRO: Falha ao extrair texto do PDF do link da bula. Pulando.", "type": "error"})
                    continue
            
            if not source_found:
                 yield await _send_event("log", {"message": f"<b>[SKU: {ean_sku}]</b> ERRO: Nenhuma fonte de bula (arquivo ou catálogo) fornecida ou válida para reprocessamento. Pulando.", "type": "error"})
                 continue

            yield await _send_event("log", {"message": f"<b>[SKU: {ean_sku}]</b> Fonte da bula encontrada. Acionando pipeline da IA...", "type": "info"})
            
            async for chunk in use_cases.run_seo_pipeline_stream(
                "medicine", 
                nome_produto, 
                {"bula_text": bula_text},
                previous_content=previous_content,
                feedback_text=feedback
            ):
                if "event: done" in chunk:
                    data = json.loads(chunk.split('data: ')[1])
                    data.update({COLUNA_EAN_SKU: ean_sku, COLUNA_NOME_PRODUTO: nome_produto})
                    chunk = f"event: done\ndata: {json.dumps(data)}\n\n"
                yield chunk

    return StreamingResponse(event_stream(items_to_reprocess, catalog_bytes, bula_bytes, catalog_filename), media_type="text/event-stream")