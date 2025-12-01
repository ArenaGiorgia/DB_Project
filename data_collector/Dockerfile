
FROM python:3.9-slim
WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copia tutto il codice(db_mongo.py, ecc)
COPY . .

# Esponi la porta 5001 (Flask/Postman)
EXPOSE 5001

ENV PYTHONUNBUFFERED=1

CMD ["python", "app.py"]