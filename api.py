import asyncio
import base64
import io
import json # Importa a biblioteca JSON
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from typing import Any, List, Dict
from pypdf import PdfReader
import pandas as pd

# Importa os casos de uso da sua aplicação
from app import use_cases
# Importa os modelos de dados necessários para outros endpoints
from data.analyze_news_models import AnalyzeNewsRequest, AnalyzeNewsResponse

app = FastAPI(
    title="Gemini Application API",
    description="API para acessar casos de uso baseados no Gemini, incluindo geração de conteúdo para e-commerce farma.",
    version="3.0.0" # Versão atualizada para refletir o mapeamento visual
)

# --- Configuração do CORS ---
# Permite que a sua página HTML (rodando em localhost) se comunique com esta API
origins = ["http://localhost:5500", "http://127.0.0.1:5500", "null", "*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Modelos Pydantic (mantidos para outros endpoints) ---
class SummarizeRequest(BaseModel): text: str; length: int = 50
class SummarizeResponse(BaseModel): summary: str
class GenerateContentRequest(BaseModel): product_name: str; product_info: Dict
class ContentResponse(BaseModel): content: str
class MedicineContentResponse(BaseModel): html_content: str; seo_title: str; meta_description: str
class OptimizeContentRequest(BaseModel): product_type: str; product_name: str; product_info: Dict[str, Any]

# --- Endpoints Legado (Preservados para não quebrar outras funcionalidades) ---
@app.post("/summarize", response_model=SummarizeResponse, tags=["Análise de Texto (Legado)"])
def summarize_endpoint(request: SummarizeRequest):
    return {"summary": use_cases.summarize_text(request.text, request.length)}

@app.post("/analyze-news", response_model=AnalyzeNewsResponse, tags=["Análise de Texto (Legado)"])
def analyze_news_endpoint(request: AnalyzeNewsRequest):
    return use_cases.analyze_news_from_url(request.url)

@app.post("/generate-vitamin-content", response_model=ContentResponse, tags=["Geração de Conteúdo Farma (Legado)"])
def generate_vitamin_endpoint(request: GenerateContentRequest):
    return {"content": use_cases.generate_vitamin_content(request.product_name, request.product_info)}

@app.post("/generate-dermocosmetic-content", response_model=ContentResponse, tags=["Geração de Conteúdo Farma (Legado)"])
def generate_dermocosmetic_endpoint(request: GenerateContentRequest):
    return {"content": use_cases.generate_dermocosmetic_content(request.product_name, request.product_info)}

@app.post("/optimize-content-stream", tags=["Otimização de Conteúdo com IA (Legado)"])
def optimize_content_stream_endpoint(request: OptimizeContentRequest):
    from app.pharma_seo_optimizer import SeoOptimizerAgent
    from app.prompt_manager import PromptManager
    from app.gemini_client import GeminiClient
    optimizer = SeoOptimizerAgent(PromptManager(), GeminiClient())
    async def event_stream():
        for event in optimizer.run_optimization(request.product_type, request.product_name, request.product_info):
            yield event
    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- NOVO ENDPOINT PARA O PROCESSADOR VISUAL (VERSÃO FINAL) ---
@app.post("/process-spreadsheet-visual", tags=["Processador Visual de Planilha"])
async def process_spreadsheet_visual(
    spreadsheet: UploadFile = File(...),
    bulas: List[UploadFile] = File(...),
    skus_json: str = Form(...) # Recebe os SKUs como uma string JSON do frontend
):
    """
    Recebe uma planilha, múltiplos PDFs de bulas e uma lista JSON de SKUs.
    Processa tudo em memória e retorna a planilha modificada para download.
    """
    # Nomes das colunas (baseado na sua planilha de exemplo)
    COLUNA_ID_SKU = "_IDSKU (Não alterável)"
    COLUNA_NOME_PRODUTO = "_NomeProduto (Obrigatório)"
    COLUNA_V_HTML = "_BreveDescricaoProduto"
    COLUNA_AD_TITULO = "_TituloSite"
    COLUNA_AE_META_DESC = "_DescricaoMetaTag"

    try:
        # ETAPA 1: Carrega a planilha em memória usando a biblioteca pandas
        print("Lendo o arquivo da planilha...")
        spreadsheet_content = await spreadsheet.read()
        df = pd.read_excel(io.BytesIO(spreadsheet_content))
        print("Planilha carregada em memória com sucesso.")

        # ETAPA 2: Processa a lista de SKUs recebida do frontend
        sku_list = [int(s) for s in json.loads(skus_json)]
        if len(sku_list) != len(bulas):
            raise HTTPException(status_code=400, detail="A quantidade de SKUs não corresponde à quantidade de arquivos de bula enviados.")

        # ETAPA 3: Itera sobre cada par (bula, sku) e processa
        print(f"Iniciando processamento de {len(bulas)} par(es) de bula/SKU...")
        for bula_file, sku in zip(bulas, sku_list):
            print(f"--- Processando SKU: {sku} | Arquivo: {bula_file.filename} ---")
            
            # Localiza a linha correta na planilha usando o SKU como chave
            linha_produto = df[df[COLUNA_ID_SKU] == sku]
            if linha_produto.empty:
                print(f"AVISO: SKU {sku} não encontrado na planilha. Pulando.")
                continue
            
            index_linha = linha_produto.index[0]
            nome_produto = linha_produto.iloc[0][COLUNA_NOME_PRODUTO]
            
            # Extrai o texto do arquivo PDF usando a biblioteca pypdf
            bula_content = await bula_file.read()
            reader = PdfReader(io.BytesIO(bula_content))
            texto_da_bula = "".join(page.extract_text() + "\n" for page in reader.pages)
            
            if not texto_da_bula.strip():
                print(f"AVISO: Não foi possível extrair texto do PDF para o SKU {sku}. Pulando.")
                df.loc[index_linha, COLUNA_V_HTML] = "ERRO: Falha ao extrair texto do PDF."
                continue

            # Chama a IA para gerar o conteúdo (função que já existia em use_cases.py)
            print(f"  Enviando para a IA para gerar conteúdo para '{nome_produto}'...")
            conteudo_gerado = use_cases.generate_medicine_content(nome_produto, texto_da_bula)

            # Atualiza o DataFrame (a planilha em memória) com os resultados
            if "error" not in conteudo_gerado:
                df.loc[index_linha, COLUNA_V_HTML] = conteudo_gerado.get("html_content")
                df.loc[index_linha, COLUNA_AD_TITULO] = conteudo_gerado.get("seo_title")
                df.loc[index_linha, COLUNA_AE_META_DESC] = conteudo_gerado.get("meta_description")
                print(f"  SUCESSO: Conteúdo para SKU {sku} gerado e pronto para ser salvo.")
            else:
                df.loc[index_linha, COLUNA_V_HTML] = f"ERRO NA GERAÇÃO: {conteudo_gerado['error']}"
                print(f"  ERRO da IA para SKU {sku}: {conteudo_gerado['error']}")
            
            # Pequena pausa para não sobrecarregar a API do Gemini
            await asyncio.sleep(1)

        # ETAPA 4: Prepara e retorna o arquivo Excel para download
        print("Processamento concluído. Gerando arquivo Excel de saída...")
        output_buffer = io.BytesIO()
        df.to_excel(output_buffer, index=False, engine='openpyxl')
        output_buffer.seek(0)

        return Response(
            content=output_buffer.read(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=planilha_processada.xlsx"}
        )

    except Exception as e:
        print(f"Erro crítico no processamento visual: {e}")
        raise HTTPException(status_code=500, detail=f"Ocorreu um erro interno no servidor: {str(e)}")

# --- NOVO ENDPOINT DE PROCESSAMENTO COM STREAMING DE LOGS ---
@app.post("/process-spreadsheet-stream", tags=["Processador Visual de Planilha"])
async def process_spreadsheet_stream(
    spreadsheet: UploadFile = File(...),
    bulas: List[UploadFile] = File(...),
    skus_json: str = Form(...)
):
    """
    Recebe os arquivos e transmite o progresso em tempo real (logs).
    Ao final, envia a planilha processada via um evento 'done'.
    """
    async def event_stream():
        # Função para enviar um log formatado para o frontend
        async def send_log(message: str, type: str = "info"):
            log_data = {"message": message, "type": type}
            yield f"event: log\ndata: {json.dumps(log_data)}\n\n"

        try:
            # ETAPA 1: Carregar Planilha
            yield await send_log("Lendo o arquivo da planilha...", "info")
            spreadsheet_content = await spreadsheet.read()
            df = pd.read_excel(io.BytesIO(spreadsheet_content))
            yield await send_log("Planilha carregada em memória com sucesso.", "success")

            # ETAPA 2: Preparar dados
            sku_list = [int(s) for s in json.loads(skus_json)]
            if len(sku_list) != len(bulas):
                raise ValueError("A quantidade de SKUs não corresponde à quantidade de arquivos de bula.")

            # ETAPA 3: Processar cada bula
            total_bulas = len(bulas)
            yield await send_log(f"Iniciando processamento de {total_bulas} par(es) de bula/SKU...", "info")
            
            # Mapeamento de colunas
            COLUNA_ID_SKU = "_IDSKU (Não alterável)"
            COLUNA_NOME_PRODUTO = "_NomeProduto (Obrigatório)"
            COLUNA_V_HTML = "_BreveDescricaoProduto"
            COLUNA_AD_TITULO = "_TituloSite"
            COLUNA_AE_META_DESC = "_DescricaoMetaTag"

            for i, (bula_file, sku) in enumerate(zip(bulas, sku_list)):
                progress = f"({i+1}/{total_bulas})"
                log_prefix = f"<b>[SKU: {sku}]</b> {progress}"

                # Localizar linha
                linha_produto = df[df[COLUNA_ID_SKU] == sku]
                if linha_produto.empty:
                    yield await send_log(f"{log_prefix} Não encontrado na planilha. Pulando.", "warning")
                    continue
                
                index_linha = linha_produto.index[0]
                nome_produto = linha_produto.iloc[0][COLUNA_NOME_PRODUTO]
                yield await send_log(f"{log_prefix} Processando '{nome_produto}'...", "info")

                # Extrair texto do PDF
                bula_content = await bula_file.read()
                reader = PdfReader(io.BytesIO(bula_content))
                texto_da_bula = "".join(page.extract_text() + "\n" for page in reader.pages)

                if not texto_da_bula.strip():
                    yield await send_log(f"{log_prefix} Não foi possível extrair texto do PDF. Pulando.", "error")
                    df.loc[index_linha, COLUNA_V_HTML] = "ERRO: Falha ao extrair texto do PDF."
                    continue

                # Chamar a IA
                yield await send_log(f"{log_prefix} Enviando para a IA...", "info")
                conteudo_gerado = use_cases.generate_medicine_content(nome_produto, texto_da_bula)

                # Atualizar DataFrame
                if "error" not in conteudo_gerado:
                    df.loc[index_linha, COLUNA_V_HTML] = conteudo_gerado.get("html_content")
                    df.loc[index_linha, COLUNA_AD_TITULO] = conteudo_gerado.get("seo_title")
                    df.loc[index_linha, COLUNA_AE_META_DESC] = conteudo_gerado.get("meta_description")
                    yield await send_log(f"{log_prefix} Conteúdo gerado com SUCESSO!", "success")
                else:
                    error_detail = conteudo_gerado.get('raw_response_for_debug', conteudo_gerado['error'])
                    yield await send_log(f"{log_prefix} ERRO da IA: {error_detail}", "error")
                    df.loc[index_linha, COLUNA_V_HTML] = f"ERRO NA GERAÇÃO: {conteudo_gerado['error']}"
                
                await asyncio.sleep(1) # Pausa para não sobrecarregar a API

            # ETAPA 4: Enviar arquivo final
            yield await send_log("Processamento concluído. Gerando arquivo Excel de saída...", "info")
            output_buffer = io.BytesIO()
            df.to_excel(output_buffer, index=False, engine='openpyxl')
            output_buffer.seek(0)
            
            # Converte o arquivo para base64 para enviar via JSON
            excel_base64 = base64.b64encode(output_buffer.read()).decode('utf-8')
            
            done_data = {
                "filename": f"planilha_processada_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                "file_data": excel_base64
            }
            yield f"event: done\ndata: {json.dumps(done_data)}\n\n"

        except Exception as e:
            # Envia um evento de erro fatal para o frontend
            error_data = {"message": f"Erro crítico no servidor: {str(e)}", "type": "error"}
            yield f"event: error\ndata: {json.dumps(error_data)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")