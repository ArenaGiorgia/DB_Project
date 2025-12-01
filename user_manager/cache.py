import threading
import time

# mi costruisco la cache dove andrò a salvarmi i dati ovvero i risultati con il loro timestamp

class Cache:
    def __init__(self,ttl_seconds=300):

        #mi creo una in-memory storage dove salviamo i dati
        #Chiave = "client_id:message_id" -> valore = {risultato, timestamp}
        self.cache = {}
        self.ttl = ttl_seconds

        #trasforma le richieste da parallelo in sequenziale,è un mutex (2 richieste, ne gestisco 1 per volta)
        self.lock = threading.Lock()
        self.pulizia = threading.Thread(target=self.pulisci_cache, daemon=True)
        self.pulizia.start()

    def get_response(self, client_id, message_id):

        #creiamo la chiave univoca combinando sia il client_id e il message_id
        key = f"{client_id}:{message_id}"

        #senza il with potevamo usare lock.acquire e lock.realise
        with self.lock:
            data = self.cache.get(key)
            if data:
                return data['response']
            return None


    def save_response(self, client_id, message_id, response):

        key = f"{client_id}:{message_id}"

        #Salva una risposta appena calcolata
        with self.lock:
            self.cache[key] = {
                'response': response,
                'timestamp': time.time()
            }

    def remove_response(self, client_id, message_id):

        key = f"{client_id}:{message_id}"
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                print(f"Rimossa chiave obsoleta: {key}")
                return True
            else:
                print(f"Tentativo di rimuovere chiave inesistente: {key}")
                return False


    def pulisci_cache(self):
        #controlla sempre e  ogni 60 secondi cancella le cose vecchie di 5 minuti
        while True:
            time.sleep(60)
            limit = time.time() - self.ttl  # 300 secondi = 5 minuti

            with self.lock:
                # Creo una lista delle chiavi vecchie da cancellare
                keys_to_delete = [k for k, v in self.cache.items() if v['timestamp'] < limit]

                for k in keys_to_delete:
                    del self.cache[k]

                    try:
                        request_id = k.split(':', 1)[1]
                        print(f"Ho eliminato il Request-ID scaduto: {request_id}")
                    except IndexError:

                        print(f"Eliminato: {k}")