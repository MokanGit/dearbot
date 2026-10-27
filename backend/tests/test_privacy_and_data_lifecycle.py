import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func
from backend.app.main import app
from backend.app.models import Application, Interaction, utc_now
from backend.app.config import settings


@pytest.mark.asyncio
async def test_telemetry_purged_when_application_revoked(db_session):
    """
    Verifies that revoking an application immediately and permanently
    purges all associated visitor interaction telemetry rows from SQLite.
    """
    uid_1 = str(uuid.uuid4())[:8]
    uid_2 = str(uuid.uuid4())[:8]

    # Create two applications
    app1 = Application(company="Company A", role="Role A", job_description="Job desc A", token=f"tok_a_{uid_1}")
    app2 = Application(company="Company B", role="Role B", job_description="Job desc B", token=f"tok_b_{uid_2}")
    db_session.add(app1)
    db_session.add(app2)
    await db_session.commit()

    # Add visitor telemetry interactions to both
    for i in range(3):
        int1 = Interaction(
            application_id=app1.id,
            timestamp=utc_now(),
            event_type="PROFILE_VIEW",
            ip_address=f"192.168.1.{10+i}",
            device_fingerprint=f"fp_a_{i}",
            device_metadata='{"screen": "1080p", "gpu": "Apple M3"}'
        )
        int2 = Interaction(
            application_id=app2.id,
            timestamp=utc_now(),
            event_type="QUESTION",
            question=f"Question {i} for Company B?",
            ip_address=f"10.0.0.{20+i}",
            device_fingerprint=f"fp_b_{i}"
        )
        db_session.add(int1)
        db_session.add(int2)
    await db_session.commit()

    # Verify initial interaction count
    count1 = (await db_session.execute(select(func.count(Interaction.id)).where(Interaction.application_id == app1.id))).scalar()
    count2 = (await db_session.execute(select(func.count(Interaction.id)).where(Interaction.application_id == app2.id))).scalar()
    assert count1 == 3
    assert count2 == 3

    # Authorize admin endpoint via dependency override
    from backend.app.services.auth import verify_admin_token
    app.dependency_overrides[verify_admin_token] = lambda: {"email": "admin@example.com"}

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Revoke app1
            res = await client.post(f"/admin/applications/{app1.id}/revoke")
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "revoked"
            assert data["telemetry_purged"] is True
    finally:
        app.dependency_overrides.pop(verify_admin_token, None)

    # Verify app1's visitor telemetry is completely purged from SQLite
    count1_after = (await db_session.execute(select(func.count(Interaction.id)).where(Interaction.application_id == app1.id))).scalar()
    assert count1_after == 0, "All visitor interaction telemetry for revoked application must be purged"

    # Verify app2's telemetry remains untouched
    count2_after = (await db_session.execute(select(func.count(Interaction.id)).where(Interaction.application_id == app2.id))).scalar()
    assert count2_after == 3, "Unrevoked application telemetry must remain intact"


@pytest.mark.asyncio
async def test_delete_application_purges_all_records(db_session):
    """
    Verifies that DELETE /admin/applications/{id} completely purges
    the application and any residual telemetry.
    """
    uid = str(uuid.uuid4())[:8]
    app_record = Application(company="Delete Corp", role="VP Eng", job_description="VP Eng description", token=f"tok_del_{uid}")
    db_session.add(app_record)
    await db_session.commit()

    interaction = Interaction(
        application_id=app_record.id,
        timestamp=utc_now(),
        event_type="PROFILE_VIEW",
        ip_address="8.8.8.8"
    )
    db_session.add(interaction)
    await db_session.commit()

    from backend.app.services.auth import verify_admin_token
    app.dependency_overrides[verify_admin_token] = lambda: {"email": "admin@example.com"}

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            del_res = await client.delete(f"/admin/applications/{app_record.id}")
            assert del_res.status_code == 200
            assert del_res.json()["status"] == "deleted"
    finally:
        app.dependency_overrides.pop(verify_admin_token, None)

    # Verify both app and interaction are gone
    app_check = (await db_session.execute(select(Application).where(Application.id == app_record.id))).scalar_one_or_none()
    assert app_check is None

    int_check = (await db_session.execute(select(func.count(Interaction.id)).where(Interaction.application_id == app_record.id))).scalar()
    assert int_check == 0
