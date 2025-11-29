import threading
import time

# mi costruisco la cache dove andrò a salvarmi i dati ovvero i risultati con il loro timestamp

class Cache:
    def __init__(self,ttl_seconds=300):

        #ttl sta per time to live cioe il tempo di vita dei dati nella cache ovvero 5 minuti = 300 secondi
        #mi creo una in-memory storage  dove salviamo i dati:
        #Chiave = "client_id:message_id" -> Valore = {risultato, timestamp}

        self.cache = {}
        self.ttl = ttl_seconds

        #trasforma le richieste in parallelo in sequenziale, è un mutex, significa che quando arrivano 2 richieste , ne gestisco 1 per volta senza creare danni
        self.lock = threading.Lock()

        # Avvio il thread che ogni volta che passano 60 secondi elimina le cose vecchie di 5 minuti
        self.pulizia = threading.Thread(target=self.pulisci_cache, daemon=True)  #deamon è un processo in background dove se il main muore anche il thread
        self.pulizia.start()

    def get_response(self, client_id, message_id):

        #creiamo la chiave univoca combinando sia il client_id e il message_id
        key = f"{client_id}:{message_id}"

        with self.lock:  #senza il with usavamo lock.acquire e lock.realise
            data = self.cache.get(key)
            if data:
                return data['response']  #restituisci il risultato
            return None

    def save_response(self, client_id, message_id, response):

        key = f"{client_id}:{message_id}"

        #Salva una risposta appena calcolata
        with self.lock:
            self.cache[key] = {
                'response': response,
                'timestamp': time.time()  # segno l'orario di arrivo
            }

    def remove_response(self, client_id, message_id):

        key = f"{client_id}:{message_id}"
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                print(f"[CACHE] Rimossa chiave obsoleta: {key}")



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
                    print(f"Cancellato il messaggio scaduto: {k}")