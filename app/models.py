"""Database tables. SQLite by default; one file in the data directory."""

import datetime as dt

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


class Line(Base):
    """A budget line: a monthly target and the transactions that count against it."""

    __tablename__ = "lines"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    group: Mapped[str] = mapped_column(String(64), default="Other")
    kind: Mapped[str] = mapped_column(String(16))  # variable | bill | fund | savings
    amount: Mapped[float] = mapped_column(Float, default=0)
    due_day: Mapped[int | None] = mapped_column(Integer)
    due_amount: Mapped[float | None] = mapped_column(Float)  # what actually leaves on the due date, if not `amount`
    pay_from: Mapped[int | None] = mapped_column(Integer)  # 1st or 2nd paycheck of the month
    from_month: Mapped[str | None] = mapped_column(String(7))  # YYYY-MM
    until_month: Mapped[str | None] = mapped_column(String(7))
    tracks: Mapped[list] = mapped_column(JSON, default=list)
    offsets: Mapped[list] = mapped_column(JSON, default=list)
    match: Mapped[list] = mapped_column(JSON, default=list)
    debt_key: Mapped[str | None] = mapped_column(String(64))
    shortcut: Mapped[str | None] = mapped_column(String(40))
    private: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text)
    start_balance: Mapped[float] = mapped_column(Float, default=0)  # funds only
    sort: Mapped[int] = mapped_column(Integer, default=0)

    def active(self, month: str) -> bool:
        return (not self.from_month or self.from_month <= month) and (not self.until_month or month <= self.until_month)


class Debt(Base):
    __tablename__ = "debts"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(32))
    last4: Mapped[str | None] = mapped_column(String(4))
    apr: Mapped[float] = mapped_column(Float, default=0)
    minimum: Mapped[float] = mapped_column(Float, default=0)
    due_day: Mapped[int | None] = mapped_column(Integer)
    limit: Mapped[float | None] = mapped_column(Float)
    payoff_order: Mapped[str | None] = mapped_column(String(16))  # "last" keeps it out of the avalanche


class DebtBalance(Base):
    """Balance history: from the budget file, statements, or a manual update."""

    __tablename__ = "debt_balances"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    debt_key: Mapped[str] = mapped_column(ForeignKey("debts.key", ondelete="CASCADE"))
    as_of: Mapped[dt.date] = mapped_column(Date)
    balance: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(16))  # budget | statement | manual


class Txn(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    amount: Mapped[float] = mapped_column(Float)  # negative = money out
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), default="other")
    line_key: Mapped[str | None] = mapped_column(String(64))  # set by hand; overrides the rules
    account: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(16))  # import | shortcut | manual
    ref: Mapped[str | None] = mapped_column(String(160), unique=True)
    note: Mapped[str | None] = mapped_column(Text)
    superseded_by: Mapped[int | None] = mapped_column(Integer)  # a logged entry later matched by an import
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    end: Mapped[dt.date | None] = mapped_column(Date)
    name: Mapped[str] = mapped_column(Text)
    amount: Mapped[float | None] = mapped_column(Float)
    line_key: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16), default="event")
    note: Mapped[str | None] = mapped_column(Text)


class SavingsGoal(Base):
    __tablename__ = "savings_goals"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    target: Mapped[float] = mapped_column(Float)
    balance: Mapped[float] = mapped_column(Float, default=0)
    account: Mapped[str | None] = mapped_column(String(32))  # e.g. savings_5678: balance follows imports


class BillPaid(Base):
    """A bill marked paid by hand, for months the bank data hasn't caught up on."""

    __tablename__ = "bills_paid"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    line_key: Mapped[str] = mapped_column(String(64))
    month: Mapped[str] = mapped_column(String(7))
    paid_on: Mapped[dt.date] = mapped_column(Date)


class ApiToken(Base):
    __tablename__ = "api_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now)
    last_used: Mapped[dt.datetime | None] = mapped_column(DateTime)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str | float | None] = mapped_column(JSON)


class MailSeen(Base):
    """Every payment email looked at, so each is handled exactly once."""

    __tablename__ = "mail_seen"
    message_id: Mapped[str] = mapped_column(String(250), primary_key=True)
    received: Mapped[dt.date] = mapped_column(Date)
    sender: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(16))  # logged | review | ignored
    txn_id: Mapped[int | None] = mapped_column(Integer)


class DigestLog(Base):
    __tablename__ = "digest_log"
    day: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    sent_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.now)
    status: Mapped[str] = mapped_column(String(200))


config.DATA_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(config.DB_URL, connect_args={"check_same_thread": False} if config.DB_URL.startswith("sqlite") else {})
Session = sessionmaker(engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
