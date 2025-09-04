# Estágio 1: 'Builder' - Cria um ambiente virtual 100% limpo com as dependências
FROM python:3.11-slim as builder

WORKDIR /app

# Cria um ambiente virtual isolado para garantir que não haja conflitos
RUN python -m venv /opt/venv

# Ativa o ambiente virtual para os comandos subsequentes
ENV PATH="/opt/venv/bin:$PATH"

# Copia e instala as dependências DENTRO do ambiente virtual limpo
# Copiar somente o requirements.txt primeiro aproveita o cache do Docker.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---
# Estágio 2: 'Final' - Constrói a imagem final da aplicação
FROM python:3.11-slim

WORKDIR /app

# Cria um usuário não-root para executar a aplicação
RUN useradd --create-home appuser
USER appuser

# Copia o ambiente virtual perfeitamente limpo do estágio 'builder'
COPY --from=builder /opt/venv /opt/venv

# Ativa o ambiente virtual na imagem final
ENV PATH="/opt/venv/bin:$PATH"

# **LIMPEZA BRUTA**: Remove caches antigos antes de copiar o código novo
RUN find . -type d -name "__pycache__" -exec rm -r {} +

# Copia todo o seu código para a imagem final
# Agora, o código da aplicação é copiado DEPOIS que as dependências já foram instaladas.
COPY . .

# Expõe a porta que a API usará
EXPOSE 8000