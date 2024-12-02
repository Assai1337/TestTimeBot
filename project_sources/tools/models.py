from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, BigInteger
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime, timedelta
from sqlalchemy.dialects.postgresql import JSON
from zoneinfo import ZoneInfo
Base = declarative_base()

# Модель для пользователей
class User(Base):
    __tablename__ = 'user'
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=False)
    firstname = Column(String, nullable=False)
    lastname = Column(String, nullable=False)
    middlename = Column(String)
    group = Column(String)
    registration_date = Column(DateTime, default=datetime.utcnow() + timedelta(hours=3))  # Используем функцию для установки времени
    attempts = relationship('TestAttempt', back_populates='user', cascade="all, delete-orphan")

# Модель для тестов
class Test(Base):
    __tablename__ = 'tests'
    id = Column(Integer, primary_key=True)
    test_name = Column(String, nullable=False)
    description = Column(Text)
    groups_with_access = Column(String)
    creation_date = Column(DateTime, default=datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None))
    expiry_date = Column(DateTime)  # Дата окончания будет устанавливаться вручную
    question_count = Column(Integer, nullable=False)
    scores_need_to_pass = Column(Integer, nullable=False)
    duration = Column(Integer, nullable=False)
    number_of_attempts = Column(Integer, nullable=False)
    # Связь с вопросами
    questions = relationship("Question", back_populates="test", cascade="all, delete-orphan")
    attempts = relationship('TestAttempt', back_populates='test', cascade="all, delete-orphan")

# Модель для вопросов с JSON-столбцом для вариантов ответов
class Question(Base):
    __tablename__ = 'questions'
    id = Column(Integer, primary_key=True)
    test_id = Column(Integer, ForeignKey('tests.id', ondelete="CASCADE"), nullable=False)
    question_text = Column(Text, nullable=False)
    question_type = Column(String, nullable=False)  # Тип: одиночный выбор, множественный выбор или текст

    # Поле для хранения вариантов ответов в формате JSON
    # Пример структуры: [{"text": "Option 1"}, {"text": "Option 2"}]
    options = Column(JSON, nullable=True)

    # Поле для хранения правильного ответа
    right_answer = Column(Text, nullable=True)

    # Связь с тестом
    test = relationship("Test", back_populates="questions")

# Модель для хранения попытки прохождения теста
class TestAttempt(Base):
    __tablename__ = 'test_attempts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    test_id = Column(Integer, ForeignKey('tests.id', ondelete="CASCADE"), nullable=False)  # Внешний ключ
    user_id = Column(BigInteger, ForeignKey('user.id', ondelete="CASCADE"), nullable=False)  # Внешний ключ
    start_time = Column(DateTime, nullable=False, default=datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None))  # Используем функцию для установки времени
    end_time = Column(DateTime, nullable=False)
    score = Column(Integer, nullable=False)
    passed = Column(Boolean, nullable=False)
    answers = Column(JSON, nullable=True)  # JSON поле для хранения ответов: id вопроса, ответ и правильность ответа

    # Определение отношений
    test = relationship('Test', back_populates='attempts')
    user = relationship('User', back_populates='attempts')

# Модель для групп
class Group(Base):
    __tablename__ = 'groups'
    id = Column(Integer, primary_key=True)
    groupname = Column(String, nullable=False, unique=True)  # Уникальное имя группы
