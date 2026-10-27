import pytest
import json
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from backend.app.main import app
from backend.app.models import Application, Document, Interaction, utc_now
from backend.app.services.ai import SYSTEM_PROMPT_TEMPLATE
from backend.app.services.cleanup import DataCleanupService


def test_private_notes_not_in_system_prompt():
    """Verify that private candidate notes are strictly excluded from the LLM system prompt template."""
    assert "notes" not in SYSTEM_PROMPT_TEMPLATE.lower()
    assert "CANDIDATE NOTES" not in SYSTEM_PROMPT_TEMPLATE
    assert "private notes" not in SYSTEM_PROMPT_TEMPLATE.lower()


@pytest.mark.asyncio
async def test_ask_stream_sse_endpoint():
    """Verify POST /a/{token}/ask-stream streams SSE tokens followed by metadata."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create application
        create_res = await client.post(
            "/admin/applications",
            json={
                "company": "Stream Tech Corp",
                "role": "Head of Engineering",
                "job_description": "Cloud native streaming systems.",
                "notes": "TOP SECRET NOTES - MUST NEVER BE IN LLM"
            }
        )
        assert create_res.status_code == 201
        token = create_res.json()["token"]

        # Call streaming endpoint
        stream_res = await client.post(
            f"/a/{token}/ask-stream",
            json={"question": "What is the candidate's leadership background?"},
            headers={"User-Agent": "Mozilla/5.0"}
        )
        assert stream_res.status_code == 200
        assert "text/event-stream" in stream_res.headers.get("content-type", "")

        events = []
        for line in stream_res.text.splitlines():
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                events.append(payload)

        # Ensure we received token chunks and terminal metadata
        token_events = [e for e in events if e.get("type") == "token"]
        metadata_events = [e for e in events if e.get("type") == "metadata"]

        assert len(token_events) > 0
        assert len(metadata_events) == 1
        assert "model_name" in metadata_events[0]
        assert metadata_events[0]["model_name"] != ""
        assert "confidence" in metadata_events[0]
        assert "request_id" in metadata_events[0]


@pytest.mark.asyncio
async def test_pre_publication_audit_endpoint():
    """Verify GET /admin/documents/pre-publication-summary returns audit statistics and categorized lists."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/admin/documents/pre-publication-summary")
        assert res.status_code == 200
        data = res.json()
        assert "active_public_count" in data
        assert "active_internal_count" in data
        assert "public_documents" in data
        assert "internal_documents" in data
        assert isinstance(data["public_documents"], list)
        assert isinstance(data["internal_documents"], list)


@pytest.mark.asyncio
async def test_permanent_application_cascade_deletion(db_session):
    """Verify immediate permanent deletion cascades across interactions and application logs."""
    app_record = Application(
        company="Delete Test Corp",
        role="VP Engineering",
        job_description="Temporary role to test deletion.",
        notes="Sensitive notes to be wiped"
    )
    db_session.add(app_record)
    await db_session.commit()
    await db_session.refresh(app_record)

    # Add dummy interaction
    interaction = Interaction(
        application_id=app_record.id,
        timestamp=utc_now(),
        event_type="TEST_EVENT",
        question="What is this?",
        answer="A test"
    )
    db_session.add(interaction)
    await db_session.commit()

    # Perform permanent deletion
    result = await DataCleanupService.delete_application_permanently(app_record, db_session)
    assert result["status"] == "deleted"

    # Verify application is gone
    check_stmt = select(Application).where(Application.id == app_record.id)
    assert (await db_session.execute(check_stmt)).scalar_one_or_none() is None

    # Verify interaction is gone
    check_int = select(Interaction).where(Interaction.application_id == app_record.id)
    assert (await db_session.execute(check_int)).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_30_day_retention_cleanup(db_session):
    """Verify 30-day retention cleanup deletes revoked applications older than 30 days and retains recent ones."""
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=35)
    recent_date = now - timedelta(days=10)

    # 1. Expired revoked application (>30 days revoked)
    old_revoked = Application(
        company="Old Revoked Corp",
        role="CTO",
        job_description="Old role",
        revoked_at=old_date
    )
    db_session.add(old_revoked)

    # 2. Recently revoked application (<30 days revoked)
    recent_revoked = Application(
        company="Recent Revoked Corp",
        role="CTO",
        job_description="Recent role",
        revoked_at=recent_date
    )
    db_session.add(recent_revoked)

    # 3. Active application (must never be touched)
    active_app = Application(
        company="Active Corp",
        role="CTO",
        job_description="Active role"
    )
    db_session.add(active_app)
    await db_session.commit()

    # Run cleanup
    cleanup_res = await DataCleanupService.cleanup_expired_revoked_applications(db_session, retention_days=30)
    assert cleanup_res["purged_count"] >= 1

    # Verify old_revoked was deleted
    assert (await db_session.execute(select(Application).where(Application.id == old_revoked.id))).scalar_one_or_none() is None

    # Verify recent_revoked was preserved
    assert (await db_session.execute(select(Application).where(Application.id == recent_revoked.id))).scalar_one_or_none() is not None

    # Verify active_app was preserved
    assert (await db_session.execute(select(Application).where(Application.id == active_app.id))).scalar_one_or_none() is not None
