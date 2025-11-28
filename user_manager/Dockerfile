# Usa immagine Python leggera
FROM python:3.9-slim

# Cartella di lavoro nel container
WORKDIR /app

# Copia i requirements e installa
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia tutto il codice (compresi cache.py, db_postgres.py, ecc)
COPY . .

# Esponi le due porte: 5000 (Flask/Postman) e 50051 (gRPC)
EXPOSE 5000
EXPOSE 50051

# Fondamentale per vedere i print() nei log subito
ENV PYTHONUNBUFFERED=1

# COMANDO DI AVVIO: Lancia app.py
CMD ["python", "app.py"]