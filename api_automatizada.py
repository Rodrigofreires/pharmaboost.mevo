# api_automatizada.py (Versão 17.4 - Logs de Reprocessamento Detalhados)
import asyncio
import io
import json
import os
import traceback
import gdown
import pandas as pd
import base64
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pypdf import PdfReader
from typing import List, Optional

from app import use_cases

app = FastAPI(
    title="PharmaBoost Automation API",
    description="API para processamento com curadoria humana e feedback loop para IA.",
    version="17.4-reprocessing-logs"
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Constantes ---
COLUNA_EAN_SKU = '_EANSKU'
COLUNA_NOME_PRODUTO = '_NomeProduto (Obrigatório)'
COLUNA_TITULO_SEO = '_TituloSite'
COLUNA_META_DESC = '_DescricaoMetaTag'
COLUNA_HTML = '_DescricaoProduto'
COLUNA_CODIGO_BARRAS = 'CODIGO_BARRAS'
COLUNA_LINK_BULA = 'BULA'
COLUNA_LINK_VALIDO = 'LINK_VALIDACAO'
CHUNK_SIZE = 500
COLUNAS_MODELO_XLS = [
    '_IDSKU (Não alterável)', '_NomeSKU', '_AtivarSKUSePossível',
    '_SKUAtivo (Não alterável)', '_EANSKU', '_Altura', '_AlturaReal',
    '_Largura', '_LarguraReal', '_Comprimento', '_ComprimentoReal',
    '_Peso', '_PesoReal', '_UnidadeMedida', '_MultiplicadorUnidade',
    '_CodigoReferenciaSKU', '_ValorFidelidade', '_DataPrevisaoChegada',
    '_CodigoFabricante', '_IDProduto', '_NomeProduto', '_BreveDescricaoProduto',
    '_ProdutoAtivo', '_CodigoReferenciaProduto', '_MostrarNoSite',
    '_LinkTexto (Não alterável)', '_DescricaoProduto', '_DataLancamentoProduto',
    '_PalavrasChave', '_TituloSite', '_DescricaoMetaTag', '_IDFornecedor',
    '_MostrarSemEstoque', '_Kit (Não alterável)', '_IDDepartamento',
    '_NomeDepartamento', '_IDCategoria', '_NomeCategoria', '_IDMarca',
    '_Marca', '_PesoCubico', '_CondicaoComercial', '_Lojas', '_Acessorios',
    '_Similares', '_Sugestoes', '_ShowTogether', '_Anexos'
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
            return pd.read_csv(io.BytesIO(file_bytes))
        else:
            return pd.read_excel(io.BytesIO(file_bytes), engine='openpyxl')
    except Exception as e:
        raise ValueError(f"Não foi possível ler a planilha '{filename}'. Verifique o formato. Erro: {e}")

# --- Endpoints ---

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


@app.post("/batch-process-and-generate-draft")
async def batch_process_stream(catalog_file: UploadFile = File(...), items_file: UploadFile = File(...)):
    try:
        catalog_bytes = await catalog_file.read()
        items_bytes = await items_file.read()
        catalog_filename = catalog_file.filename
        items_filename = items_file.filename
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler os arquivos: {e}")

    async def event_stream(cat_bytes, it_bytes, cat_filename, it_filename):
        try:
            df_catalogo = read_spreadsheet(cat_bytes, cat_filename)
            df_processar_full = read_spreadsheet(it_bytes, it_filename)
            df_catalogo.columns = df_catalogo.columns.str.strip()
            if COLUNA_CODIGO_BARRAS not in df_catalogo.columns:
                raise ValueError(f"A coluna '{COLUNA_CODIGO_BARRAS}' não foi encontrada no arquivo de catálogo.")
            df_catalogo[COLUNA_CODIGO_BARRAS] = df_catalogo[COLUNA_CODIGO_BARRAS].astype(str)
            total_items = len(df_processar_full)
            yield await _send_event("log", {"message": f"Planilhas carregadas. Total de {total_items} itens para verificar.", "type": "info", "total_items": total_items})
            
            resultados_finais = []
            processed_items_count = 0

            for i in range(0, total_items, CHUNK_SIZE):
                df_processar_chunk = df_processar_full.iloc[i:i + CHUNK_SIZE]
                processed_count_in_chunk = min(i + CHUNK_SIZE, total_items)
                df_processar_chunk.columns = df_processar_chunk.columns.str.strip()
                df_processar_chunk[COLUNA_EAN_SKU] = df_processar_chunk[COLUNA_EAN_SKU].astype(str)
                df_merged = pd.merge(df_processar_chunk, df_catalogo, left_on=COLUNA_EAN_SKU, right_on=COLUNA_CODIGO_BARRAS, how='left')
                df_validos = df_merged[df_merged[COLUNA_LINK_VALIDO].astype(str).str.strip().str.lower() == 'sim'].copy()

                if df_validos.empty:
                    yield await _send_event("log", {"message": f"Lote {i+1}-{processed_count_in_chunk}: Nenhum item validado encontrado.", "type": "info"})
                    continue

                yield await _send_event("log", {"message": f"Processando lote de {len(df_validos)} itens válidos (Total verificado: {processed_count_in_chunk}/{total_items})...", "type": "success"})

                for index, row in df_validos.iterrows():
                    processed_items_count += 1
                    ean_sku = str(row.get(COLUNA_EAN_SKU))
                    nome_produto = row.get(COLUNA_NOME_PRODUTO)
                    link_bula = row.get(COLUNA_LINK_BULA)
                    
                    yield await _send_event("progress", {"current": processed_items_count, "total": total_items, "sku": ean_sku})

                    if pd.isna(link_bula) or not str(link_bula).strip():
                        yield await _send_event("log", {"message": f"<b>[SKU: {ean_sku}]</b> Link da bula ausente. Pulando.", "type": "warning"})
                        continue
                    bula_text = await get_bula_text_from_link(ean_sku, link_bula)
                    if not bula_text.strip():
                        yield await _send_event("log", {"message": f"<b>[SKU: {ean_sku}]</b> Falha ao ler o PDF da bula. Pulando.", "type": "error"})
                        continue

                    async for chunk in use_cases.run_seo_pipeline_stream("medicine", nome_produto, {"bula_text": bula_text}):
                        if "event: done" in chunk:
                            final_data = json.loads(chunk.split('data: ')[1])
                            final_data[COLUNA_EAN_SKU] = ean_sku
                            final_data[COLUNA_NOME_PRODUTO] = nome_produto
                            
                            resultados_finais.append({
                                COLUNA_EAN_SKU: ean_sku,
                                COLUNA_TITULO_SEO: final_data.get("seo_title", "Erro"),
                                COLUNA_META_DESC: final_data.get("meta_description", "Erro"),
                                COLUNA_HTML: final_data.get("final_content", "Erro")
                            })
                            yield await _send_event("done", final_data)
                        else:
                            yield chunk
                    
                    await asyncio.sleep(2)

            if resultados_finais:
                df_resultados = pd.DataFrame(resultados_finais)
                df_processar_full.set_index(COLUNA_EAN_SKU, inplace=True)
                df_resultados.set_index(COLUNA_EAN_SKU, inplace=True)
                df_processar_full.update(df_resultados)
                df_processar_full.reset_index(inplace=True)
                output_buffer = io.BytesIO()
                with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
                    df_processar_full.to_excel(writer, index=False, sheet_name='Rascunho_IA')
                file_data_b64 = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
                yield await _send_event("finished", {"filename": "rascunho_para_revisao.xlsx", "file_data": file_data_b64})
            else:
                 yield await _send_event("log", {"message": "<b>AVISO:</b> Nenhum produto válido foi processado com sucesso.", "type": "warning"})
        except Exception as e:
            traceback.print_exc()
            yield await _send_event("log", {"message": f"ERRO FATAL (Lote): {e}", "type": "error"})

    return StreamingResponse(event_stream(catalog_bytes, items_bytes, catalog_filename, items_filename), media_type="text/event-stream")


@app.post("/finalize-spreadsheet")
async def finalize_spreadsheet(approved_data_json: str = Form(...), spreadsheet: Optional[UploadFile] = File(None)):
    try:
        approved_data = json.loads(approved_data_json)
        if not approved_data:
            raise HTTPException(status_code=400, detail="Nenhum item aprovado foi enviado.")
        
        df_approved = pd.DataFrame(approved_data)
        df_approved[COLUNA_EAN_SKU] = df_approved[COLUNA_EAN_SKU].astype(str)

        if not spreadsheet:
             raise HTTPException(status_code=400, detail="A planilha base é obrigatória para finalização.")

        df_base = pd.read_excel(io.BytesIO(await spreadsheet.read()), engine='openpyxl')
        df_base[COLUNA_EAN_SKU] = df_base[COLUNA_EAN_SKU].astype(str)
        
        df_base.set_index(COLUNA_EAN_SKU, inplace=True)
        df_approved.rename(columns={
            'seoTitle': COLUNA_TITULO_SEO,
            'metaDescription': COLUNA_META_DESC,
            'htmlContent': COLUNA_HTML,
            'sku': COLUNA_EAN_SKU
        }, inplace=True)
        df_approved_for_update = df_approved[[COLUNA_EAN_SKU, COLUNA_TITULO_SEO, COLUNA_META_DESC, COLUNA_HTML]].set_index(COLUNA_EAN_SKU)
        df_base.update(df_approved_for_update)
        df_base.reset_index(inplace=True)
        
        for col in COLUNAS_MODELO_XLS:
            if col not in df_base.columns:
                df_base[col] = None

        df_export = df_base[COLUNAS_MODELO_XLS]

        output_buffer = io.BytesIO()
        with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False, sheet_name='Aprovados')
        
        return Response(
            content=output_buffer.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=planilha_aprovados.xlsx"}
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao finalizar planilha: {str(e)}")


@app.post("/finalize-disapproved-spreadsheet")
async def finalize_disapproved_spreadsheet(spreadsheet: UploadFile = File(...), disapproved_data_json: str = Form(...)):
    try:
        df_original = pd.read_excel(io.BytesIO(await spreadsheet.read()), engine='openpyxl')
        disapproved_data = json.loads(disapproved_data_json)
        if not disapproved_data:
            raise HTTPException(status_code=400, detail="Nenhum item reprovado enviado.")

        disapproved_skus = [str(item['sku']) for item in disapproved_data]
        df_original[COLUNA_EAN_SKU] = df_original[COLUNA_EAN_SKU].astype(str)
        
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

            # **INÍCIO DA LÓGICA DE LOGS DETALHADOS**
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
            # **FIM DA LÓGICA DE LOGS DETALHADOS**

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