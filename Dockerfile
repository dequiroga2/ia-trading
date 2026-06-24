# Imagen para desplegar el portal en Render.com o Hugging Face Spaces (ambos gratis).
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt anthropic

COPY . .

# El host fija el puerto con la variable PORT (Render) o 7860 (HF Spaces).
ENV PORT=7860
EXPOSE 7860

CMD ["python", "server.py"]
