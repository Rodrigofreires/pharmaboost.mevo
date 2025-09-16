# api_automatizada.py (Versão 23.1 - Limpeza de Dados Pré-Merge)
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
from typing import List, Optional, Dict, Any
import base64

from app import use_cases

app = FastAPI(
    title="PharmaBoost Automation API",
    description="API para processamento com curadoria humana e feedback loop para IA.",
    version="23.1-merge-first-clean"
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Constantes ---
MAX_CONCURRENT_REQUESTS = 50 
COLUNA_EAN_SKU_ITENS = '_EANSKU'
COLUNA_CODIGO_BARRAS_CATALOGO = 'CODIGO_BARRAS'
COLUNA_NOME_PRODUTO = 'NOME'
COLUNA_LINK_BULA = 'BULA'
COLUNA_LINK_VALIDO = 'LINK_VALIDACAO'

# Mantido como no original para a escrita final do arquivo
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

# --- Funções Auxiliares ---
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
            return pd.read_csv(io.BytesIO(file_bytes), encoding='utf-8-sig', sep=',')
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
        resultados_finais = []
        summary = {'success': 0, 'skipped': 0, 'errors': 0}
        
        async def worker(row, total_items, semaphore, queue, counter, summary_dict):
            async with semaphore:
                ean_sku = str(row.get(COLUNA_EAN_SKU_ITENS.upper(), 'N/A'))
                nome_produto = str(row.get(COLUNA_NOME_PRODUTO.upper(), 'N/A'))

                try:
                    counter[0] += 1
                    await queue.put(await _send_event("progress", {"current": counter[0], "total": total_items, "sku": ean_sku}))

                    is_valid = str(row.get(COLUNA_LINK_VALIDO.upper(), '')).strip().lower() == 'sim'
                    link_bula = row.get(COLUNA_LINK_BULA.upper())
                    
                    if not is_valid:
                        await queue.put(await _send_event("log", {"message": f"<b>[SKU: {ean_sku}]</b> Item não validado (coluna '{COLUNA_LINK_VALIDO}' não é 'sim'). Pulando.", "type": "warning"}))
                        summary_dict['skipped'] += 1
                        return

                    if pd.isna(link_bula) or not str(link_bula).strip():
                        await queue.put(await _send_event("log", {"message": f"<b>[SKU: {ean_sku}]</b> Link da bula ausente. Pulando.", "type": "warning"}))
                        summary_dict['skipped'] += 1
                        return
                    
                    bula_text = await get_bula_text_from_link(ean_sku, link_bula)
                    if not bula_text.strip():
                        await queue.put(await _send_event("log", {"message": f"<b>[SKU: {ean_sku}]</b> Falha ao ler o PDF da bula. Pulando.", "type": "error"}))
                        summary_dict['errors'] += 1
                        return
                    
                    async for chunk in use_cases.run_seo_pipeline_stream("medicine", nome_produto, {"bula_text": bula_text}):
                        await queue.put(chunk)
                        if "event: done" in chunk:
                            final_data = json.loads(chunk.split('data: ')[1])
                            final_data[COLUNA_EAN_SKU_ITENS] = ean_sku 
                            resultados_finais.append(final_data)
                            summary_dict['success'] += 1

                except Exception as e:
                    summary_dict['errors'] += 1
                    await queue.put(await _send_event("log", {"message": f"<b>[SKU: {ean_sku}]</b> Erro inesperado no worker: {e}", "type": "error"}))
                finally:
                    await queue.put(None) 
        
        try:
            df_catalogo = read_spreadsheet(cat_bytes, cat_filename)
            df_processar = read_spreadsheet(it_bytes, it_filename)
            
            df_processar.columns = df_processar.columns.str.strip()
            df_catalogo.columns = df_catalogo.columns.str.strip()

            initial_count = len(df_processar)
            df_processar.dropna(subset=[COLUNA_EAN_SKU_ITENS], inplace=True)
            df_processar = df_processar[df_processar[COLUNA_EAN_SKU_ITENS].astype(str).str.strip() != '']
            final_count = len(df_processar)

            if initial_count > final_count:
                yield await _send_event("log", {"message": f"<b>AVISO:</b> {initial_count - final_count} linhas foram removidas da planilha de itens por não conterem um SKU válido.", "type": "warning"})

            df_processar[COLUNA_EAN_SKU_ITENS] = df_processar[COLUNA_EAN_SKU_ITENS].astype(str)
            df_catalogo[COLUNA_CODIGO_BARRAS_CATALOGO] = df_catalogo[COLUNA_CODIGO_BARRAS_CATALOGO].astype(str)
            
            df_merged = pd.merge(
                df_processar,
                df_catalogo,
                left_on=COLUNA_EAN_SKU_ITENS,
                right_on=COLUNA_CODIGO_BARRAS_CATALOGO,
                how="left"
            )
            
            df_merged.columns = df_merged.columns.str.upper()

            total_items = len(df_merged)
            yield await _send_event("log", {"message": f"Arquivos lidos e unificados. {total_items} itens para processar com até {MAX_CONCURRENT_REQUESTS} agentes em paralelo.", "type": "info"})

            queue = asyncio.Queue()
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
            processed_counter = [0]
            
            worker_tasks = [
                asyncio.create_task(worker(row, total_items, semaphore, queue, processed_counter, summary))
                for _, row in df_merged.iterrows()
            ]

            finished_workers = 0
            while finished_workers < total_items:
                item = await queue.get()
                if item is None:
                    finished_workers += 1
                else:
                    yield item
            
            await asyncio.gather(*worker_tasks)

            summary_message = f"<b>Processamento em lote finalizado.</b> Sumário: {summary['success']} com sucesso, {summary['skipped']} ignorados, {summary['errors']} com erro."
            yield await _send_event("log", {"message": summary_message, "type": "info"})
            
            if not resultados_finais:
                yield await _send_event("log", {"message": "<b>AVISO:</b> Nenhum produto foi processado com sucesso. O processo será finalizado sem gerar rascunho.", "type": "warning"})
                return

            yield await _send_event("log", {"message": "<b>Montando o rascunho para curadoria...</b>", "type": "info"})

            resultados_finais_dict = {
                str(res.get(COLUNA_EAN_SKU_ITENS)): {
                    '_TituloSite': res.get("seo_title", "Erro"),
                    '_DescricaoMetaTag': res.get("meta_description", "Erro"),
                    '_DescricaoProduto': res.get("final_content", "Erro")
                } for res in resultados_finais
            }
            
            df_itens_original = read_spreadsheet(it_bytes, it_filename)
            
            for sku, updates in resultados_finais_dict.items():
                mask = df_itens_original[COLUNA_EAN_SKU_ITENS].astype(str).str.strip() == str(sku).strip()
                for col, value in updates.items():
                    if col in df_itens_original.columns:
                        df_itens_original.loc[mask, col] = value
            
            output_buffer = io.BytesIO()
            df_itens_original.to_excel(output_buffer, index=False)
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
                        final_data['_EANSKU'] = ean_sku
                        final_data['_NomeProduto (Obrigatório)'] = product_name
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
    try:
        approved_data = json.loads(approved_data_json)
        if not approved_data:
            raise HTTPException(status_code=400, detail="Nenhum item aprovado foi enviado.")
        if not spreadsheet:
            raise HTTPException(status_code=400, detail="A planilha base é obrigatória para finalização.")
        df_updates = pd.DataFrame(approved_data)
        df_updates = df_updates.loc[:, ~df_updates.columns.duplicated()]
        df_updates.rename(columns={'sku': '_EANSKU', 'seoTitle': '_TituloSite', 'metaDescription': '_DescricaoMetaTag', 'htmlContent': '_DescricaoProduto'}, inplace=True)
        df_updates['_EANSKU'] = df_updates['_EANSKU'].apply(lambda x: str(x).split('.')[0].strip())
        df_updates = df_updates.drop_duplicates(subset=['_EANSKU'], keep='last')
        
        df_base = pd.read_excel(io.BytesIO(await spreadsheet.read()), engine='openpyxl')
        df_base = df_base.loc[:, ~df_base.columns.duplicated()]
        df_base['_EANSKU'] = df_base['_EANSKU'].apply(lambda x: str(x).split('.')[0].strip())
        df_base = df_base.drop_duplicates(subset=['_EANSKU'], keep='first')
        
        df_base_sem_conteudo = df_base.drop(columns=['_TituloSite', '_DescricaoMetaTag', '_DescricaoProduto'], errors='ignore')
        
        df_final = pd.merge(df_base_sem_conteudo, df_updates, on='_EANSKU', how="inner")
        
        for col in COLUNAS_MODELO_XLS:
            if col not in df_final.columns:
                df_final[col] = None
        df_final = df_final[COLUNAS_MODELO_XLS]
        
        output_buffer = io.BytesIO()
        with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
            df_final.to_excel(writer, index=False, sheet_name='Aprovados')
        return Response(content=output_buffer.getvalue(), media_type="application/vnd.openxmlformats-officedocument.sheet", headers={"Content-Disposition": "attachment; filename=planilha_aprovados.xlsx"})
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao finalizar planilha de aprovados: {str(e)}")

@app.post("/finalize-disapproved-spreadsheet")
async def finalize_disapproved_spreadsheet(spreadsheet: UploadFile = File(...), disapproved_data_json: str = Form(...)):
    try:
        df_original = pd.read_excel(io.BytesIO(await spreadsheet.read()), engine='openpyxl')
        df_original = df_original.loc[:, ~df_original.columns.duplicated()]
        disapproved_data = json.loads(disapproved_data_json)
        if not disapproved_data:
            raise HTTPException(status_code=400, detail="Nenhum item reprovado enviado.")
        disapproved_skus = [str(item['sku']).split('.')[0].strip() for item in disapproved_data]
        
        df_original['_EANSKU'] = df_original['_EANSKU'].apply(lambda x: str(x).split('.')[0].strip())
        
        df_disapproved = df_original[df_original['_EANSKU'].isin(disapproved_skus)].copy()
        
        output_buffer = io.BytesIO()
        with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
            df_disapproved.to_excel(writer, index=False, sheet_name='Reprovados')
        return Response(content=output_buffer.getvalue(), media_type="application/vnd.openxmlformats-officedocument.sheet", headers={"Content-Disposition": "attachment; filename=planilha_reprovados.xlsx"})
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
            bula_text_manual = await asyncio.to_thread(extract_text_from_pdf_bytes, b_bytes)
        df_catalogo = None
        if cat_bytes:
            df_catalogo = read_spreadsheet(cat_bytes, cat_filename)
            df_catalogo.columns = df_catalogo.columns.str.strip().str.upper()
            df_catalogo[COLUNA_CODIGO_BARRAS_CATALOGO] = df_catalogo[COLUNA_CODIGO_BARRAS_CATALOGO].astype(str)
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
                catalog_info_row = df_catalogo[df_catalogo[COLUNA_CODIGO_BARRAS_CATALOGO] == ean_sku]
                if catalog_info_row.empty:
                    yield await _send_event("log", {"message": f"<b>[SKU: {ean_sku}]</b> AVISO: SKU não encontrado no arquivo de catálogo. Pulando.", "type": "warning"})
                    continue
                link_bula = catalog_info_row.iloc[0].get(COLUNA_LINK_BULA.upper())
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
            async for chunk in use_cases.run_seo_pipeline_stream("medicine", nome_produto, {"bula_text": bula_text}, previous_content=previous_content, feedback_text=feedback):
                if "event: done" in chunk:
                    data = json.loads(chunk.split('data: ')[1])
                    data.update({COLUNA_EAN_SKU_ITENS: ean_sku, '_NomeProduto (Obrigatório)': nome_produto})
                    chunk = f"event: done\ndata: {json.dumps(data)}\n\n"
                yield chunk

    return StreamingResponse(event_stream(items_to_reprocess, catalog_bytes, bula_bytes, catalog_filename), media_type="text/event-stream")