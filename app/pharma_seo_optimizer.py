import json
import asyncio
from . import seo_analyzer

class SeoOptimizerAgent:
    """
    Um agente de IA que orquestra a geração e otimização de conteúdo de SEO
    de forma iterativa, fornecendo um stream de eventos para o frontend.
    """
    MAX_ATTEMPTS = 5
    SCORE_THRESHOLD = 70

    def __init__(self, prompt_manager, gemini_client):
        """
        Inicializa o agente com as ferramentas necessárias.
        """
        self.prompt_manager = prompt_manager
        self.gemini_client = gemini_client

    async def _send_event(self, event_type: str, data: dict):
        """Formata um evento para Server-Sent Events (SSE)."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    async def run_optimization(self, product_type: str, product_name: str, product_info: dict):
        """
        Executa o ciclo completo de otimização de SEO e gera eventos.
        Este é um gerador assíncrono.
        """
        best_content = None
        best_score = 0
        
        try:
            # --- Tentativa 1: Geração Inicial ---
            yield await self._send_event("log", {"message": "Iniciando a primeira geração de conteúdo...", "type": "info"})
            
            # Define o gerador de prompt com base no tipo de produto
            generator_prompt_name = {
                "medicine": "medicamento_generator",
                "vitamin": "vitamina_suplemento_generator",
                "cosmetic": "dermocosmetico_generator"
            }.get(product_type, "medicamento_generator")

            # Renderiza o prompt inicial
            initial_prompt = self.prompt_manager.render(
                generator_prompt_name,
                product_name=product_name,
                melhoria_estrategica="Foco em clareza para o consumidor e conformidade com a bula.",
                **product_info
            )
            
            # Executa a chamada para a IA
            response_raw = self.gemini_client.execute_prompt(initial_prompt)
            
            # Extração robusta de JSON
            try:
                json_start = response_raw.find('{')
                json_end = response_raw.rfind('}') + 1
                if json_start == -1: raise ValueError("JSON não encontrado.")
                json_str = response_raw[json_start:json_end]
                initial_data = json.loads(json_str)
                current_content = initial_data.get("html_content")
            except (ValueError, json.JSONDecodeError):
                yield await self._send_event("log", {"message": "Falha ao decodificar a resposta inicial da IA. Tentando otimização direta.", "type": "warning"})
                current_content = f"<h1>{product_name}</h1><p>Informações sobre o produto.</p>"

            # Análise de SEO do conteúdo inicial
            analysis = seo_analyzer.analyze_seo_performance(current_content, product_name, product_info)
            current_score = analysis.get("total_score", 0)
            
            best_score = current_score
            best_content = initial_data if 'initial_data' in locals() and isinstance(initial_data, dict) else {
                "html_content": current_content,
                "seo_title": f"{product_name}",
                "meta_description": "Descrição inicial."
            }


            yield await self._send_event("update", {"score": current_score, "attempt": 1, "max_attempts": self.MAX_ATTEMPTS})
            yield await self._send_event("log", {"message": f"Tentativa 1/5 - Score inicial: {current_score}", "type": "info"})

            # --- Loop de Otimização ---
            for attempt in range(2, self.MAX_ATTEMPTS + 1):
                if best_score >= self.SCORE_THRESHOLD:
                    yield await self._send_event("log", {"message": f"Meta de score ({self.SCORE_THRESHOLD}) atingida. Finalizando otimização.", "type": "success"})
                    break

                yield await self._send_event("log", {"message": f"Iniciando tentativa de otimização {attempt}/{self.MAX_ATTEMPTS}...", "type": "info"})
                
                # Prepara o prompt de otimização
                optimization_prompt = self.prompt_manager.render(
                    "one_shot_optimizer",
                    product_name=product_name,
                    initial_content=best_content.get("html_content"),
                    initial_score=best_score,
                    feedback=json.dumps(analysis.get("breakdown"), indent=2),
                    successful_strategies="Usar H2 claros; incluir 'consulte um médico'.",
                    failed_strategies="Evitar parágrafos muito longos."
                )

                # Chama a IA para otimizar
                optimized_html = self.gemini_client.execute_prompt(optimization_prompt)

                # Analisa a nova versão
                analysis = seo_analyzer.analyze_seo_performance(optimized_html, product_name, product_info)
                new_score = analysis.get("total_score", 0)
                
                yield await self._send_event("update", {"score": new_score, "attempt": attempt, "max_attempts": self.MAX_ATTEMPTS})
                
                # Verifica se melhorou
                if new_score > best_score:
                    best_score = new_score
                    best_content["html_content"] = optimized_html
                    # Simples heurística para atualizar título e meta
                    best_content["seo_title"] = f"{product_name} - Otimizado"
                    best_content["meta_description"] = optimized_html.split('<p>')[1].split('</p>')[0][:155] if '<p>' in optimized_html else "Descrição otimizada."
                    yield await self._send_event("log", {"message": f"Tentativa {attempt}/{self.MAX_ATTEMPTS} - MELHORIA! Novo score: {new_score}", "type": "success"})
                else:
                    yield await self._send_event("log", {"message": f"Tentativa {attempt}/{self.MAX_ATTEMPTS} - Sem melhoria. Score: {new_score}", "type": "warning"})

                await asyncio.sleep(1) # Pausa para o frontend respirar

        except Exception as e:
            yield await self._send_event("error", {"message": f"Erro durante a otimização: {str(e)}", "type": "error"})
            # Garante que algo seja retornado mesmo em caso de erro
            if not best_content:
                 best_content = {
                    "html_content": f"<p>Ocorreu um erro ao processar: {e}</p>",
                    "seo_title": product_name,
                    "meta_description": "Erro na geração."
                }


        # --- Evento Final ---
        # Envia o melhor resultado encontrado, independentemente da pontuação
        final_data = {
            "final_score": best_score,
            "final_content": best_content.get("html_content"),
            "seo_title": best_content.get("seo_title"),
            "meta_description": best_content.get("meta_description")
        }
        yield await self._send_event("done", final_data)