# main.py
from app import use_cases

def run_application():
    """
    Ponto de entrada principal que executa os casos de uso de exemplo.
    """
    print("--- INICIANDO APLICAÇÃO GEMINI ---")

    # --- Teste do Sumarizador de Texto ---
    long_text = """
    A engenharia de prompt é o processo de projetar e otimizar instruções de entrada 
    para guiar eficazmente as respostas de um modelo de linguagem. É uma abordagem iterativa 
    que envolve clareza, especificidade e fornecimento de contexto para obter resultados 
    precisos e relevantes. Técnicas como few-shot prompting, onde exemplos são fornecidos, 
    e chain-of-thought, que incentiva o raciocínio passo a passo, são cruciais para 
    melhorar o desempenho do modelo em tarefas complexas.
    """
    summary = use_cases.summarize_text(long_text, length=25)
    print("\n--- CASO DE USO: SUMARIZADOR ---\n")
    print(f"Resumo Gerado:\n{summary}")
    print("\n----------------------------------\n")

    # --- Teste do Classificador de Sentimento ---
    review1 = "The plot was a bit predictable, but the acting was superb!"
    review2 = "A complete waste of time. I would not recommend this to anyone."
    print("\n--- CASO DE USO: CLASSIFICADOR DE SENTIMENTO ---\n")
    sentiment1 = use_cases.classify_sentiment(review1)
    sentiment2 = use_cases.classify_sentiment(review2)
    print(f"'{review1[:30]}...' -> Sentimento: {sentiment1}")
    print(f"'{review2[:30]}...' -> Sentimento: {sentiment2}")
    print("\n----------------------------------\n")

    # --- Teste do Gerador de E-mail ---
    points = [
        "Confirmar o recebimento do relatório do Q3.",
        "Agradecer à equipe pelo excelente trabalho.",
        "Agendar uma reunião de planejamento para o Q4 para a próxima terça-feira às 10h."
    ]
    email = use_cases.generate_formal_email(
        recipient_name="Equipe de Marketing",
        sender_name="João Silva, Diretor",
        tone="apreciativo e direto",
        key_points=points
    )
    print("\n--- CASO DE USO: GERADOR DE E-MAIL ---\n")
    print(f"E-mail Gerado:\n{email}")
    print("\n----------------------------------\n")


if __name__ == "__main__":
    run_application()