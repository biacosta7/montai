# Imagem da demo no Hugging Face Spaces (Docker SDK, plano gratuito de CPU).
# Também serve para testar localmente:
#   docker build -t montai .
#   docker run --rm -p 8501:8501 --env-file .env montai

FROM python:3.12-slim

# O Space roda o container com o usuário de id 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONPATH=/home/user/app/src \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/user/.cache/huggingface
WORKDIR /home/user/app

# Dependências antes do código, para o cache do Docker reaproveitar esta camada.
# O requirements.txt instala o torch só-CPU no Linux.
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

# Baixa o modelo de embeddings e monta o índice do ChromaDB no build: a primeira
# visita não espera, e o app não depende do Hub para subir.
RUN python scripts/build_index.py

# Daqui em diante, o modelo vem só do cache local.
ENV HF_HUB_OFFLINE=1

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
