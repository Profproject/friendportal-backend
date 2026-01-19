from sqlalchemy import Column, Integer, Float, Boolean, String, DateTime
from sqlalchemy.orm import declarative_base
import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)

    # рефералка
    referrer_id = Column(Integer, nullable=True)

    # балансы
    balance = Column(Float, default=0)
    balance_locked = Column(Float, default=0)

    # флаги
    visit_reward_given = Column(Boolean, default=False)
    activated = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class WithdrawRequest(Base):
    __tablename__ = "withdraw_requests"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)

    address = Column(String)
    memo = Column(String)

    amount = Column(Float, default=0)
    status = Column(String, default="pending")

    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class AdRequest(Base):
    __tablename__ = "ad_requests"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)

    package = Column(Integer)  # 25 / 75 / 250
    link = Column(String)

    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
