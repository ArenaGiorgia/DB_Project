import os
import time
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# Leggo l'URL da Docker (o uso localhost per i test)
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017/")


class MongoDB:
    def __init__(self):
        self.client = None
        self.db = None
        # Avvio la connessione appena creo la classe
        self.connect_db()

    def connect_db(self):
        """Prova a connettersi con un meccanismo di retry."""
        tentativi = 10
        while tentativi > 0:
            try:
                # 1. Mi connetto al server Mongo
                self.client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)

                # 2. Controllo se è vivo (ping)
                self.client.admin.command('ping')
                print("[MONGO] Connessione riuscita!")

                # 3. Seleziono il database (se non esiste, lo crea al primo salvataggio)
                self.db = self.client["flight_db"]
                return

            except ConnectionFailure:
                print("[MONGO] Non pronto... riprovo tra 3 secondi.")
                time.sleep(3)
                tentativi -= 1

        print("[MONGO] ERRORE: Impossibile connettersi.")

    def salva_voli(self, email, aeroporto, voli):
        """
        Salva i dati scaricati.
        Input:
          - email: chi ha fatto la richiesta
          - aeroporto: codice aeroporto (es. LIRF)
          - voli: la lista di dati grezzi ricevuti da OpenSky
        """
        if self.db is None:
            print("[MONGO] Errore: Nessuna connessione attiva.")
            return None

        # Preparo il documento JSON
        documento = {
            "user": email,
            "airport": aeroporto,
            "timestamp": time.time(),  # Ora attuale
            "data": voli  # Salvo tutto il blocco dati
        }

        # Inserisco nella collezione 'flights'
        risultato = self.db.flights.insert_one(documento)

        # Restituisco l'ID generato da Mongo (lo trasformo in stringa per leggerlo)
        return str(risultato.inserted_id)


# Istanza pronta
mongo_db = MongoDB()