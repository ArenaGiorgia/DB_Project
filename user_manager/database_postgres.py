import os
import time
import psycopg
from dotenv import load_dotenv

# Carica le variabili dal file .env
load_dotenv()

class Database:
    def __init__(self):
        self.url = os.getenv("DATABASE_URL")
        # Avvio il tentativo di connessione
        self.connection_db()

    def connection_db(self):

        tentativi = 10
        while tentativi > 0:
            connection = None
            try:
                connection = psycopg.connect(self.url)
                print("Postgres connesso con successo")
                self.crea_tabella(connection)

                connection.close()
                return

            except Exception as e:

                 if connection is not None:
                    connection.close()

                 print("Riprovo tra 3 secondi...")
                 time.sleep(3)
                 tentativi -= 1

        raise Exception("Impossibile connettersi al Database dopo 10 tentativi")

    def crea_tabella(self, conn):

        query = """
        CREATE TABLE IF NOT EXISTS 
        users (
            email VARCHAR(255) PRIMARY KEY,
            password VARCHAR(255),
            nome VARCHAR(100),
            cognome VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        #Creo il cursore che è un oggetto che esegue i comandi
        cursore = conn.cursor()
        cursore.execute(query)
        #per salvare  le modifiche
        conn.commit()
        #Chiudo il cursore
        cursore.close()

    def get_connection(self):
        #fai una nuova connessione che ovviamente poi dobbiamo chiudere in app.py
        return psycopg.connect(self.url)

database_postgres= Database()