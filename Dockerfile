FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "psycopg[binary]>=3.1"

COPY jd_collector ./jd_collector
COPY config ./config

EXPOSE 8000
CMD ["python", "-m", "jd_collector", "serve", "--host", "0.0.0.0", "--port", "8000", "--with-scheduler"]
