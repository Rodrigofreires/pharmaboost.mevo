import asyncio
import base64
import io
import json
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any
import pandas as pd
from pypdf import PdfReader
from bs4 import BeautifulSoup

# Importa os casos de uso da sua aplicação, que contêm a lógica de negócio
from app import use_cases

app = FastAPI(
    title="Gemini Application API",
    description="API para acessar casos de uso baseados no Gemini, com fluxo de revisão humana e otimização contínua.",
    version="3.8.0" # Versão com 5 Tentativas e Retorno do Melhor Score
)

# --- Configuração do CORS ---
# Permite que o frontend (rodando em um endereço diferente) se comunique com esta API
origins = ["http://localhost:5500", "http://127.0.0.1:5500", "null", "*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Modelos Pydantic ---
# Definem a estrutura de dados esperada para as requisições da API

class ApprovedItem(BaseModel):
    sku: int
    product_name: str
    html_content: str
    seo_title: str
    meta_description: str

class OptimizationRequest(BaseModel):
    product_type: str
    product_name: str
    product_info: Dict[str, Any]

# --- Endpoints da API ---

@app.post("/process-for-review", tags=["Processador de Planilha com Otimização de IA"])
async def process_for_review(
    spreadsheet: UploadFile = File(...),
    bulas: List[UploadFile] = File(...),
    skus_json: str = Form(...)
):
    """
    Recebe uma planilha e múltiplos arquivos de bula para processamento em lote.
    Este endpoint gera e OTIMIZA o conteúdo usando o SeoOptimizerAgent.
    """
    try:
        spreadsheet_bytes = await spreadsheet.read()
        bulas_data = [(bula.filename, await bula.read()) for bula in bulas]
        sku_list = [int(s) for s in json.loads(skus_json)]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler os arquivos: {e}")

    async def event_stream():
        async def send_event(event_type: str, data: dict):
            return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

        try:
            yield await send_event("log", {"message": "Lendo o arquivo da planilha...", "type": "info"})
            df = pd.read_excel(io.BytesIO(spreadsheet_bytes))
            yield await send_event("log", {"message": "Planilha carregada com sucesso.", "type": "success"})

            if len(sku_list) != len(bulas_data):
                raise ValueError("A quantidade de SKUs não corresponde à de bulas.")

            total_bulas = len(bulas_data)
            yield await send_event("log", {"message": f"Iniciando processamento e otimização de {total_bulas} SKUs...", "type": "info"})

            COLUNA_ID_SKU = "_IDSKU (Não alterável)"
            COLUNA_NOME_PRODUTO = "_NomeProduto (Obrigatório)"

            for i, ((bula_filename, bula_bytes), sku) in enumerate(zip(bulas_data, sku_list)):
                progress = f"({i+1}/{total_bulas})"
                log_prefix = f"<b>[SKU: {sku}]</b> {progress}"

                linha_produto = df[df[COLUNA_ID_SKU] == sku]
                if linha_produto.empty:
                    yield await send_event("log", {"message": f"{log_prefix} Não encontrado. Pulando.", "type": "warning"})
                    continue
                
                nome_produto = linha_produto.iloc[0][COLUNA_NOME_PRODUTO]
                yield await send_event("log", {"message": f"{log_prefix} Processando '{nome_produto}'...", "type": "info"})

                try:
                    reader = PdfReader(io.BytesIO(bula_bytes))
                    texto_da_bula = "".join(page.extract_text() + "\n" for page in reader.pages)

                    if not texto_da_bula.strip():
                        raise ValueError("Texto do PDF está vazio.")

                    product_info_simulado = {
                        "bula_text": texto_da_bula
                    }

                    yield await send_event("log", {"message": f"{log_prefix} Enviando para o Otimizador com IA...", "type": "info"})
                    
                    optimization_generator = use_cases.run_seo_optimization_stream(
                        product_type="medicine",
                        product_name=nome_produto,
                        product_info=product_info_simulado
                    )

                    final_content_data = None
                    final_score = 0
                    async for event_chunk in optimization_generator:
                        # Repassa todos os eventos (log, update) para o frontend
                        yield event_chunk
                        
                        if "event: done" in event_chunk:
                            data_str = event_chunk.split('data: ')[1]
                            final_data = json.loads(data_str)
                            final_score = final_data.get("final_score", 0)
                            
                            final_content_data = {
                                "html_content": final_data.get("final_content") or "<p>Erro ao gerar conteúdo.</p>",
                                "seo_title": final_data.get("seo_title") or f"{nome_produto}",
                                "meta_description": final_data.get("meta_description") or "Descrição não gerada."
                            }

                    # --- CORREÇÃO: Remove o Quality Gate e envia sempre o melhor resultado ---
                    if final_content_data:
                        review_item = { "sku": sku, "product_name": nome_produto, **final_content_data }
                        yield await send_event("review_item", review_item)
                        
                        # A mensagem de log reflete o resultado final, mas não descarta o item
                        if final_score >= 70:
                            yield await send_event("log", {"message": f"{log_prefix} Conteúdo OTIMIZADO (Score Final: {final_score}) gerado. Aguardando sua revisão.", "type": "success"})
                        else:
                            yield await send_event("log", {"message": f"{log_prefix} Melhor score atingido ({final_score}) não alcançou a meta de 70, mas foi enviado para revisão.", "type": "info"})
                    else:
                         yield await send_event("log", {"message": f"{log_prefix} ERRO: O otimizador não retornou um resultado final.", "type": "error"})

                except Exception as e:
                    yield await send_event("log", {"message": f"{log_prefix} ERRO: {e}", "type": "error"})

                await asyncio.sleep(0.5)

        except Exception as e:
            yield await send_event("error", {"message": f"Erro crítico no processamento: {str(e)}", "type": "error"})
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/finalize-spreadsheet", tags=["Processador de Planilha com Otimização de IA"])
async def finalize_spreadsheet(
    spreadsheet: UploadFile = File(...),
    approved_data_json: str = Form(...)
):
    """
    Recebe a planilha original e os dados aprovados/editados pelo usuário
    para montar e retornar o arquivo Excel final.
    """
    try:
        spreadsheet_bytes = await spreadsheet.read()
        approved_data = json.loads(approved_data_json)
        
        df = pd.read_excel(io.BytesIO(spreadsheet_bytes))
        
        COLUNA_ID_SKU = "_IDSKU (Não alterável)"
        COLUNA_V_HTML = "_BreveDescricaoProduto"
        COLUNA_AD_TITULO = "_TituloSite"
        COLUNA_AE_META_DESC = "_DescricaoMetaTag"
        
        for item in approved_data:
            sku = item['sku']
            index_linha = df.index[df[COLUNA_ID_SKU] == sku].tolist()
            if index_linha:
                idx = index_linha[0]
                df.loc[idx, COLUNA_V_HTML] = item['html_content']
                df.loc[idx, COLUNA_AD_TITULO] = item['seo_title']
                df.loc[idx, COLUNA_AE_META_DESC] = item['meta_description']

        output_buffer = io.BytesIO()
        df.to_excel(output_buffer, index=False, engine='openpyxl')
        output_buffer.seek(0)
        
        excel_base64 = base64.b64encode(output_buffer.read()).decode('utf-8')
        
        return JSONResponse(content={
            "filename": f"planilha_final_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            "file_data": excel_base64
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao finalizar a planilha: {str(e)}")