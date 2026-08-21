from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

settings.ensure_storage_dirs()

engine = create_engine(
    f"sqlite:///{settings.database_path}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# There is no migration tool in this project (SQLite, single local user,
# TRD §13). `Base.metadata.create_all()` only creates missing *tables*, not
# missing *columns* on an existing one, so a schema change that only adds
# nullable columns is applied here idempotently rather than forcing anyone
# with an existing database to delete it.
_COLUMN_UPGRADES: dict[str, list[tuple[str, str]]] = {
    "bills": [
        ("vendor_phone", "VARCHAR(30)"),
        ("vendor_email", "VARCHAR(255)"),
    ],
}


def apply_column_upgrades() -> None:
    with engine.connect() as conn:
        for table, columns in _COLUMN_UPGRADES.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if not existing:
                continue  # table doesn't exist yet; create_all will create it with all columns
            for column_name, column_type in columns:
                if column_name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}"))
        conn.commit()
