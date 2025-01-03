from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, BigInteger
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime, timedelta
from sqlalchemy.dialects.postgresql import JSON
from zoneinfo import ZoneInfo

Base = declarative_base()


# Модель для групп
class Group(Base):
    __tablename__ = 'groups'
    id = Column(Integer, primary_key=True)
    groupname = Column(String, nullable=False, unique=True)  # Уникальное имя группы

    # Обратное отношение к пользователям
    users = relationship('User', back_populates='group_rel')


# Модель для пользователей
class User(Base):
    __tablename__ = 'user'
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=False)
    firstname = Column(String, nullable=False)
    lastname = Column(String, nullable=False)
    middlename = Column(String)
    group = Column(String, ForeignKey('groups.groupname'), nullable=False)  # Внешний ключ на groups.groupname
    confirmed = Column(Boolean)
    registration_date = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(hours=3))

    # Отношения
    attempts = relationship('TestAttempt', back_populates='user', cascade="all, delete-orphan")
    group_rel = relationship('Group', back_populates='users')  # Отношение к группе


# Модель для тестов
class Test(Base):
    __tablename__ = 'tests'
    id = Column(Integer, primary_key=True)
    test_name = Column(String, nullable=False)
    description = Column(Text)
    groups_with_access = Column(String)
    creation_date = Column(DateTime, default=lambda: datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None))
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
    options = Column(JSON, nullable=True)  # Варианты ответов
    right_answer = Column(Text, nullable=True)  # Правильный ответ

    # Связь с тестом
    test = relationship("Test", back_populates="questions")


# Модель для хранения попытки прохождения теста
class TestAttempt(Base):
    __tablename__ = 'test_attempts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    test_id = Column(Integer, ForeignKey('tests.id', ondelete="CASCADE"), nullable=False)  # Внешний ключ на тест
    user_id = Column(BigInteger, ForeignKey('user.id', ondelete="CASCADE"),
                     nullable=False)  # Внешний ключ на пользователя
    start_time = Column(DateTime, nullable=False,
                        default=lambda: datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None))
    end_time = Column(DateTime, nullable=False)
    score = Column(Integer, nullable=False)
    passed = Column(Boolean, nullable=False)
    answers = Column(JSON, nullable=True)  # JSON поле для хранения ответов

    # Отношения
    test = relationship('Test', back_populates='attempts')
    user = relationship('User', back_populates='attempts')
