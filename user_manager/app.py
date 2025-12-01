import threading
import grpc
from concurrent import futures
from flask import Flask, request, jsonify, abort
import hashlib
import user_pb2
import user_pb2_grpc
from database_postgres import database_postgres
from cache import Cache


#Avvio la Cache Globale che dura 5 minuti = 300 secondi
global_cache = Cache(ttl_seconds=300)

#Definisco il server Flask che risponde a POSTMAN
app = Flask(__name__)

DATA_COLLECTOR_GRPC = "data-collector:50052"

#Definisco il Server gRPC (Risponde al Data Collector)
class UserManagerGRPC(user_pb2_grpc.UserManagerServicer):

    def CheckUser(self, request, context):
    #Questa funzione viene chiamata dal Data Collector. Mi dice se l'utente con i suoi dati si trova in memoria.

        client_id = request.client_id #è riferito al servizio che in questo caso nostro è il datacollector
        message_id = request.message_id
        email = request.email

        print(f"Richiesta da parte di {client_id} con message_id: {message_id} e Email: {email}")

        # controllo la cache con la Politica At-Most-Once
        cache_response = global_cache.get_response(client_id, message_id)
        if cache_response:
            print(f"Mi hai mandato gia la stessa request, ti prendo il dato conservato nella mia cache.")
            # importante perche mi permette di dire che io NON ti sto dando il cosidetto "utente gia autenticato" ma la risposta che gia ho in cache
            return cache_response

        #Controllo nel database
        exists = False
        connection = None
        try:
            #nuova connessione
            connection = database_postgres.get_connection()
            cursore = connection.cursor()

            try:

                cursore.execute("SELECT * FROM users WHERE email = %s", (email,))

                #Controllo se c e qualcosa
                if cursore.fetchone():
                    exists = True
            finally:
                cursore.close()

        except Exception as e:
            print(f"Errore database: {e}")

        finally:
            #ovviamente alla fine si chiude sempre la connessione
            if connection:
                connection.close()

        response = user_pb2.CheckUserResponse(exists=exists)

        #salvo il nuovo messaggio dentro la cache
        global_cache.save_response(client_id, message_id, response)

        return response


def start_grpc_server():

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    user_pb2_grpc.add_UserManagerServicer_to_server(UserManagerGRPC(), server)
    port=50051
    server.add_insecure_port(f"[::]:{port}")  #canale insicuro che prende qualsiasi host
    server.start()
    server.wait_for_termination()


@app.route('/users', methods=['POST'])
#su POSTMAN mettiamo metodo POST e /users per inserire un nuovo utente

def register():


    # 1. Recupero l'ID univoco dalla richiesta (Header)
    request_id = request.headers.get('Request-ID')

    if not request_id:
        return jsonify({"errore": "Manca l'header Request-ID per At-Most-Once"}), 400

    # 2. Controllo se ho già risposto a questo ID dentro la cache
    #utilizzo il DATA_COLLECTOR come client per identificare quel microservizio
    cache_resp = global_cache.get_response("DATA_COLLECTOR", request_id)
    if cache_resp:
        print(f"Mi hai mandato gia la stessa request, ti prendo il dato conservato nella mia cache.")
        # Restituisco la risposta salvata (Status Code e Body)
        return jsonify(cache_resp['body']), cache_resp['status']
    # ----------------------------------------------------

    data = request.json
    email = data.get('email')
    nome = data.get('nome')
    password = data.get('password')
    cognome = data.get('cognome')

    if not email or not password:
        return jsonify({"errore": "Email obbligatoria"}), 400

    connection = None
    try:
        connection = database_postgres.get_connection()
        cursor = connection.cursor()

        try:

            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                return jsonify("Utente gia registrato / Vai al login"), 200

            pw_hash = hashlib.sha256(password.encode()).hexdigest()

            #Inserisco l'utente
            cursor.execute(
                "INSERT INTO users (email, password, nome, cognome) VALUES (%s, %s, %s, %s)",
                (email,pw_hash, nome, cognome)
            )

            #salvo le modifiche
            connection.commit()


            response_body = "Registrazione completata!"
            status_code = 201

            # Salvo in cache per futuri retry con lo stesso ID
            global_cache.save_response("DATA_COLLECTOR", request_id, {'body': response_body, 'status': status_code})


            return jsonify(response_body), status_code

        finally:
            # Chiudo il cursore
            cursor.close()

    except Exception as e:
        return jsonify({"errore": f"Errore server: {str(e)}"}), 500

    finally:
        if connection:
            connection.close()


@app.route('/users', methods=['DELETE'])
def delete_user():
    # Recupero l'ID per gestire la pulizia della cache
    request_id = request.headers.get('Request-ID')

    data = request.get_json() or {}
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        abort(400, description="Email e Password obbligatori per cancellare")

    pw_hash = hashlib.sha256(password.encode()).hexdigest()

    conn = None
    try:
        conn = database_postgres.get_connection()
        cur = conn.cursor()
        try:
            # 1. CANCELLO DA POSTGRES
            cur.execute("DELETE FROM users WHERE email = %s AND password = %s", (email, pw_hash))
            conn.commit()

            if cur.rowcount > 0:

                if request_id:
                    # Chiamo la funzione modificata
                    esito = global_cache.remove_response("DATA_COLLECTOR", request_id)

                    if esito:
                        print(f"Cache pulita correttamente per ID {request_id}")
                    else:
                        print(f"Nessuna cache trovata per ID {request_id}")
                try:
                    # Ci connettiamo alla porta 50052 che abbiamo configurato nel Data Collector
                    target_grpc = 'data-collector:50052'

                    with grpc.insecure_channel(target_grpc) as channel:
                        stub = user_pb2_grpc.DataCollectorStub(channel)

                        # Creo la richiesta gRPC
                        request_grpc = user_pb2.DeleteDataRequest(email=email)

                        # Chiamo la funzione remota
                        response = stub.DeleteData(request_grpc)

                        print(f"Richiesta inviata per {email}. Successo: {response.success}")

                except grpc.RpcError as e:
                    # Se il Data Collector è giù, stampiamo solo un warning
                    print(f"Errore gRPC verso Data Collector: {e}")
                except Exception as e:
                    print(f"Errore generico pulizia dati: {e}")

                return jsonify({"message": "Utente eliminato e dati puliti", "email": email}), 200
            else:
                # --- CORREZIONE QUI ---
                # 1. Stampo a video (Log del server)
                print(f"[DELETE FAIL] Utente {email} non trovato nel DB o password errata.")

                # 2. Restituisco una risposta JSON valida a Postman (così eviti l'HTML)
                return jsonify({"errore": "Utente non trovato o credenziali errate"}), 401

        finally:
            cur.close()

    except Exception as e:
        # Gestione errori generici del server
        print(f"[SERVER ERROR] {str(e)}")
        return jsonify({"errore": f"Errore interno del server: {str(e)}"}), 500
    finally:
        if conn: conn.close()

if __name__ == '__main__':

    threading_grpc = threading.Thread(target=start_grpc_server, daemon=True)
    threading_grpc.start()
    app.run(host='0.0.0.0', port=5000, debug=False)