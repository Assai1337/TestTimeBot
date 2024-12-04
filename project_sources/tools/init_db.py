from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, User, Test, Question, TestAttempt
import config

engine = create_engine(config.DATABASE_URL.replace("+asyncpg", ''))
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()

print("Таблицы успешно созданы в базе данных.")
