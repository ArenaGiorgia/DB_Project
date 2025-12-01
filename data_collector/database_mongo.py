import os
import time
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017/")


class MongoDB:
    def __init__(self):
        self.client = None
        self.db = None
        self.connect_db()

    def connect_db(self):
        tentativi = 10
        while tentativi > 0:
            try:
                self.client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
                self.client.admin.command('ping')
                print("[MONGO] Connessione riuscita")
                self.db = self.client["flight_db"]
                # Creo indici per velocizzare le ricerche
                self.db.flights.create_index("airport")
                self.db.flights.create_index("timestamp")
                return
            except ConnectionFailure:
                print("Tentativo di riconnessione Mongo...")
                time.sleep(3)
                tentativi -= 1
        print("[MONGO] Impossibile connettersi.")

    # --- FUNZIONI DI SCRITTURA ---

    def aggiungi_interesse(self, email, aeroporto):
        """Salva l'interesse dell'utente per un aeroporto [cite: 24, 38]"""
        if self.db is None: return False
        # Usa 'update_one' con upsert=True per evitare duplicati
        self.db.interests.update_one(
            {"user": email, "airport": aeroporto},
            {"$set": {"user": email, "airport": aeroporto}},
            upsert=True
        )
        return True


    #per il delete quando togliamo un utente
    def rimuovi_interessi_utente(self, email):
            """Cancella tutti gli interessi associati a una email specifica"""
            if self.db is None: return 0

            # delete_many cancella TUTTI i documenti che matchano il filtro
            result = self.db.interests.delete_many({"user": email})
            print(f"[MONGO] Cancellati {result.deleted_count} interessi per {email}")
            return result.deleted_count



    def salva_voli(self, aeroporto, voli):
        """Salva i dati scaricati dal monitoraggio ciclico """
        if self.db is None: return None
        documento = {
            "airport": aeroporto,
            "timestamp": time.time(),
            "count": len(voli),  # Utile per le statistiche
            "data": voli
        }
        res = self.db.flights.insert_one(documento)
        return str(res.inserted_id)

    # --- FUNZIONI DI LETTURA (PER MONITORAGGIO) ---

    def get_tutti_aeroporti_monitorati(self):
        """Restituisce la lista degli aeroporti unici che interessano agli utenti"""
        if self.db is None: return []
        # Distinct mi dà la lista degli aeroporti senza duplicati
        return self.db.interests.distinct("airport")

    # --- FUNZIONI DI STATISTICA [cite: 43] ---

    def get_ultimo_volo(self, aeroporto):
        """Recupera l'ultimo volo registrato per un aeroporto """
        if self.db is None: return None

        # Cerca l'ultimo inserimento (sort timestamp decrescente)
        record = self.db.flights.find_one(
            {"airport": aeroporto, "count": {"$gt": 0}},  # Deve avere almeno un volo
            sort=[("timestamp", -1)]
        )

        if record and "data" in record and len(record["data"]) > 0:
            # Restituisce il primo volo della lista più recente
            return record["data"][0]
        return None

    def get_media_voli(self, aeroporto, giorni):
        """Calcola la media voli degli ultimi X giorni [cite: 45, 46]"""
        if self.db is None: return 0

        now = time.time()
        limite_tempo = now - (giorni * 86400)  # 86400 secondi in un giorno

        pipeline = [
            # 1. Filtra documenti di quell'aeroporto negli ultimi X giorni
            {"$match": {
                "airport": aeroporto,
                "timestamp": {"$gte": limite_tempo}
            }},
            # 2. Somma il numero di voli trovati
            {"$group": {
                "_id": None,
                "totale_voli": {"$sum": "$count"}
            }}
        ]

        risultato = list(self.db.flights.aggregate(pipeline))
        if not risultato:
            return 0

        totale_voli = risultato[0]["totale_voli"]
        # Media = Totale Voli / Giorni
        return round(totale_voli / giorni, 2)

    def get_voli_di_interesse_utente(self, email):
        """
        Simula la query:
        SELECT * FROM flights
        JOIN interests ON flights.airport = interests.airport
        WHERE interests.user = email
        """
        if self.db is None: return []

        # PASSO 1: Trova gli aeroporti seguiti dall'utente
        # Equivalente a: SELECT airport FROM interests WHERE user = email
        interessi_cursor = self.db.interests.find({"user": email})
        lista_aeroporti = [doc["airport"] for doc in interessi_cursor]

        if not lista_aeroporti:
            return []  # L'utente non segue nessun aeroporto

        # PASSO 2: Trova tutti i voli che matchano quegli aeroporti
        # Equivalente a: SELECT * FROM flights WHERE airport IN (lista_aeroporti)

        # Nota: Qui potremmo mettere un limite temporale (es. ultimi 7 giorni)
        # ma per ora prendiamo TUTTO lo storico come richiesto.
        cursor_flights = self.db.flights.find({
            "airport": {"$in": lista_aeroporti}
        }).sort("timestamp", -1)  # Ordiniamo dai più recenti

        # PASSO 3: "Appiattiamo" i risultati
        # Poiché ogni record nel DB contiene una lista di voli nel campo "data",
        # li estraiamo per fare una lista unica pulita.
        lista_voli_completa = []
        for doc in cursor_flights:
            if "data" in doc and isinstance(doc["data"], list):
                # Aggiungiamo i voli trovati alla lista risultato
                lista_voli_completa.extend(doc["data"])

        return lista_voli_completa

mongo_db = MongoDB()