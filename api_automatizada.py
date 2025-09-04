# api_automatizada.py (Versão Totalmente Refatorada e Robusta)
import asyncio
import base64
import io
import json
import os
import traceback
import gdown
import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pypdf import PdfReader
from celery import group
from celery.result import AsyncResult
from worker import process_single_item, celery_app


app = FastAPI(
    title="PharmaBoost Automation API",
    description="API para processamento em lote e paralelo de planilhas Excel.",
    version="13.0.0-robust-download"
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Constantes (sem alterações) ---
COLUNA_EAN_SKU = '_EANSKU'
COLUNA_CODIGO_BARRAS = 'CODIGO_BARRAS'
COLUNA_LINK_BULA = 'BULA'
COLUNA_LINK_VALIDO = 'LINK_VALIDACAO'
COLUNA_NOME_PRODUTO = '_NomeProduto (Obrigatório)'
COLUNA_TITULO_SEO = '_TituloSite'
COLUNA_META_DESC = '_DescricaoMetaTag'
COLUNA_HTML = '_DescricaoProduto'

# --- Funções Auxiliares (sem alterações) ---
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

def read_spreadsheet(file_bytes: bytes, filename: str) -> pd.DataFrame:
    if filename.lower().endswith(('.xlsx', '.xls')):
        return pd.read_excel(io.BytesIO(file_bytes), engine='openpyxl')
    else:
        return pd.read_csv(io.BytesIO(file_bytes))

# --- ENDPOINTS ---

@app.post("/batch-process/start")
async def start_batch_processing(catalog_file: UploadFile = File(...), items_file: UploadFile = File(...)):
    try:
        catalog_bytes = await catalog_file.read()
        items_bytes = await items_file.read()
        
        df_catalogo = read_spreadsheet(catalog_bytes, catalog_file.filename)
        df_processar = read_spreadsheet(items_bytes, items_file.filename)

        required_catalog_cols = {COLUNA_CODIGO_BARRAS, COLUNA_LINK_BULA, COLUNA_LINK_VALIDO}
        required_items_cols = {COLUNA_EAN_SKU, COLUNA_NOME_PRODUTO}

        df_catalogo.columns = df_catalogo.columns.str.strip()
        df_processar.columns = df_processar.columns.str.strip()

        if not required_catalog_cols.issubset(df_catalogo.columns):
            missing = required_catalog_cols - set(df_catalogo.columns)
            raise HTTPException(status_code=400, detail=f"Coluna(s) ausente(s) no arquivo de CATÁLOGO: {missing}")
        
        if not required_items_cols.issubset(df_processar.columns):
            missing = required_items_cols - set(df_processar.columns)
            raise HTTPException(status_code=400, detail=f"Coluna(s) ausente(s) no arquivo de ITENS A PROCESSAR: {missing}")

        df_catalogo[COLUNA_CODIGO_BARRAS] = df_catalogo[COLUNA_CODIGO_BARRAS].astype(str).str.strip()
        df_processar[COLUNA_EAN_SKU] = df_processar[COLUNA_EAN_SKU].astype(str).str.strip()

        df_merged = pd.merge(df_processar, df_catalogo, left_on=COLUNA_EAN_SKU, right_on=COLUNA_CODIGO_BARRAS, how='left')
        df_validos = df_merged[df_merged[COLUNA_LINK_VALIDO].astype(str).str.strip().str.lower() == 'sim'].copy()
        
        if df_validos.empty:
            raise HTTPException(status_code=400, detail="Nenhum item válido encontrado para processamento.")

        tasks = []
        for _, row in df_validos.iterrows():
            ean_sku = str(row.get(COLUNA_EAN_SKU))
            nome_produto = row.get(COLUNA_NOME_PRODUTO)
            link_bula = row.get(COLUNA_LINK_BULA)
            
            if link_bula and not pd.isna(link_bula):
                bula_text = await get_bula_text(ean_sku, link_bula)
                if bula_text.strip():
                    # O worker agora recebe todas as informações necessárias
                    tasks.append(process_single_item.s(ean_sku=ean_sku, product_name=nome_produto, bula_text=bula_text))

        if not tasks:
             raise HTTPException(status_code=400, detail="Nenhuma bula válida pôde ser lida para iniciar o processamento.")

        job = group(tasks)
        result_group = job.apply_async()
        
        # Não precisamos mais salvar o arquivo original no servidor
        return JSONResponse(content={"job_id": result_group.id, "task_count": len(tasks)})

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Falha ao iniciar o trabalho: {str(e)}")


@app.get("/batch-process/status/{job_id}")
async def get_job_status(job_id: str):
    result = AsyncResult(job_id, app=celery_app)
    
    # Lógica de status permanece a mesma, é robusta
    if not result.children:
        return {"ready": False, "completed_tasks": 0, "total_tasks": "Iniciando...", "status": result.state}

    total_tasks = len(result.children)
    completed_tasks = sum(1 for res in result.children if res.ready())
    
    is_ready = total_tasks > 0 and completed_tasks == total_tasks

    return {
        "job_id": job_id,
        "status": "SUCCESS" if is_ready else result.state,
        "completed_tasks": completed_tasks,
        "total_tasks": total_tasks,
        "ready": is_ready
    }

@app.get("/batch-process/download-result/{job_id}", response_class=Response)
async def get_job_result_download(job_id: str):
    """
    NOVO ENDPOINT: Coleta os resultados e gera uma planilha Excel para download direto.
    """
    result_group = AsyncResult(job_id, app=celery_app)
    if not result_group.ready():
        raise HTTPException(status_code=202, detail="O trabalho ainda não está concluído.")

    results = result_group.get(propagate=False)
    successful_results = [res for res in results if isinstance(res, dict) and res.get('status') == 'SUCCESS']
    
    if not successful_results:
        # Se não houver sucesso, retorna um JSON com o detalhe das falhas
        failed_results = [res for res in results if not isinstance(res, dict) or res.get('status') != 'SUCCESS']
        return JSONResponse(
            status_code=404,
            content={
                "message": "Nenhum item foi processado com sucesso.",
                "failures": failed_results
            }
        )
    
    # Renomeia as chaves do dicionário para os nomes das colunas desejadas
    formatted_results = [{
        COLUNA_EAN_SKU: res.get('ean_sku'),
        COLUNA_NOME_PRODUTO: res.get('product_name'),
        COLUNA_TITULO_SEO: res.get('seo_title'),
        COLUNA_META_DESC: res.get('meta_description'),
        COLUNA_HTML: res.get('final_content')
    } for res in successful_results]
    
    # Cria um DataFrame diretamente dos resultados formatados
    df_resultados = pd.DataFrame(formatted_results)
    
    output_buffer = io.BytesIO()
    with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
        df_resultados.to_excel(writer, index=False, sheet_name='Resultados_IA')
    
    headers = {
        'Content-Disposition': f'attachment; filename="resultados_{job_id}.xlsx"'
    }
    
    return Response(content=output_buffer.getvalue(), media_type="application/vnd.openxmlformats-officedocument.sheet", headers=headers)

# Os endpoints /finalize-spreadsheet e /finalize-disapproved-spreadsheet permanecem, 
# pois a lógica deles para a etapa de revisão humana continua válida.
@app.post("/finalize-spreadsheet")
async def finalize_spreadsheet(spreadsheet: UploadFile = File(...), approved_data_json: str = Form(...)):
    try:
        # Lógica original mantida
        df_original = read_spreadsheet(await spreadsheet.read(), spreadsheet.filename)
        approved_data = json.loads(approved_data_json)
        if not approved_data:
            return Response(status_code=204)
        
        df_approved = pd.DataFrame(approved_data)
        
        # Função auxiliar para atualização segura
        def safe_update_and_preserve_data(df_original: pd.DataFrame, df_updates: pd.DataFrame, key_column: str) -> pd.DataFrame:
            df_original[key_column] = df_original[key_column].astype(str)
            df_updates[key_column] = df_updates[key_column].astype(str)
            df_final = df_original.set_index(key_column)
            df_updates_indexed = df_updates.set_index(key_column)
            df_final.update(df_updates_indexed)
            df_final.reset_index(inplace=True)
            return df_final

        df_final = safe_update_and_preserve_data(df_original, df_approved, COLUNA_EAN_SKU)

        output_buffer = io.BytesIO()
        with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
            df_final.to_excel(writer, index=False, sheet_name='Aprovados')
        
        return Response(content=output_buffer.getvalue(), media_type="application/vnd.openxmlformats-officedocument.sheet", headers={"Content-Disposition": "attachment; filename=planilha_aprovados.xlsx"})
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao finalizar planilha: {str(e)}")

@app.post("/finalize-disapproved-spreadsheet")
async def finalize_disapproved_spreadsheet(items_file: UploadFile = File(...), disapproved_data_json: str = Form(...)):
    try:
        # Lógica original mantida
        df_original = read_spreadsheet(await items_file.read(), items_file.filename)
        disapproved_data = json.loads(disapproved_data_json)
        if not disapproved_data:
            return Response(status_code=204)

        disapproved_skus = [str(item[COLUNA_EAN_SKU]) for item in disapproved_data]
        df_original[COLUNA_EAN_SKU] = df_original[COLUNA_EAN_SKU].astype(str)
        df_disapproved = df_original[df_original[COLUNA_EAN_SKU].isin(disapproved_skus)].copy()

        output_buffer = io.BytesIO()
        with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
            df_disapproved.to_excel(writer, index=False, sheet_name='Reprovados')
        
        return Response(content=output_buffer.getvalue(), media_type="application/vnd.openxmlformats-officedocument.sheet", headers={"Content-Disposition": "attachment; filename=planilha_reprovados.xlsx"})
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao gerar planilha de reprovados: {str(e)}")