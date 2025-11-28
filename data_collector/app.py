import os
import uuid
import time
import threading
import requests
import grpc
from flask import Flask, request, jsonify

import user_pb2
import user_pb2_grpc
from database_mongo import mongo_db

app = Flask(__name__)

USER_MANAGER_ADDRESS = os.getenv("USER_MANAGER_GRPC", "localhost:50051")
MY_CLIENT_ID = "data_collector_service"
OPENSKY_USER = os.getenv("OPENSKY_USER")
OPENSKY_PASSWORD = os.getenv("OPENSKY_PASSWORD")


# --- FUNZIONE HELPER PER OPENSKY ---
def fetch_opensky_data(airport):
    """Funzione ausiliaria per scaricare dati da OpenSky"""
    ora_fine = int(time.time())
    ora_inizio = ora_fine - 3600  # Ultima ora

    url = "https://opensky-network.org/api/flights/departure"
    params = {'airport': airport, 'begin': ora_inizio, 'end': ora_fine}

    auth_data = None
    if OPENSKY_USER and OPENSKY_PASSWORD:
        auth_data = (OPENSKY_USER, OPENSKY_PASSWORD)

    try:
        r = requests.get(url, params=params, auth=auth_data, timeout=10)
        if r.status_code == 200:
            return r.json()
        else:
            print(f"[OpenSky Error] {r.status_code} per {airport}")
            return []
    except Exception as e:
        print(f"[OpenSky Exception] {e}")
        return []


# --- BACKGROUND TASK  ---
def monitoraggio_ciclico():
    """
    Ciclicamente legge dal DB la lista degli aeroporti di interesse,
    scarica i dati e li salva.
    """
    print(">>> Avvio Thread Monitoraggio Ciclico...")
    while True:
        try:
            # 1. Recupera la lista unica di aeroporti interessati
            aeroporti = mongo_db.get_tutti_aeroporti_monitorati()

            print(f"[BACKGROUND] Monitoraggio attivo per: {aeroporti}")

            for airport in aeroporti:
                # 2. Scarica info voli
                voli = fetch_opensky_data(airport)

                # 3. Scrive sul Data DB
                if voli:
                    mongo_db.salva_voli(airport, voli)
                    print(f"[BACKGROUND] Salvati {len(voli)} voli per {airport}")

            # Attesa ciclo (es. 10 minuti per test, PDF suggerisce 12h)
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
                return jsonify({"errore": "Utente non registrato"}), 403
    except grpc.RpcError as e:
        return jsonify({"errore": f"User Manager irragiungibile: {e}"}), 500

    # 2. Aggiunge l'interesse nel Data DB
    mongo_db.aggiungi_interesse(email, airport)

    # --- MODIFICA FONDAMENTALE PER IL TEST ---
    # Scarichiamo SUBITO i dati, senza aspettare il ciclo di 10 minuti
    print(f"[DC] Download immediato dati per {airport}...")
    voli = fetch_opensky_data(airport)
    if voli:
        mongo_db.salva_voli(airport, voli)
        print(f"[DC] Dati salvati con successo per {airport}")
    else:
        print(f"[DC] Nessun volo trovato al momento per {airport}")
    # ------------------------------------------

    return jsonify({"messaggio": f"Interesse aggiunto per {airport}"}), 200





@app.route('/flights/last', methods=['GET'])
def get_last_flight():
    """
    Recupero dell'ultimo volo (funzionalità aggiuntiva).
    Interroga il database locale (non OpenSky).
    """
    airport = request.args.get('airport')
    if not airport: return jsonify({"errore": "Airport mancante"}), 400

    volo = mongo_db.get_ultimo_volo(airport)
    if volo:
        return jsonify(volo), 200
    return jsonify({"messaggio": "Nessun dato trovato"}), 404


@app.route('/flights/average', methods=['GET'])
def get_average_flights():
    """
    Calcolo media ultimi X giorni[cite: 45].
    """
    airport = request.args.get('airport')
    days = request.args.get('days')  # Giorni (X)

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
    # Avvio il thread di monitoraggio in background
    bg_thread = threading.Thread(target=monitoraggio_ciclico, daemon=True)
    bg_thread.start()

    print(">>> Data Collector attivo sulla porta 5001...")
    app.run(host='0.0.0.0', port=5001, debug=True)