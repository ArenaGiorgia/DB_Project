import sys
import os
import time
import threading
import logging
import grpc
import schedule
import requests
from flask import Flask, request, jsonify
from pymongo import MongoClient

# --- CONFIGURAZIONE ---
# Configurazione Log
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DataCollector")

# Configurazione Variabili d'Ambiente (fondamentali per Docker)
# Se siamo in locale usa 'localhost', se in Docker usa il nome del servizio 'user-manager'
USER_MANAGER_HOST = os.getenv("USER_MANAGER_HOST", "localhost")
USER_MANAGER_PORT = os.getenv("USER_MANAGER_PORT", "50051")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")

# Import dei file gRPC generati
# Nota: Assicurati che user_pb2.py e user_pb2_grpc.py siano nella stessa cartella o nel path
try:
    import user_pb2
    import user_pb2_grpc
except ImportError:
    # Fallback utile se la struttura delle cartelle è diversa in locale
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import user_pb2
    import user_pb2_grpc

# --- SETUP FLASK & DB ---
app = Flask(__name__)

# Connessione a MongoDB
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["flight_data_db"]
    interests_collection = db["interests"]
    flights_collection = db["flights"]
    logger.info(f"Connesso a MongoDB: {MONGO_URI}")
except Exception as e:
    logger.error(f"Errore connessione MongoDB: {e}")


# --- CLIENT gRPC ---
def check_user_exists_grpc(email):
    """
    Chiama il microservizio User Manager via gRPC per verificare l'utente.
    """
    target = f"{USER_MANAGER_HOST}:{USER_MANAGER_PORT}"
    logger.info(f"Tentativo connessione gRPC verso: {target} per email: {email}")

    try:
        # Creiamo il canale di comunicazione
        with grpc.insecure_channel(target) as channel:
            stub = user_pb2_grpc.UserManagerServiceStub(channel)
            # Creiamo la richiesta
            request_msg = user_pb2.GetUserRequest(email=email)
            # Effettuiamo la chiamata (RPC)
            response = stub.GetUser(request_msg)

            # Se non solleva eccezioni, l'utente esiste
            return True, response.user_id

    except grpc.RpcError as e:
        status_code = e.code()
        if status_code == grpc.StatusCode.NOT_FOUND:
            logger.warning(f"Utente {email} non trovato nello User Manager.")
            return False, None
        else:
            logger.error(f"Errore gRPC: {e.details()}")
            return False, None
    except Exception as e:
        logger.error(f"Errore generico connessione gRPC: {e}")
        return False, None


# --- API REST (Flask) ---

@app.route('/interests', methods=['POST'])
def add_interest():
    """
    L'utente invia: { "email": "mario@test.com", "airport_code": "LIRF" }
    1. Verifichiamo via gRPC se l'utente esiste.
    2. Se sì, salviamo l'interesse su MongoDB.
    """
    data = request.json
    email = data.get("email")
    airport_code = data.get("airport_code")

    if not email or not airport_code:
        return jsonify({"error": "Dati mancanti"}), 400

    # 1. Verifica esistenza utente (Comunicazione Inter-Processo)
    exists, user_id = check_user_exists_grpc(email)

    if not exists:
        return jsonify({"error": "Utente non registrato nel sistema. Impossibile aggiungere interesse."}), 404

    # 2. Salvataggio su MongoDB (Upsert: se esiste aggiorna, se no crea)
    # Usiamo $addToSet per evitare duplicati dello stesso aeroporto per lo stesso utente
    result = interests_collection.update_one(
        {"email": email},
        {"$addToSet": {"airports": airport_code}},
        upsert=True
    )

    return jsonify({"message": f"Aeroporto {airport_code} aggiunto agli interessi di {email}"}), 200


@app.route('/flights/<airport_code>', methods=['GET'])
def get_flights(airport_code):
    """
    Recupera i voli salvati per un certo aeroporto.
    """
    flights = list(flights_collection.find({"airport": airport_code}, {"_id": 0}))
    return jsonify(flights), 200


# --- BACKGROUND JOB (Data Fetcher) ---
def fetch_opensky_data():
    """
    Ciclo che scarica i dati da OpenSky per tutti gli aeroporti monitorati.
    """
    logger.info("Avvio ciclo di aggiornamento dati OpenSky...")

    # 1. Trova tutti gli aeroporti unici monitorati
    unique_airports = interests_collection.distinct("airports")
    if not unique_airports:
        logger.info("Nessun aeroporto da monitorare.")
        return

    for airport in unique_airports:
        logger.info(f"Recupero dati per aeroporto: {airport}")

        # --- SIMULAZIONE CHIAMATA OPENSKY ---
        # Qui dovresti usare requests.get("https://opensky-network.org/api/...")
        # Simuliamo un volo per non bloccare lo sviluppo senza API Key
        mock_flight = {
            "airport": airport,
            "icao24": "a0a0a0",
            "callsign": f"AZ{int(time.time()) % 1000}",
            "timestamp": time.time(),
            "type": "DEPARTURE"  # o ARRIVAL
        }

        # Scrittura su MongoDB
        flights_collection.insert_one(mock_flight)
        # ------------------------------------

    logger.info("Ciclo aggiornamento completato.")


def run_scheduler():
    # Esegui il job ogni 60 secondi
    schedule.every(60).seconds.do(fetch_opensky_data)

    while True:
        schedule.run_pending()
        time.sleep(1)


# --- MAIN ---
if __name__ == '__main__':
    # Avvia lo scheduler in un thread separato per non bloccare Flask
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True  # Si chiude quando muore il main
    scheduler_thread.start()

    # Avvia Flask sulla porta 5001 (o quella che preferisci, mappata in docker-compose)
    # Host 0.0.0.0 è essenziale per Docker
    app.run(host='0.0.0.0', port=5001)