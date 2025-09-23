# app/google_search.py (Versão com Backoff Exponencial)
import logging
import time
from typing import List, NamedTuple
import requests
from config import settings

# Estrutura para manter os resultados organizados
class SearchResult(NamedTuple):
    source_title: str
    snippet: str

class QueryResult(NamedTuple):
    query: str
    results: List[SearchResult]

class GoogleSearch:
    """
    Realiza buscas utilizando a API Google Custom Search JSON,
    com cache, atraso e um sistema de backoff exponencial para lidar com erros de limite de taxa (429).
    """

    def __init__(self):
        self.api_key = settings.GOOGLE_API_KEY
        self.cse_id = settings.GOOGLE_CSE_ID
        self.search_url = "https://www.googleapis.com/customsearch/v1"
        self.cache = {}
        # Aumentar o delay inicial ajuda a espaçar as requisições
        self.REQUEST_DELAY_SECONDS = 1  # Atraso de 250ms

        if not self.api_key or not self.cse_id:
            raise ValueError(
                "As variáveis de ambiente GOOGLE_API_KEY e GOOGLE_CSE_ID não foram encontradas."
            )

    def search(self, queries: List[str]) -> List[QueryResult]:
        """
        Executa uma lista de buscas e retorna os resultados, utilizando o cache.
        """
        all_results = []
        for query in queries:
            if query in self.cache:
                logging.info(f"Cache HIT para a busca: '{query}'")
                all_results.append(self.cache[query])
                continue

            logging.info(f"Cache MISS para a busca: '{query}'. A contactar a API...")

           
            max_retries = 4
            backoff_factor = 2
            wait_time = 1 

            for attempt in range(max_retries):
                try:
                    time.sleep(self.REQUEST_DELAY_SECONDS)

                    params = {
                        "key": self.api_key,
                        "cx": self.cse_id,
                        "q": query,
                        "num": 5,
                    }
                    response = requests.get(self.search_url, params=params)
                    
                    # Lança um erro para códigos HTTP que indicam falha (como 429)
                    response.raise_for_status()

                    search_data = response.json()
                    query_results = []

                    if "items" in search_data:
                        for item in search_data.get("items", []):
                            query_results.append(
                                SearchResult(
                                    source_title=item.get("title", "Sem título"),
                                    snippet=item.get("snippet", "Sem snippet"),
                                )
                            )

                    result_obj = QueryResult(query=query, results=query_results)
                    self.cache[query] = result_obj
                    all_results.append(result_obj)
                    
                    # Se a busca foi bem-sucedida, sai do loop de tentativas
                    break 

                except requests.exceptions.HTTPError as e:
                    # Verifica se o erro é de "Too Many Requests"
                    if e.response.status_code == 429:
                        logging.warning(f"Limite de taxa atingido (429) na tentativa {attempt + 1}/{max_retries} para a busca: '{query}'. Aguardando {wait_time}s...")
                        time.sleep(wait_time)
                        wait_time *= backoff_factor # Aumenta o tempo de espera para a próxima tentativa
                        
                        # Se for a última tentativa, loga o erro e continua
                        if attempt == max_retries - 1:
                            logging.error(f"Erro ao buscar por '{query}' após {max_retries} tentativas: {e}")
                            all_results.append(QueryResult(query=query, results=[]))
                    else:
                        # Para outros erros HTTP, loga e desiste
                        logging.error(f"Erro HTTP inesperado ao buscar por '{query}': {e}")
                        all_results.append(QueryResult(query=query, results=[]))
                        break

                except requests.exceptions.RequestException as e:
                    logging.error(f"Erro de conexão ao buscar por '{query}': {e}")
                    all_results.append(QueryResult(query=query, results=[]))
                    break
            # --- FIM DA CORREÇÃO ---

        return all_results

google_search = GoogleSearch()