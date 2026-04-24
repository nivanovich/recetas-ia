FROM python:3.10-slim

WORKDIR /app

# Instalar dependencias para procesamiento de video/audio
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway asigna un puerto dinámico mediante la variable $PORT
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT}"]