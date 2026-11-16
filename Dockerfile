FROM python:3.11-slim
WORKDIR /app

# CPU-only torch keeps the image small (embeddings run locally, no GPU needed).
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY ui ./ui
COPY data/kb ./data/kb
RUN useradd --create-home appuser && chown -R appuser /app/data
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
