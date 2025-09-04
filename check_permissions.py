# check_permissions.py
import os
import json
from datetime import datetime, timezone

# Este script de diagnóstico vai verificar se o programa tem permissão para escrever no arquivo de estratégias.

# 1. Defina o caminho para o arquivo, da mesma forma que a aplicação principal faz.
project_root = os.path.dirname(os.path.abspath(__file__))
ledger_file = os.path.join(project_root, 'estrategias_pharma_seo.json')

print(f"Tentando ler e escrever no arquivo: {ledger_file}")

# 2. Crie um registro de teste para adicionar ao arquivo.
test_record = {
    "estrategia_aplicada": "TESTE DE ESCRITA BEM-SUCEDIDO",
    "tipo_de_produto": "diagnostic",
    "texto_original_score": 0,
    "novo_texto_score": 100,
    "melhora_score": 100,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "quantidade_lida": -1
}

try:
    # 3. Tente ler o conteúdo existente.
    print("Passo 1: Lendo o arquivo...")
    with open(ledger_file, 'r', encoding='utf-8') as f:
        content = f.read()
        # Valida se o arquivo não está vazio e se é um JSON válido
        if not content.strip():
             ledger = []
        else:
             ledger = json.loads(content)
        print(f"Leitura bem-sucedida. O arquivo contém {len(ledger)} registros.")

    # Adiciona o registro de teste na memória
    ledger.append(test_record)
    print("Passo 2: Adicionando registro de teste na memória.")

    # 4. Tente escrever o conteúdo completo de volta no arquivo.
    with open(ledger_file, 'w', encoding='utf-8') as f:
        json.dump(ledger, f, indent=2, ensure_ascii=False)
        print("Passo 3: Escrevendo o conteúdo atualizado no arquivo...")

    print("\n-------------------------------------------------------------")
    print("SUCESSO! ✅")
    print("O script conseguiu ler e escrever no arquivo com sucesso.")
    print("Verifique o arquivo 'estrategias_pharma_seo.json' para confirmar que o registro de TESTE foi adicionado.")
    print("Se o teste funcionou, a aplicação principal também deveria funcionar.")
    print("-------------------------------------------------------------")

except FileNotFoundError:
    print("\n-------------------------------------------------------------")
    print("ERRO: ARQUIVO NÃO ENCONTRADO! ❌")
    print(f"O arquivo esperado em '{ledger_file}' não foi encontrado.")
    print("Certifique-se de que o script está na pasta raiz 'pharmaBoost'.")
    print("-------------------------------------------------------------")

except json.JSONDecodeError:
    print("\n-------------------------------------------------------------")
    print("ERRO: JSON INVÁLIDO! ❌")
    print(f"O conteúdo do arquivo '{ledger_file}' não é um JSON válido.")
    print("Por favor, verifique o conteúdo do arquivo. Ele deve ser uma lista de objetos, começando com '[' e terminando com ']'.")
    print("Para resetar, você pode apagar o conteúdo e deixar apenas '[]'.")
    print("-------------------------------------------------------------")

except Exception as e:
    print("\n-------------------------------------------------------------")
    print(f"ERRO DE PERMISSÃO OU ESCRITA! ❌")
    print(f"Ocorreu um erro ao tentar escrever no arquivo: {e}")
    print("\nCAUSA PROVÁVEL:")
    print("O programa não tem as permissões necessárias para modificar o arquivo 'estrategias_pharma_seo.json'.")
    print("\nCOMO RESOLVER:")
    print("1. Navegue até a pasta do projeto no seu terminal ou explorador de arquivos.")
    print("2. Verifique as propriedades de segurança/permissões do arquivo.")
    print("3. Garanta que o usuário que está executando o script tenha permissão de ESCRITA (Write).")
    print("-------------------------------------------------------------")