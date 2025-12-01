# Sistema Distribuito di Monitoraggio Voli (DSBD Homework #1)

**Corso:** Sistemi Distribuiti e Big Data (2025/2026)

**Progetto:** #HW1 - Microservizi per gestione utenti e monitoraggio voli aerei

## 📋 Descrizione del Progetto
Questo progetto implementa un'architettura a microservizi distribuita e dockerizzata per il monitoraggio del traffico aereo utilizzando le API di *OpenSky Network*. Il sistema permette la registrazione di utenti e il tracciamento automatico di voli per aeroporti di interesse, garantendo robustezza e persistenza dei dati.

### 🏗️ Architettura
Il sistema è composto da 4 container orchestrati tramite Docker Compose:

1.  **User Manager Service (Python/Flask/gRPC):** Gestisce l'anagrafica utenti con politica di registrazione *"At-Most-Once"*.
2.  **Data Collector Service (Python/Flask/gRPC):** Raccoglie dati sui voli, gestisce i job periodici e comunica con lo User Manager.
3.  **User DB (PostgreSQL):** Database relazionale per garantire l'integrità dei dati utente.
4.  **Data DB (MongoDB):** Database NoSQL per la memorizzazione flessibile dei dati di volo.

## 🚀 Guida Rapida (Quick Start)

### Prerequisiti
* Docker Desktop installato e attivo.
* (Opzionale) Account su OpenSky Network per dati storici completi.

### Installazione e Avvio
1.  Clona la repository:
    ```bash
    git clone [https://github.com/ArenaGiorgia/DB_Project.git](https://github.com/ArenaGiorgia/DB_Project.git)
    cd DB_Project
    ```

2.  (Opzionale) Configura le credenziali OpenSky nel file `docker-compose.yml` per accedere ai dati reali (altrimenti il sistema userà dati simulati):
    ```yaml
    environment:
      - OPENSKY_USER=tuo_username
      - OPENSKY_PASSWORD=tua_password
    ```

3.  Avvia l'intero stack:
    ```bash
    docker-compose up --build
    ```

4.  Per fermare il sistema e pulire i volumi (reset database):
    ```bash
    docker-compose down -v
    ```

## 🔌 API Endpoints

Il sistema espone le seguenti API REST testabili tramite Postman:

### User Manager (Porta 5000)
| Metodo | Endpoint | Body (JSON) | Descrizione |
| :--- | :--- | :--- | :--- |
| `POST` | `/users` | `{"email": "...", "first_name": "..."}` | Registra un nuovo utente (Idempotente). |
| `DELETE` | `/users/<email>` | - | Cancella un utente. |

### Data Collector (Porta 5001)
| Metodo | Endpoint | Body / Query | Descrizione |
| :--- | :--- | :--- | :--- |
| `POST` | `/interests` | `{"email": "...", "airport": "CODE"}` | Aggiunge un interesse (Verifica utente via gRPC). |
| `GET` | `/flights/last` | `?airport=CODE` | Restituisce l'ultimo volo registrato. |
| `GET` | `/flights/average`| `?airport=CODE&days=7` | Calcola la media voli degli ultimi giorni. |

## 🛠️ Scelte Tecniche Principali
* **Polyglot Persistence:** PostgreSQL per dati strutturati (Utenti) vs MongoDB per dati volatili/JSON (Voli).
* **Comunicazione Ibrida:** REST per l'esterno, gRPC per la comunicazione interna tra microservizi.
* **Fault Tolerance:** Implementazione di un meccanismo di *fallback* che genera dati mock in caso di indisponibilità delle API OpenSky.
* **Background Jobs:** Utilizzo della libreria `schedule` e threading per non bloccare le API durante il fetch dei dati.

## 👥 Autori
* [Giorgia Arena]
* [Alessio Tornabene]
