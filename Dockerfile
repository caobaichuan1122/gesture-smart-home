FROM python:3.11-slim

# System deps for OpenCV + psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "yolo.asgi:application"]
