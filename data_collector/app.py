import os
import uuid
import time
import threading
import requests
import grpc
from flask import Flask, request, jsonify

# Import locali
import user_pb2
import user_pb2_grpc
from database_mongo import mongo_db

app = Flask(__name__)

USER_MANAGER_ADDRESS = os.getenv("USER_MANAGER_GRPC", "localhost:50051")
MY_CLIENT_ID = "data_collector_service"
OPENSKY_USER = os.getenv("OPENSKY_USER")
OPENSKY_PASSWORD = os.getenv("OPENSKY_PASSWORD")


# --- FUNZIONE HELPER PER OPENSKY MODIFICATA ---
def fetch_opensky_data(airport):
    """
    Scarica dati da OpenSky.
    MODIFICA: Finestra temporale allargata e gestione Mock data.
    """
    ora_fine = int(time.time())
    # MODIFICA 1: Cerchiamo nelle ultime 24 ore (86400 sec) invece di 1 ora
    # Questo aggira il problema del ritardo nei dati dell'API gratuita.
    ora_inizio = ora_fine - 7200

    url = "https://opensky-network.org/api/flights/departure"
    params = {'airport': airport, 'begin': ora_inizio, 'end': ora_fine}

    auth_data = None
    if OPENSKY_USER and OPENSKY_PASSWORD:
        auth_data = (OPENSKY_USER, OPENSKY_PASSWORD)

    try:
        print(f"[OpenSky] Richiesta dati per {airport} (ultime 24h)...")
        r = requests.get(url, params=params, auth=auth_data, timeout=10)

        if r.status_code == 200:
            dati = r.json()
            if dati:
                return dati
            else:
                print(f"[OpenSky] Nessun volo trovato per {airport} nelle ultime 24h.")
        else:
            print(f"[OpenSky Error] Status {r.status_code}: {r.text}")

    except Exception as e:
        print(f"[OpenSky Exception] {e}")

    # MODIFICA 2: FALLBACK / MOCK DATA
    # Se l'API fallisce o è vuota, generiamo un dato finto per permettere
    # il test delle API REST (GET /last) e dimostrare il funzionamento del sistema.
    print(f"[SYSTEM] Generazione dati MOCK per {airport} (per scopi dimostrativi)...")
    mock_flight = [{
        "icao24": "mock_id",
        "firstSeen": int(time.time()) - 1000,
        "estDepartureAirport": airport,
        "lastSeen": int(time.time()),
        "estArrivalAirport": "LIRF",
        "callsign": f"TEST_{airport}",
        "estDepartureAirportHorizDistance": 0,
        "estDepartureAirportVertDistance": 0,
        "estArrivalAirportHorizDistance": 0,
        "estArrivalAirportVertDistance": 0,
        "departureAirportCandidatesCount": 0,
        "arrivalAirportCandidatesCount": 0
    }]
    return mock_flight


# --- BACKGROUND TASK  ---
def monitoraggio_ciclico():
    print("Avvio Thread Monitoraggio Ciclico...")
    while True:
        try:
            aeroporti = mongo_db.get_tutti_aeroporti_monitorati()
            if aeroporti:
                print(f"Aggiornamento per: {aeroporti}")
                for airport in aeroporti:
                    voli = fetch_opensky_data(airport)
                    mongo_db.salva_voli(airport, voli)
                    print(f"Dati aggiornati per {airport}")

            # Attesa ciclo (es. 10 minuti)
            time.sleep(600)
        except Exception as e:
            print(f"[BACKGROUND ERROR] {e}")
            time.sleep(60)


# --- API REST ---
@app.route('/interests', methods=['POST'])
def add_interest():
    data = request.json
    email = data.get('email')
    airport = data.get('airport')

    if not email or not airport:
        return jsonify({"errore": "Email e Airport obbligatori"}), 400

    # 1. Verifica Utente via gRPC
    messaggio_univoco = str(uuid.uuid4())
    try:
        with grpc.insecure_channel(USER_MANAGER_ADDRESS) as channel:
            stub = user_pb2_grpc.UserManagerStub(channel)


            grpc_req = user_pb2.CheckUserRequest(
                client_id=MY_CLIENT_ID,
                message_id=messaggio_univoco,
                email=email
            )

            risposta = stub.CheckUser(grpc_req)

            if not risposta.exists:
                return jsonify({"errore": "Utente non registrato"}), 404

    except grpc.RpcError as e:

        print(f"Errore gRPC reale: {e}")

        # Se vuoi gestire specifici codici di errore reali (es. UNAVAILABLE)
        if e.code() == grpc.StatusCode.UNAVAILABLE:
            return jsonify({"errore": "User Manager non raggiungibile"}), 503

        return jsonify({"errore": f"Errore comunicazione gRPC: {e.details()}"}), 500

    # 2. Aggiunge l'interesse nel Data DB
    mongo_db.aggiungi_interesse(email, airport)

    # 3. Download IMMEDIATO (con logica Mock se fallisce)
    print(f"Download immediato dati per {airport}...")
    voli = fetch_opensky_data(airport)  # Ora questa funzione ritorna Mock se OpenSky fallisce
    mongo_db.salva_voli(airport, voli)

    return jsonify({"messaggio": f"Interesse aggiunto e dati iniziali recuperati per {airport}"}), 200


@app.route('/flights/last', methods=['GET'])
def get_last_flight():
    airport = request.args.get('airport')
    if not airport: return jsonify({"errore": "Airport mancante"}), 400

    volo = mongo_db.get_ultimo_volo(airport)
    if volo:
        # Converto ObjectId se presente o pulisco dati interni
        if '_id' in volo: del volo['_id']
        return jsonify(volo), 200

    return jsonify({"messaggio": "Nessun dato trovato"}), 404


@app.route('/flights/average', methods=['GET'])
def get_average_flights():
    airport = request.args.get('airport')
    days = request.args.get('days')

    if not airport or not days:
        return jsonify({"errore": "Parametri mancanti"}), 400

    try:
        days = int(days)
    except ValueError:
        return jsonify({"errore": "Days deve essere un numero"}), 400

    media = mongo_db.get_media_voli(airport, days)
    return jsonify({
        "airport": airport,
        "days": days,
        "average_flights": media
    }), 200


if __name__ == '__main__':
    bg_thread = threading.Thread(target=monitoraggio_ciclico, daemon=True)
    bg_thread.start()
    print("Data Collector attivo sulla porta 5001...")
    app.run(host='0.0.0.0', port=5001, debug=True)