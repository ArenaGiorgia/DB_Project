
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copia tutto il codice(cache.py, db_postgres.py, ecc)
COPY . .

#Espone le due porte: 5000 (Flask/Postman) e 50051 (gRPC)
EXPOSE 5000
EXPOSE 50051

ENV PYTHONUNBUFFERED=1

CMD ["python", "app.py"]