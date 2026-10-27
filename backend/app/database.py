from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event, inspect, text
from sqlalchemy.exc import OperationalError
from backend.app.config import settings
from backend.app.models import Base
import asyncio
import os

_IS_SQLITE = settings.DATABASE_URL.startswith("sqlite")
_DB_WRITE_LOCK = asyncio.Lock()

# Ensure parent directory for sqlite file exists
if _IS_SQLITE:
    db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

_ENGINE_KWARGS = {
    "echo": False,
    "future": True,
    "pool_size": 30,
    "max_overflow": 50,
    "pool_timeout": 60,
}
if _IS_SQLITE:
    _ENGINE_KWARGS["connect_args"] = {"timeout": 30}

engine = create_async_engine(
    settings.DATABASE_URL,
    **_ENGINE_KWARGS,
)

if _IS_SQLITE:
    @event.listens_for(engine.sync_engine, "connect")
    def _configure_sqlite_concurrency(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA busy_timeout=30000;")
            cursor.execute("PRAGMA temp_store=MEMORY;")
        finally:
            cursor.close()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

NEW_INTERACTION_COLUMNS = [
    ("access_method", "VARCHAR(50) DEFAULT 'web'"),
    ("tool", "VARCHAR(100)"),
    ("latency_ms", "INTEGER"),
    ("ip_address", "VARCHAR(64)"),
    ("reverse_dns", "VARCHAR(255)"),
    ("geo_country", "VARCHAR(100)"),
    ("geo_city", "VARCHAR(100)"),
    ("geo_region", "VARCHAR(100)"),
    ("isp", "VARCHAR(255)"),
    ("organization", "VARCHAR(255)"),
    ("asn", "VARCHAR(100)"),
    ("referer", "VARCHAR(512)"),
    ("accept_language", "VARCHAR(100)"),
    ("device_fingerprint", "VARCHAR(64)"),
    ("device_metadata", "TEXT"),
]


NEW_APPLICATION_COLUMNS = [
    ("cover_letter_path", "VARCHAR(512)"),
    ("cover_letter_filename", "VARCHAR(255)"),
    ("cover_letter_text", "TEXT"),
    ("candidate_name", "VARCHAR(255)"),
    ("candidate_headline", "VARCHAR(255)"),
    ("cover_letter_summary", "TEXT"),
    ("suggested_questions", "TEXT"),
]

NEW_DOCUMENT_COLUMNS = [
    ("classification", "VARCHAR(32) DEFAULT 'internal'"),
    ("is_active", "BOOLEAN DEFAULT 1"),
    ("classification_source", "VARCHAR(32) DEFAULT 'auto_default'"),
    ("manually_approved_at", "DATETIME"),
]


def _migrate_columns(sync_conn):
    inspector = inspect(sync_conn)
    if "interactions" in inspector.get_table_names():
        existing_cols = {col["name"] for col in inspector.get_columns("interactions")}
        for col_name, col_type in NEW_INTERACTION_COLUMNS:
            if col_name not in existing_cols:
                sync_conn.execute(text(f"ALTER TABLE interactions ADD COLUMN {col_name} {col_type}"))

    if "applications" in inspector.get_table_names():
        existing_cols = {col["name"] for col in inspector.get_columns("applications")}
        for col_name, col_type in NEW_APPLICATION_COLUMNS:
            if col_name not in existing_cols:
                sync_conn.execute(text(f"ALTER TABLE applications ADD COLUMN {col_name} {col_type}"))

        # Sanitize any legacy records that had running headers parsed as name or headline
        sync_conn.execute(text(
            "UPDATE applications SET candidate_name = :d_name WHERE candidate_name LIKE '%page%' OR candidate_name LIKE 'CV %' OR candidate_name LIKE 'CV-%' OR candidate_name LIKE 'CV –%'"
        ), {"d_name": settings.CANDIDATE_NAME})
        sync_conn.execute(text(
            "UPDATE applications SET candidate_headline = :d_hl WHERE candidate_headline LIKE '%page%' OR candidate_headline LIKE 'CV %' OR candidate_headline LIKE 'CV-%' OR candidate_headline LIKE 'CV –%'"
        ), {"d_hl": "CTO & Product Technology Executive"})

    if "documents" in inspector.get_table_names():
        existing_cols = {col["name"] for col in inspector.get_columns("documents")}
        for col_name, col_type in NEW_DOCUMENT_COLUMNS:
            if col_name not in existing_cols:
                sync_conn.execute(text(f"ALTER TABLE documents ADD COLUMN {col_name} {col_type}"))

        # Retroactively classify existing records
        from backend.app.services.google_drive import classify_document
        rows = sync_conn.execute(text("SELECT id, filename, title FROM documents")).fetchall()
        for r in rows:
            cls = classify_document(r[1] or "", r[2] or "")
            sync_conn.execute(text("UPDATE documents SET classification = :cls WHERE id = :id"), {"cls": cls, "id": r[0]})


async def init_db():
    """Create all database tables and migrate missing columns."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_columns)


async def commit_interaction(session: AsyncSession, interaction) -> None:
    """
    Safely persists an Interaction record under high concurrency.
    Closes any stale read-only snapshot before opening a write transaction
    to prevent SQLite WAL snapshot upgrade errors (SQLITE_BUSY_SNAPSHOT).
    """
    for attempt in range(4):
        try:
            async with _DB_WRITE_LOCK:
                if session.in_transaction() and not (session.new or session.dirty or session.deleted):
                    await session.commit()
                session.add(interaction)
                await session.commit()
            return
        except OperationalError:
            try:
                await session.rollback()
            except Exception:
                pass
            if attempt == 3:
                raise
            await asyncio.sleep(0.05 * (attempt + 1))


async def get_db():
    """Dependency for providing an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            if session.new or session.dirty or session.deleted:
                async with _DB_WRITE_LOCK:
                    await session.commit()
            elif session.in_transaction():
                await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
