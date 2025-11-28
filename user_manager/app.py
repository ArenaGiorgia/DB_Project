import threading
import grpc
from concurrent import futures
from flask import Flask, request, jsonify,abort
import hashlib
import user_pb2
import user_pb2_grpc
from database_postgres import database_postgres
from cache import Cache

#Avvio la Cache Globale che dura 5 minuti = 300 secondi
global_cache = Cache(ttl_seconds=300)

#Definisco il server Flask che risponde a POSTMAN
app = Flask(__name__)

#Definisco il Server gRPC (Risponde al Data Collector)
class UserManagerGRPC(user_pb2_grpc.UserManagerServicer):

    def CheckUser(self, request, context):
    #Questa funzione viene chiamata dal Data Collector. Mi dice se l'utente con i suoi dati si trova in memoria.

        client_id = request.client_id
        message_id = request.message_id
        email = request.email

        print(f"Richiesta da parte di {client_id} con message_id: {message_id} e Email: {email}")

        # controllo la cache con la Politica At-Most-Once
        cache_response = global_cache.get_response(client_id, message_id)
        if cache_response:
            print(f"Richiesta duplicata. Rispondo dandoti i dati gia in memoria.")
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
                #Eseguo query
                cursore.execute("SELECT 1 FROM users WHERE email = %s", (email,))

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
    """Fa partire il server gRPC in un thread separato"""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    user_pb2_grpc.add_UserManagerServicer_to_server(UserManagerGRPC(), server)
    port=50051
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    server.wait_for_termination()


@app.route('/users', methods=['POST'])
#su POSTMAN mettiamo metodo POST e /users per inserire un nuovo utente

def register():

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
            cursor.execute("SELECT 1 FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                return jsonify({"messaggio": "Utente già registrato"}), 200

            pw_hash = hashlib.sha256(password.encode()).hexdigest()

            #Inserisco l'utente
            cursor.execute(
                "INSERT INTO users (email, password, nome, cognome) VALUES (%s, %s, %s, %s)",
                (email,pw_hash, nome, cognome)
            )

            #salvo le modifiche
            connection.commit()

            return jsonify({"messaggio": "Registrazione completata!"}), 201

        finally:
            # Chiudo il cursore
            cursor.close()

    except Exception as e:
        return jsonify({"errore": f"Errore server: {str(e)}"}), 500

    finally:
        if connection:
            connection.close()


@app.route('/users', methods=['DELETE'])
#su POSTMAN mettiamo metodo DELETE e /users per inserire un nuovo utente
def delete_user():
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
            # Cancello l'utente ovviamente se email E password coincidono
            cur.execute("DELETE FROM users WHERE email = %s AND password = %s", (email, pw_hash))
            conn.commit()

            if cur.rowcount > 0:
                return jsonify({"message": "Utente eliminato", "email": email}), 200
            else:
                # Se rowcount è 0, o l'email è sbagliata o la password è sbagliata
                abort(401, description="Credenziali errate o utente inesistente")

        finally:
            cur.close()

    except Exception as e:
        # Se è un errore 401 lanciato da noi, lo rilanciamo
        if "401" in str(e): abort(401, description="Credenziali errate")
        abort(500, description=str(e))
    finally:
        if conn: conn.close()



if __name__ == '__main__':

    threading_grpc = threading.Thread(target=start_grpc_server, daemon=True)
    threading_grpc.start()
    app.run(host='0.0.0.0', port=5000, debug=False)