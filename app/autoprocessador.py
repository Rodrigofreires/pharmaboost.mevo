# api_automatizada.py (Versão 11.0.4 - Gerenciamento de Rate Limit)
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
from typing import List, Iterator

from app import use_cases

app = FastAPI(
    title="PharmaBoost Automation API",
    description="API para processamento em lote de planilhas Excel.",
    version="11.0.4-rate-limit-handling"
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Constantes ---
COLUNA_EAN_SKU = '_EANSKU'
COLUNA_CODIGO_BARRAS = 'CODIGO_BARRAS'
COLUNA_LINK_BULA = 'BULA'
COLUNA_LINK_VALIDO = 'LINK_VALIDACAO'
COLUNA_NOME_PRODUTO = '_NomeProduto (Obrigatório)'
COLUNA_TITULO_SEO = '_TituloSite'
COLUNA_META_DESC = '_DescricaoMetaTag'
COLUNA_HTML = '_DescricaoProduto'
CHUNK_SIZE = 500

async def get_bula_text(ean_sku: str, link_bula: str) -> str:
    os.makedirs('bulas_temp', exist_ok=True)
    output_path = f"bulas_temp/{ean_sku}.pdf"
    try:
        if not os.path.exists(output_path):
            await asyncio.to_thread(gdown.download, str(link_bula), output_path, quiet=True, fuzzy=True)

        with open(output_path, 'rb') as f:
            file_bytes = f.read()
            return "".join(page.extract_text() for page in PdfReader(io.BytesIO(file_bytes)).pages if page.extract_text())
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)

def safe_update_and_preserve_data(df_original: pd.DataFrame, df_updates: pd.DataFrame, key_column: str) -> pd.DataFrame:
    df_original[key_column] = df_original[key_column].astype(str)
    df_updates[key_column] = df_updates[key_column].astype(str)

    df_final = df_original.set_index(key_column)
    df_updates_indexed = df_updates.set_index(key_column)

    df_final.update(df_updates_indexed)

    df_final.reset_index(inplace=True)
    return df_final

def read_spreadsheet(file_bytes: bytes, filename: str) -> pd.DataFrame:
    if filename.lower().endswith('.csv'):
        return pd.read_csv(io.BytesIO(file_bytes), sep=',', encoding='utf-8-sig')
    else:
        return pd.read_excel(io.BytesIO(file_bytes), engine='openpyxl')

@app.post("/batch-process-and-generate-draft")
async def batch_process_stream(catalog_file: UploadFile = File(...), items_file: UploadFile = File(...)):
    try:
        catalog_bytes = await catalog_file.read()
        items_bytes = await items_file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler os arquivos enviados: {e}")

    async def event_stream():
        async def _send_event(event_type: str, data: dict):
            await asyncio.sleep(0.01)
            return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

        try:
            df_catalogo = read_spreadsheet(catalog_bytes, catalog_file.filename)
            df_catalogo.columns = df_catalogo.columns.str.strip()
            df_catalogo[COLUNA_CODIGO_BARRAS] = df_catalogo[COLUNA_CODIGO_BARRAS].astype(str).str.strip()

            df_processar_full = read_spreadsheet(items_bytes, items_file.filename)
            df_processar_full.dropna(subset=[COLUNA_EAN_SKU], inplace=True)
            
            total_items = len(df_processar_full)
            yield await _send_event("log", {"message": f"Planilhas carregadas. Total de {total_items} itens para verificar.", "type": "info"})

            resultados_finais = []
            
            for i in range(0, total_items, CHUNK_SIZE):
                df_processar_chunk = df_processar_full.iloc[i:i + CHUNK_SIZE]
                
                processed_count = min(i + CHUNK_SIZE, total_items)

                df_processar_chunk.columns = df_processar_chunk.columns.str.strip()
                df_processar_chunk[COLUNA_EAN_SKU] = df_processar_chunk[COLUNA_EAN_SKU].astype(str).str.strip()

                df_merged = pd.merge(df_processar_chunk, df_catalogo, left_on=COLUNA_EAN_SKU, right_on=COLUNA_CODIGO_BARRAS, how='left')
                df_validos = df_merged[df_merged[COLUNA_LINK_VALIDO].astype(str).str.strip().str.lower() == 'sim'].copy()

                if df_validos.empty:
                    yield await _send_event("log", {"message": f"Lote {processed_count}/{total_items}: Nenhum item validado encontrado. Pulando.", "type": "info"})
                    continue

                yield await _send_event("log", {"message": f"Processando lote de {len(df_validos)} itens válidos (Total verificado: {processed_count}/{total_items})...", "type": "success"})

                for index, row in df_validos.iterrows():
                    ean_sku = str(row.get(COLUNA_EAN_SKU))
                    nome_produto = row.get(COLUNA_NOME_PRODUTO)
                    link_bula = row.get(COLUNA_LINK_BULA)

                    if not link_bula or pd.isna(link_bula):
                        yield await _send_event("log", {"message": f"<b>[SKU: {ean_sku}]</b> Link da bula ausente. Pulando.", "type": "warning"})
                        continue

                    bula_text = await get_bula_text(ean_sku, link_bula)
                    if not bula_text.strip():
                        yield await _send_event("log", {"message": f"<b>[SKU: {ean_sku}]</b> Falha ao ler o PDF da bula.", "type": "error"})
                        continue

                    async for chunk in use_cases.run_seo_pipeline_stream("medicine", nome_produto, {"bula_text": bula_text}):
                        yield chunk
                        if "event: done" in chunk:
                            final_data = json.loads(chunk.split('data: ')[1])
                            resultados_finais.append({
                                COLUNA_EAN_SKU: ean_sku,
                                COLUNA_TITULO_SEO: final_data.get("seo_title", "Erro"),
                                COLUNA_META_DESC: final_data.get("meta_description", "Erro"),
                                COLUNA_HTML: final_data.get("final_content", "Erro")
                            })

                    if index != df_validos.index[-1]:
                        # CORREÇÃO: Aumentado o tempo de espera para 60 segundos para evitar o limite de requisições da API.
                        yield await _send_event("log", {"message": "Aguardando 60 segundos para evitar o limite de requisições da API...", "type": "info"})

            if resultados_finais:
                df_resultados = pd.DataFrame(resultados_finais)
                df_final = safe_update_and_preserve_data(df_processar_full, df_resultados, COLUNA_EAN_SKU)

                output_buffer = io.BytesIO()
                with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='Rascunho_IA')

                file_data_b64 = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
                yield await _send_event("finished", {"filename": "rascunho_para_revisao.xlsx", "file_data": file_data_b64})
            else:
                 yield await _send_event("log", {"message": "<b>AVISO:</b> Nenhum produto válido foi processado com sucesso. O processo será finalizado.", "type": "warning"})

        except Exception as e:
            traceback.print_exc()
            yield await _send_event("log", {"message": f"ERRO FATAL: {e}", "type": "error"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.post("/finalize-spreadsheet")
async def finalize_spreadsheet(spreadsheet: UploadFile = File(...), approved_data_json: str = Form(...)):
    try:
        df_original = pd.read_excel(io.BytesIO(await spreadsheet.read()), engine='openpyxl')
        approved_data = json.loads(approved_data_json)
        if not approved_data:
            raise HTTPException(status_code=400, detail="Nenhum item aprovado foi enviado.")
            
        df_approved = pd.DataFrame(approved_data)
        
        df_final = safe_update_and_preserve_data(df_original, df_approved, COLUNA_EAN_SKU)

        output_buffer = io.BytesIO()
        with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
            df_final.to_excel(writer, index=False, sheet_name='Aprovados')
        
        return Response(content=output_buffer.getvalue(), media_type="application/vnd.openxmlformats-officedocument.sheet", headers={"Content-Disposition": "attachment; filename=planilha_aprovados.xlsx"})
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao finalizar planilha: {str(e)}")


@app.post("/finalize-disapproved-spreadsheet")
async def finalize_disapproved_spreadsheet(spreadsheet: UploadFile = File(...), disapproved_data_json: str = Form(...)):
    """
    Gera uma planilha contendo apenas as linhas dos produtos que foram reprovados.
    CORREÇÃO: Alterado 'items_file' para 'spreadsheet' para padronizar com o frontend.
    """
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
async def reprocess_items(catalog_file: UploadFile = File(...), items_to_reprocess_json: str = Form(...)):
    try:
        catalog_bytes = await catalog_file.read()
        items_to_reprocess = json.loads(items_to_reprocess_json)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler os arquivos ou dados: {e}")

    async def event_stream():
        df_catalogo = pd.read_excel(io.BytesIO(catalog_bytes), engine='openpyxl')
        df_catalogo.columns = df_catalogo.columns.str.strip()
        df_catalogo[COLUNA_CODIGO_BARRAS] = df_catalogo[COLUNA_CODIGO_BARRAS].astype(str)

        for item in items_to_reprocess:
            ean_sku = str(item[COLUNA_EAN_SKU])
            nome_produto = item[COLUNA_NOME_PRODUTO]
            
            catalog_info_row = df_catalogo[df_catalogo[COLUNA_CODIGO_BARRAS] == ean_sku]
            if catalog_info_row.empty: continue
            
            link_bula = catalog_info_row.iloc[0][COLUNA_LINK_BULA]
            bula_text = await get_bula_text(ean_sku, link_bula)
            
            async for chunk in use_cases.run_seo_pipeline_stream("medicine", nome_produto, {"bula_text": bula_text}):
                if "event: done" in chunk:
                    data = json.loads(chunk.split('data: ')[1])
                    data.update({COLUNA_EAN_SKU: ean_sku, COLUNA_NOME_PRODUTO: nome_produto})
                    chunk = f"event: done\ndata: {json.dumps(data)}\n\n"
                yield chunk

    return StreamingResponse(event_stream(), media_type="text/event-stream")