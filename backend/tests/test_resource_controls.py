import io
import json
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.models import Application, Interaction, utc_now
from backend.app.services.security import rate_limiter, MAX_QUESTIONS_PER_APPLICATION


@pytest.mark.asyncio
async def test_unified_multi_channel_quota_enforcement(db_session):
    uid = str(uuid.uuid4())[:8]
    test_app = Application(
        company="Quota Test Bank",
        role="Head of Architecture",
        job_description="Architectural governance and quota resilience",
        token=f"token_quota_{uid}",
    )
    db_session.add(test_app)
    await db_session.flush()

    # Pre-populate interactions across multiple channels to reach MAX_QUESTIONS_PER_APPLICATION:
    part_a = int(MAX_QUESTIONS_PER_APPLICATION * 0.4)
    part_b = int(MAX_QUESTIONS_PER_APPLICATION * 0.4)
    part_c = MAX_QUESTIONS_PER_APPLICATION - part_a - part_b
    for i in range(part_a):
        db_session.add(Interaction(
            application_id=test_app.id,
            timestamp=utc_now(),
            event_type="QUESTION_GET",
            access_method="url_get",
            tool="ask_cv_url"
        ))
    for i in range(part_b):
        db_session.add(Interaction(
            application_id=test_app.id,
            timestamp=utc_now(),
            event_type="MCP_CALL",
            access_method="mcp",
            tool="ask_about_candidate"
        ))
    for i in range(part_c):
        db_session.add(Interaction(
            application_id=test_app.id,
            timestamp=utc_now(),
            event_type="WEBMCP_CALL",
            access_method="webmcp",
            tool="ask_cv"
        ))
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. POST /ask should now hit 429
        post_res = await client.post(
            f"/a/{test_app.token}/ask",
            json={"question": "What is his background?"}
        )
        assert post_res.status_code == 429
        assert "Frågekvoten för denna profil har uppnåtts" in post_res.json()["detail"]

        # 2. GET /ask should also hit 429
        get_res = await client.get(
            f"/a/{test_app.token}/ask",
            params={"q": "Tell me about his background"}
        )
        assert get_res.status_code == 429
        assert "Frågekvoten för denna profil har uppnåtts" in get_res.json()["detail"]

        # 3. MCP ask_about_candidate should return error with quota message
        mcp_res = await client.post(
            f"/mcp/{test_app.token}",
            json={
                "jsonrpc": "2.0",
                "id": 99,
                "method": "tools/call",
                "params": {
                    "name": "ask_about_candidate",
                    "arguments": {"question": "Tell me about his background"}
                }
            }
        )
        assert mcp_res.status_code == 200
        rpc_err = mcp_res.json().get("error")
        assert rpc_err is not None
        assert "Frågekvoten för denna profil har uppnåtts" in rpc_err["message"]


@pytest.mark.asyncio
async def test_mcp_input_sanitization_and_context_stuffing(db_session):
    uid = str(uuid.uuid4())[:8]
    test_app = Application(
        company="Sanitize Test AB",
        role="Security Engineer",
        job_description="Context stuffing defenses",
        token=f"token_sanitize_{uid}",
    )
    db_session.add(test_app)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Unbroken 130-char token stuffing -> should return -32602
        mcp_res_token = await client.post(
            f"/mcp/{test_app.token}",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "ask_about_candidate",
                    "arguments": {"question": "A" * 130}
                }
            }
        )
        assert mcp_res_token.status_code == 200
        assert mcp_res_token.json()["error"]["code"] == -32602
        assert "excessively long token" in mcp_res_token.json()["error"]["message"]

        # 2. Repeated character chain stuffing (e.g. 40 identical letters) -> should return -32602
        mcp_res_repeat = await client.post(
            f"/mcp/{test_app.token}",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "ask_about_candidate",
                    "arguments": {"question": "hello " + "x" * 45}
                }
            }
        )
        assert mcp_res_repeat.status_code == 200
        assert mcp_res_repeat.json()["error"]["code"] == -32602
        assert "abnormal repeated character sequence" in mcp_res_repeat.json()["error"]["message"]


@pytest.mark.asyncio
async def test_device_metadata_size_bounding(db_session):
    uid = str(uuid.uuid4())[:8]
    test_app = Application(
        company="Metadata Test Corp",
        role="Frontend Architect",
        job_description="Device metadata testing",
        token=f"token_meta_{uid}",
    )
    db_session.add(test_app)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Oversized metadata (>4096 bytes)
        huge_metadata = {"bloat": "x" * 5000}
        res_view = await client.post(
            f"/a/{test_app.token}/view",
            json={"device_metadata": huge_metadata}
        )
        assert res_view.status_code == 400
        assert "device_metadata exceeds maximum allowed size" in res_view.json()["detail"]

        res_ask = await client.post(
            f"/a/{test_app.token}/ask",
            json={
                "question": "What is the candidate's tech background?",
                "device_metadata": huge_metadata
            }
        )
        assert res_ask.status_code == 400
        assert "device_metadata exceeds maximum allowed size" in res_ask.json()["detail"]


def make_minimal_pdf() -> bytes:
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, "Test PDF Document")
    c.showPage()
    c.save()
    return buf.getvalue()


@pytest.mark.asyncio
async def test_admin_upload_validation_and_size_caps(db_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Reject non-PDF CV
        fake_cv = io.BytesIO(b"This is plain text pretending to be a CV")
        res_bad_cv = await client.post(
            "/admin/applications",
            data={
                "company": "Validate Bank",
                "role": "CTO",
                "job_description": "Validating uploads"
            },
            files={"cv_file": ("resume.pdf", fake_cv, "application/pdf")}
        )
        assert res_bad_cv.status_code == 400
        assert "missing %PDF- header" in res_bad_cv.json()["detail"]

        # 2. Reject unsupported additional document extension
        valid_pdf_bytes = make_minimal_pdf()
        bad_doc = io.BytesIO(b"malicious script payload")
        res_bad_ext = await client.post(
            "/admin/applications",
            data={
                "company": "Validate Bank",
                "role": "CTO",
                "job_description": "Validating uploads",
                "additional_titles": ["Malicious Script"]
            },
            files={
                "cv_file": ("resume.pdf", io.BytesIO(valid_pdf_bytes), "application/pdf"),
                "additional_files": ("payload.exe", bad_doc, "application/octet-stream")
            }
        )
        assert res_bad_ext.status_code == 400
        assert "unsupported format" in res_bad_ext.json()["detail"]

        # 3. Valid PDF and document upload succeeds
        valid_doc = io.BytesIO(valid_pdf_bytes)
        res_ok = await client.post(
            "/admin/applications",
            data={
                "company": "Success Financial",
                "role": "Chief Technology Officer",
                "job_description": "Fintech leadership",
                "additional_titles": ["Reference Letter"]
            },
            files={
                "cv_file": ("resume.pdf", io.BytesIO(valid_pdf_bytes), "application/pdf"),
                "additional_files": ("ref.pdf", valid_doc, "application/pdf")
            }
        )
        assert res_ok.status_code == 201
        assert res_ok.json()["company"] == "Success Financial"
