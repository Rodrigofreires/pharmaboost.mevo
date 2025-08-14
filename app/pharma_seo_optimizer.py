import json
import os
import fcntl
import time
from typing import Dict, Any, Tuple
from datetime import datetime, timezone

from .prompt_manager import PromptManager
from .gemini_client import GeminiClient
from .seo_analyzer import analyze_seo_performance

class SeoOptimizerAgent:
    """
    Agente de IA que otimiza conteúdo de forma rápida e com aprendizado contínuo.
    Usa um processo de 3 etapas: Gerar, Estruturar e Otimizar.
    """
    def __init__(self, prompt_manager: PromptManager, gemini_client: GeminiClient):
        self.prompt_manager = prompt_manager
        self.gemini_client = gemini_client
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.ledger_file = os.path.join(project_root, 'estrategias_pharma_seo.json')

    def _update_ledger(self, update_function):
        """
        Função central e segura para ler, modificar e salvar o arquivo JSON,
        usando file locking para prevenir condições de corrida.
        """
        try:
            with open(self.ledger_file, 'a+', encoding='utf-8') as f:
                while True:
                    try:
                        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except (IOError, BlockingIOError):
                        time.sleep(0.1) 

                f.seek(0)
                content = f.read()
                
                ledger = json.loads(content) if content else []

                updated_ledger = update_function(ledger)
                
                f.seek(0)
                json.dump(updated_ledger, f, indent=2, ensure_ascii=False)
                f.truncate()
                
                # Libera o lock
                fcntl.flock(f, fcntl.LOCK_UN)
                
                return updated_ledger

        except (IOError, FileNotFoundError, json.JSONDecodeError):
            # Em caso de erro, garante que o lock seja liberado se ele foi adquirido
            try: fcntl.flock(f, fcntl.LOCK_UN)
            except: pass
            return []

    def _get_strategy_context(self, n: int = 5) -> Tuple[str, str]:
        """
        Lê e atualiza o contador de leitura das estratégias de forma segura.
        """
        def update_read_counts(ledger):
            for strategy in ledger:
                strategy['quantidade_lida'] = strategy.get('quantidade_lida', 0) + 1
            return ledger

        ledger = self._update_ledger(update_read_counts)
        
        if not ledger:
            return "Nenhuma ainda.", "Nenhuma ainda."

        successful = sorted([s for s in ledger if s.get('melhora_score', 0) > 0], key=lambda x: x.get('melhora_score', 0), reverse=True)
        failed = sorted([s for s in ledger if s.get('melhora_score', 0) <= 0], key=lambda x: x.get('timestamp', ''), reverse=True)
        
        successful_strategies = "\n".join([f"- {item['estrategia_aplicada']}" for item in successful[:n]]) or "Nenhuma ainda."
        failed_strategies = "\n".join([f"- {item['estrategia_aplicada']}" for item in failed[:n]]) or "Nenhuma ainda."
        
        return successful_strategies, failed_strategies

    def _save_strategy_to_ledger(self, strategy: str, old_score: int, new_score: int, product_type: str):
        """
        Salva uma nova estratégia no arquivo de forma segura.
        """
        def add_new_record(ledger):
            record = {
                "estrategia_aplicada": strategy,
                "tipo_de_produto": product_type,
                "texto_original_score": old_score,
                "novo_texto_score": new_score,
                "melhora_score": new_score - old_score,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "quantidade_lida": 0
            }
            ledger.append(record)
            return ledger

        self._update_ledger(add_new_record)

    def _get_strategy_suggestion(self, feedback: str, successful: str, failed: str) -> str:
        """Pede ao Gemini uma nova estratégia com base no contexto."""
        strategy_prompt = f"""
        Você é um estrategista de IA e SEO. Sua tarefa é criar uma ÚNICA e NOVA instrução para melhorar um prompt.
        O objetivo é corrigir os pontos fracos de um texto.

        CONTEXTO:
        - Pontos Fracos do Texto Atual:
        {feedback}
        - Estratégias que já FUNCIONARAM (inspire-se):
        {successful}
        - Estratégias que já FALHARAM (evite):
        {failed}

        SUA MISSÃO:
        Crie uma instrução de prompt CRIATIVA e DIFERENTE das que já falharam para corrigir os pontos fracos.
        Responda APENAS com a instrução para o prompt.
        """
        return self.gemini_client.execute_prompt(strategy_prompt, temperature=0.8)

    def run_optimization(self, product_type: str, product_name: str, product_info: Dict[str, Any]):
        def emit_event(event_type: str, data: dict):
            return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

        yield emit_event("log", {"message": f"INICIANDO OTIMIZAÇÃO PARA: '{product_name}'"})
        
        # --- ETAPA 1: Gerar Conteúdo Inicial ---
        yield emit_event("log", {"message": "Gerando conteúdo inicial..."})
        prompt_name_map = {"medicine": "medicamento_generator", "vitamin": "vitamina_suplemento_generator", "dermocosmetic": "dermocosmetico_generator"}
        generator_prompt_name = prompt_name_map[product_type]
        initial_context = {**product_info, "product_name": product_name, "melhoria_estrategica": "Nenhuma."}
        
        raw_initial_content = self.gemini_client.execute_prompt(self.prompt_manager.render(generator_prompt_name, **initial_context))
        
        initial_content = raw_initial_content.replace("```html", "").replace("```", "").strip()

        if "error" in initial_content:
            yield emit_event("error", {"message": "Falha ao gerar o conteúdo inicial.", "details": initial_content})
            return

        initial_analysis = analyze_seo_performance(initial_content, product_name, product_info)
        initial_score = initial_analysis.get('total_score', 0)
        yield emit_event("update", {"type": "score", "value": initial_score, "message": "Score Inicial."})

        # --- ETAPA 2: Gerar Estratégia de Melhoria ---
        yield emit_event("log", {"message": "Analisando e gerando estratégia de otimização..."})
        feedback_str = "\n".join([f"- {cat}: {' '.join(res['feedback'])}" for cat, res in initial_analysis.get('breakdown', {}).items() if res.get('feedback')])
        successful_strategies, failed_strategies = self._get_strategy_context()
        suggested_strategy = self._get_strategy_suggestion(feedback_str, successful_strategies, failed_strategies)
        
        if "error" in suggested_strategy:
             yield emit_event("error", {"message": "Falha ao gerar a estratégia de otimização.", "details": suggested_strategy})
             yield emit_event("done", {"final_content": initial_content, "final_score": initial_score})
             return
        
        yield emit_event("update", {"type": "strategy", "value": suggested_strategy})

        # --- ETAPA 3: Aplicar a Estratégia e Gerar Conteúdo Final ---
        yield emit_event("log", {"message": "Aplicando a nova estratégia e gerando conteúdo final..."})
        final_context = {**product_info, "product_name": product_name, "melhoria_estrategica": suggested_strategy}
        raw_final_content = self.gemini_client.execute_prompt(self.prompt_manager.render(generator_prompt_name, **final_context))
        final_content_html = raw_final_content.replace("```html", "").replace("```", "").strip()

        if "error" in final_content_html:
            yield emit_event("error", {"message": "Falha ao gerar o conteúdo final otimizado.", "details": final_content_html})
            self._save_strategy_to_ledger(suggested_strategy, initial_score, 0, product_type)
            yield emit_event("done", {"final_content": initial_content, "final_score": initial_score})
            return

        # --- ETAPA 4: Analisar Resultado e Salvar Aprendizado ---
        final_analysis = analyze_seo_performance(final_content_html, product_name, product_info)
        final_score = final_analysis.get('total_score', 0)

        yield emit_event("log", {"message": "Análise final completa. Salvando aprendizado..."})
        self._save_strategy_to_ledger(suggested_strategy, initial_score, final_score, product_type)
        
        improvement = final_score - initial_score
        result_message = f"Melhora de {improvement} pontos." if improvement > 0 else "A estratégia não melhorou o score, mas foi registrada para aprendizado."
        yield emit_event("update", {"type": "result", "value": result_message, "new_score": final_score})
        
        if final_score > initial_score:
            yield emit_event("done", {"final_content": final_content_html, "final_score": final_score})
        else:
            yield emit_event("done", {"final_content": initial_content, "final_score": initial_score})
