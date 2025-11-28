# Usa immagine Python leggera
FROM python:3.9-slim

# Cartella di lavoro nel container
WORKDIR /app

# Copia i requirements e installa
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia tutto il codice (compresi db_mongo.py, ecc)
COPY . .

# Esponi la porta 5001 (Flask/Postman)
EXPOSE 5001

# Fondamentale per vedere i print() nei log subito
ENV PYTHONUNBUFFERED=1

# COMANDO DI AVVIO: Lancia app.py
CMD ["python", "app.py"]