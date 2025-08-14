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

class GenerateContentRequest(BaseModel): product_name: str; product_info: Dict
class ContentResponse(BaseModel): content: str
class MedicineContentResponse(BaseModel): html_content: str; seo_title: str; meta_description: str
class OptimizeContentRequest(BaseModel): product_type: str; product_name: str; product_info: Dict[str, Any]


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
    try:
        spreadsheet_bytes = await spreadsheet.read()
        
        # Lê todas as bulas para uma lista de tuplas (nome_do_arquivo, conteudo_em_bytes)
        bulas_data = []
        for bula_file in bulas:
            content = await bula_file.read()
            bulas_data.append((bula_file.filename, content))

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler os arquivos enviados: {e}")

    # O gerador agora recebe os dados em bytes, e não os objetos UploadFile.
    async def event_stream(spreadsheet_content: bytes, bulas_content: list):
        
        # Função auxiliar (corrotina que retorna a string do evento)
        async def send_log(message: str, type: str = "info") -> str:
            log_data = {"message": message, "type": type}
            return f"event: log\ndata: {json.dumps(log_data)}\n\n"

        try:
            # ETAPA 1: Carregar Planilha a partir dos bytes
            yield await send_log("Lendo o arquivo da planilha...", "info")
            # Usa io.BytesIO para que o pandas leia os dados da memória
            df = pd.read_excel(io.BytesIO(spreadsheet_content))
            yield await send_log("Planilha carregada em memória com sucesso.", "success")

            # ETAPA 2: Preparar dados
            sku_list = [int(s) for s in json.loads(skus_json)]
            if len(sku_list) != len(bulas_content):
                raise ValueError("A quantidade de SKUs não corresponde à quantidade de arquivos de bula.")

            # ETAPA 3: Processar cada bula
            total_bulas = len(bulas_content)
            yield await send_log(f"Iniciando processamento de {total_bulas} par(es) de bula/SKU...", "info")
            
            # Mapeamento de colunas
            COLUNA_ID_SKU = "_IDSKU (Não alterável)"
            COLUNA_NOME_PRODUTO = "_NomeProduto (Obrigatório)"
            COLUNA_V_HTML = "_BreveDescricaoProduto"
            COLUNA_AD_TITULO = "_TituloSite"
            COLUNA_AE_META_DESC = "_DescricaoMetaTag"

            # O loop agora itera sobre os dados que já lemos para a memória
            for i, ((bula_filename, bula_bytes), sku) in enumerate(zip(bulas_content, sku_list)):
                progress = f"({i+1}/{total_bulas})"
                log_prefix = f"<b>[SKU: {sku}]</b> {progress}"

                linha_produto = df[df[COLUNA_ID_SKU] == sku]
                if linha_produto.empty:
                    yield await send_log(f"{log_prefix} Não encontrado na planilha. Pulando.", "warning")
                    continue
                
                index_linha = linha_produto.index[0]
                nome_produto = linha_produto.iloc[0][COLUNA_NOME_PRODUTO]
                yield await send_log(f"{log_prefix} Processando '{nome_produto}'...", "info")

                # Extrair texto do PDF a partir dos bytes
                reader = PdfReader(io.BytesIO(bula_bytes))
                texto_da_bula = "".join(page.extract_text() + "\n" for page in reader.pages)

                if not texto_da_bula.strip():
                    yield await send_log(f"{log_prefix} Não foi possível extrair texto do PDF ({bula_filename}). Pulando.", "error")
                    df.loc[index_linha, COLUNA_V_HTML] = "ERRO: Falha ao extrair texto do PDF."
                    continue

                yield await send_log(f"{log_prefix} Enviando para a IA...", "info")
                conteudo_gerado = use_cases.generate_medicine_content(nome_produto, texto_da_bula)

                if "error" not in conteudo_gerado:
                    df.loc[index_linha, COLUNA_V_HTML] = conteudo_gerado.get("html_content")
                    df.loc[index_linha, COLUNA_AD_TITULO] = conteudo_gerado.get("seo_title")
                    df.loc[index_linha, COLUNA_AE_META_DESC] = conteudo_gerado.get("meta_description")
                    yield await send_log(f"{log_prefix} Conteúdo gerado com SUCESSO!", "success")
                else:
                    error_detail = conteudo_gerado.get('raw_response_for_debug', conteudo_gerado['error'])
                    yield await send_log(f"{log_prefix} ERRO da IA: {error_detail}", "error")
                    df.loc[index_linha, COLUNA_V_HTML] = f"ERRO NA GERAÇÃO: {conteudo_gerado['error']}"
                
                await asyncio.sleep(1)

            # ETAPA 4: Enviar arquivo final
            yield await send_log("Processamento concluído. Gerando arquivo Excel de saída...", "info")
            output_buffer = io.BytesIO()
            df.to_excel(output_buffer, index=False, engine='openpyxl')
            output_buffer.seek(0)
            
            excel_base64 = base64.b64encode(output_buffer.read()).decode('utf-8')
            
            done_data = {
                "filename": f"planilha_processada_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                "file_data": excel_base64
            }
            yield f"event: done\ndata: {json.dumps(done_data)}\n\n"

        except Exception as e:
            error_data = {"message": f"Erro crítico no processamento: {str(e)}", "type": "error"}
            yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
    
    # Inicia o streaming, passando os dados já lidos como argumentos para o gerador.
    return StreamingResponse(event_stream(spreadsheet_bytes, bulas_data), media_type="text/event-stream")