from sqlalchemy import Column, String
from .database import Base

class User(Base):
    __tablename__ = "users"
    # La chiave primaria garantisce la politica At-Most-Once
    email = Column(String, primary_key=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    fiscal_code = Column(String)