# Usa un'immagine Python leggera ufficiale
FROM python:3.9-slim

# Imposta la directory di lavoro dentro il container
WORKDIR /app

# Copia il file dei requisiti e installa le dipendenze
# (Facendolo prima di copiare il codice, sfruttiamo la cache di Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia tutto il codice sorgente della cartella user_manager nel container
COPY . .

# Esponi le porte:
# 50051 per gRPC (comunicazione interna)
# 5000 per REST API (se userai Flask)
EXPOSE 50051 5000

# Variabile d'ambiente per dire a Python di non bufferizzare l'output (utile per i log)
ENV PYTHONUNBUFFERED=1

# Comando di avvio
CMD ["python", "main.py"]