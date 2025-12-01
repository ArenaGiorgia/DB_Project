import os
import uuid
import time
import threading
import requests
import grpc
import json
from flask import Flask, request, jsonify
import user_pb2
import user_pb2_grpc
from concurrent import futures
from database_mongo import mongo_db

app = Flask(__name__)

USER_MANAGER_ADDRESS = os.getenv("USER_MANAGER_GRPC", "localhost:50051")
MY_CLIENT_ID = "data_collector_service"
OPENSKY_CLIENT_ID = os.getenv("OPENSKY_CLIENT_ID")
OPENSKY_CLIENT_SECRET = os.getenv("OPENSKY_CLIENT_SECRET")
AUTH_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"


# server gRPC che diventa il DATA-COLLECTOR in caso di eliminazione degli utenti con interessi
class DataCollectorGRPC(user_pb2_grpc.DataCollectorServicer):
    def DeleteData(self, request, context):
        email = request.email
        print(f"Richiesta cancellazione dati per: {email}")

        count = mongo_db.rimuovi_interessi_utente(email)

        return user_pb2.DeleteDataResponse(success=True)


def start_grpc_server():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    user_pb2_grpc.add_DataCollectorServicer_to_server(DataCollectorGRPC(), server)

    # Usiamo una porta diversa dallo User Manager usando la 50052
    port = 50052
    server.add_insecure_port(f'[::]:{port}')
    print(f"Data Collector gRPC Server attivo sulla porta {port}")
    server.start()
    server.wait_for_termination()


def get_opensky_token():
    if not OPENSKY_CLIENT_ID or not OPENSKY_CLIENT_SECRET:
        print(" Client ID o Secret mancanti.")
        return None

    payload = {
        "grant_type": "client_credentials",
        "client_id": OPENSKY_CLIENT_ID,
        "client_secret": OPENSKY_CLIENT_SECRET
    }

    try:
        # Facciamo una POST all'URL di autenticazione di OPENSKY
        r = requests.post(AUTH_URL, data=payload, timeout=5)
        if r.status_code == 200:
            token = r.json().get("access_token")
            return token
        else:
            print(f"[OpenSky Auth Error] Status {r.status_code}: {r.text}")
            return None
    except Exception as e:
        print(f"[OpenSky Auth Exception] {e}")
        return None


def fetch_opensky_data(airport):
    ora_fine = int(time.time())
    # Cerchiamo nelle ultime 24 ore (7200 modificato a 86400 se vuoi 24h reali, qui ho lasciato il tuo 7200)
    # Nota: 7200 secondi sono 2 ore. Se vuoi 24 ore metti 86400.
    ora_inizio = ora_fine - 7200

    url = "https://opensky-network.org/api/flights/departure"
    params = {'airport': airport, 'begin': ora_inizio, 'end': ora_fine}
    token = get_opensky_token()
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        print(f"Token ottenuto, eseguo richiesta autenticata per {airport}...")
    else:
        print(f"Token non disponibile, eseguo richiesta anonima per {airport}...")

    try:
        # Passiamo 'headers' invece di 'auth'
        r = requests.get(url, params=params, headers=headers, timeout=10)

        if r.status_code == 200:
            dati = r.json()
            if dati:
                return dati
            else:
                print(f"[OpenSky] Nessun volo trovato per {airport} nel periodo richiesto.")
        else:
            print(f"[OpenSky Error] Status {r.status_code}: {r.text}")

    except Exception as e:
        print(f"[OpenSky Exception] {e}")

    #solo per scopi dimostrativi
    print(f"Generazione dati MOCK per {airport}")
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


#task in background
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


#API REST
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

        if e.code() == grpc.StatusCode.UNAVAILABLE:
            return jsonify({"errore": "User Manager non raggiungibile"}), 503

        return jsonify({"errore": f"Errore comunicazione gRPC: {e.details()}"}), 500

    # 2. Aggiunge l'interesse nel Data DB
    mongo_db.aggiungi_interesse(email, airport)

    # 3. Download IMMEDIATO
    print(f"Download immediato dati per {airport}...")
    voli = fetch_opensky_data(airport)
    mongo_db.salva_voli(airport, voli)

    return jsonify({"messaggio": f"Interesse aggiunto e dati iniziali recuperati per {airport}"}), 200


@app.route('/interests', methods=['DELETE'])
def remove_interests():
    """
    Endpoint chiamato dallo User Manager quando un utente viene eliminato.
    Uso: DELETE /interests?email=...
    """
    email = request.args.get('email')

    if not email:
        return jsonify({"errore": "Email mancante"}), 400

    count = mongo_db.rimuovi_interessi_utente(email)

    return jsonify({"messaggio": f"Rimossi {count} interessi per {email}"}), 200


@app.route('/flights/last', methods=['GET'])
def get_last_flight():
    airport = request.args.get('airport')
    if not airport: return jsonify({"errore": "Airport mancante"}), 400

    volo = mongo_db.get_ultimo_volo(airport)
    if volo:
        if '_id' in volo: del volo['_id']

        print(f"\n[DEBUG LAST FLIGHT] Ultimo volo trovato per {airport}:")
        print(json.dumps(volo, indent=4))
        print("-" * 30)

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

    response_data = {
        "airport": airport,
        "days": days,
        "average_flights": media
    }

    print(f"Calcolo Media:")
    print(json.dumps(response_data, indent=4))
    print("-" * 30)

    return jsonify(response_data), 200


@app.route('/flights/my-interests', methods=['GET'])
def get_my_interest_flights():

    email = request.args.get('email')

    if not email:
        return jsonify({"errore": "Parametro email obbligatorio"}), 400

    voli = mongo_db.get_voli_di_interesse_utente(email)

    response_data = {
        "user": email,
        "total_flights_found": len(voli),
        "flights": voli
    }

    print(f"Recupero interessi per {email}:")
    print(json.dumps(response_data, indent=4))
    print("-" * 30)

    return jsonify(response_data), 200


if __name__ == '__main__':
    bg_thread = threading.Thread(target=monitoraggio_ciclico, daemon=True)
    bg_thread.start()

    grpc_thread = threading.Thread(target=start_grpc_server, daemon=True)
    grpc_thread.start()

    print("Data Collector attivo sulla porta 5001 per FLASK e 5002 per il canale grpc")
    app.run(host='0.0.0.0', port=5001, debug=False)