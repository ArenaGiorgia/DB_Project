import logging
import threading
from concurrent import futures
from flask import Flask, request, jsonify
import grpc
from sqlalchemy.exc import IntegrityError

# IMPORT LOCALI (Funzionano perché i file sono nella stessa cartella)
import user_pb2
import user_pb2_grpc
from database import engine, SessionLocal, Base
from models import User

# Configurazione
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("UserManager")

# Inizializzazione DB
Base.metadata.create_all(bind=engine)


# --- SERVER gRPC ---
class UserManagerService(user_pb2_grpc.UserManagerServiceServicer):
    def GetUser(self, request, context):
        email_requested = request.email
        logger.info(f"gRPC Check: {email_requested}")

        session = SessionLocal()
        try:
            user = session.query(User).filter(User.email == email_requested).first()
            if user:
                return user_pb2.GetUserResponse(
                    user_id=user.email,
                    email=user.email,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    fiscal_code=user.fiscal_code
                )
            else:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details('Utente non trovato')
                return user_pb2.GetUserResponse()
        finally:
            session.close()


def serve_grpc():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    user_pb2_grpc.add_UserManagerServiceServicer_to_server(UserManagerService(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    server.wait_for_termination()


# --- SERVER FLASK ---
app = Flask(__name__)


@app.route('/users', methods=['POST'])
def register():
    data = request.json
    email = data.get("email")
    if not email: return jsonify({"error": "Email missing"}), 400

    session = SessionLocal()
    try:
        new_user = User(
            email=email,
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            fiscal_code=data.get("fiscal_code")
        )
        session.add(new_user)
        session.commit()
        return jsonify({"message": "User registered"}), 201
    except IntegrityError:
        session.rollback()
        # Politica At-Most-Once [cite: 63]
        return jsonify({"error": "User already exists"}), 409
    finally:
        session.close()


@app.route('/users/<email>', methods=['DELETE'])
def delete(email):
    session = SessionLocal()
    session.query(User).filter(User.email == email).delete()
    session.commit()
    session.close()
    return jsonify({"message": "Deleted"}), 200


if __name__ == '__main__':
    # Avvia gRPC in background
    t = threading.Thread(target=serve_grpc)
    t.daemon = True
    t.start()
    # Avvia Flask
    app.run(host='0.0.0.0', port=5000)