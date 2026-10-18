FROM python:3.13-slim
WORKDIR /app
COPY requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt
COPY qcheckers ./qcheckers
COPY server ./server
RUN useradd --create-home appuser
USER appuser
CMD ["sh", "-c", "python -m server --host 0.0.0.0 --port ${PORT:-8080} --log /tmp/server.jsonl"]
