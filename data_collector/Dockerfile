FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Il Data Collector potrebbe non dover esporre porte se fa solo da client e job in background,
# ma se metti delle API di statistica, esponi la porta (es. 5001)
EXPOSE 5001

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]