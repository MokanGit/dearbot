import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from backend.app.main import app
from backend.app.models import Application, Document, utc_now
from backend.app.services.google_drive import classify_document, GoogleDriveService


def test_document_classification_rules():
    assert classify_document("CTO-CIO Job Search Strategy - Sample Candidate.md", "Job Search Strategy") == "internal"
    assert classify_document("CV Tailoring Rules - Sample Candidate.md", "CV Tailoring Rules") == "internal"
    assert classify_document("CV Master Evidence Bank - Sample Candidate.md", "Master Evidence Bank") == "internal"
    assert classify_document("README - CV Tailoring System.md", "README System") == "internal"
    assert classify_document("Master CV - Review Copy - Sample Candidate.md", "Review Copy") == "internal"

    assert classify_document("01_executive_overview.md", "Executive Overview & Leadership Profile") == "public"
    assert classify_document("02_selected_experience.md", "Example Financial Services — CITO") == "public"
    assert classify_document("03_ai_and_data_governance.md", "AI & Data Governance Experience") == "public"
    assert classify_document("04_cybersecurity_and_grc.md", "Cybersecurity, Operational Resilience & GRC") == "public"


@pytest.mark.asyncio
async def test_mcp_get_evidence_blocks_internal_and_bounds_public(db_session):
    import uuid
    uid = str(uuid.uuid4())[:8]

    # Setup test application
    app_record = Application(
        company="Nordic Security Bank",
        role="Chief Information Security Officer",
        job_description="Enterprise security and DORA leadership",
        token=f"token_sec_{uid}",
    )
    db_session.add(app_record)

    # Insert one internal document and one public document
    internal_doc = Document(
        google_file_id=f"g_internal_strat_{uid}",
        title="Job Search Strategy & Target Salaries",
        filename="CTO-CIO Job Search Strategy - Sample Candidate.md",
        content_markdown="# Confidential Strategy\nTarget compensation: 2.5M SEK. Do not disclose.\n" * 50,
        content_hash=f"hash_strat_{uid}",
        classification="internal",
        last_modified=utc_now(),
        last_synced=utc_now(),
    )
    public_doc = Document(
        google_file_id=f"g_public_exec_{uid}",
        title=f"Executive Leadership Profile {uid}",
        filename="01_executive_overview.md",
        content_markdown="# Sample Candidate Executive Profile\n\nSample Candidate is a seasoned technology executive and CITO.\n\n" + ("Extensive track record leading large-scale cloud migrations and regulatory compliance.\n\n" * 20),
        content_hash=f"hash_pub_{uid}",
        classification="public",
        last_modified=utc_now(),
        last_synced=utc_now(),
    )
    db_session.add(internal_doc)
    db_session.add(public_doc)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. MCP get_evidence on internal document -> Must be blocked
        mcp_req_internal = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "get_evidence",
                "arguments": {"source_title": "strategy"}
            }
        }
        res = await client.post(f"/mcp/token_sec_{uid}", json=mcp_req_internal)
        assert res.status_code == 200
        content_text = res.json()["result"]["content"][0]["text"]
        assert "Evidence document not found or access restricted" in content_text
        assert "Confidential Strategy" not in content_text
        assert "2.5M SEK" not in content_text

        # 2. MCP get_evidence on public document -> Allowed and strictly bounded
        mcp_req_public = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "get_evidence",
                "arguments": {"source_title": uid}
            }
        }
        res_pub = await client.post(f"/mcp/token_sec_{uid}", json=mcp_req_public)
        assert res_pub.status_code == 200
        pub_text = res_pub.json()["result"]["content"][0]["text"]
        assert "Verified Public Evidence" in pub_text
        assert len(pub_text) <= 1500
        assert "Evidence bounded to approved public excerpt" in pub_text


@pytest.mark.asyncio
async def test_admin_toggle_document_classification(db_session):
    import uuid
    uid = str(uuid.uuid4())[:8]
    doc = Document(
        google_file_id=f"g_toggle_{uid}",
        title="Engineering Overview",
        filename=f"engineering_{uid}.md",
        content_markdown="# Engineering Overview\nDetails here.",
        content_hash=f"hash_eng_{uid}",
        classification="internal",
        last_modified=utc_now(),
        last_synced=utc_now(),
    )
    db_session.add(doc)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Toggle from internal to public
        res = await client.patch(
            f"/admin/documents/{doc.id}/classification",
            json={"classification": "public"}
        )
        assert res.status_code == 200
        assert res.json()["classification"] == "public"

        # Verify in DB
        await db_session.refresh(doc)
        assert doc.classification == "public"
