import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from backend.app.main import app
from backend.app.database import AsyncSessionLocal
from backend.app.models import Interaction, Application


@pytest.mark.asyncio
async def test_webmcp_end_to_end():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Sync knowledge base
        sync_res = await client.post("/admin/sync")
        assert sync_res.status_code == 200

        # 2. Create application token
        create_res = await client.post("/admin/applications", json={
            "company": "Nordic Resilient Bank",
            "role": "Chief Information Officer",
            "job_description": "Executive leadership in DORA, banking resilience, and team scaling.",
            "notes": "Testing WebMCP"
        })
        assert create_res.status_code == 201
        token = create_res.json()["token"]

        # 3. Test profile.json discovery schema for WebMCP Tier 4 & documents metadata
        profile_res = await client.get(f"/a/{token}/profile.json")
        assert profile_res.status_code == 200
        pdata = profile_res.json()
        assert "webmcp" in pdata["capabilities"]
        assert "tier_4_webmcp" in pdata["instructions_for_ai"]
        assert pdata["instructions_for_ai"]["tier_4_webmcp"]["primary_tool"] == "ask_cv"
        assert "ask_cv" in pdata["instructions_for_ai"]["tier_4_webmcp"]["tools"]
        assert "documents" in pdata
        assert "evaluation_context" in pdata
        assert not pdata["headline"].endswith("-")

        # 4. Test WebMCP invocation via POST /a/{token}/ask with explicit access_method="webmcp"
        webmcp_payload = {
            "question": "Has the candidate worked with DORA?",
            "access_method": "webmcp",
            "tool": "ask_cv"
        }
        ask_res = await client.post(f"/a/{token}/ask", json=webmcp_payload)
        assert ask_res.status_code == 200
        data = ask_res.json()
        assert "answer" in data
        assert len(data["answer"]) > 10
        assert "evidence" in data
        assert "confidence" in data
        assert data.get("source") == "cv-assistant"
        assert "request_id" in data

        # 4b. Test unsupported-claim challenge returns clean no-evidence response
        unsupported_res = await client.post(
            f"/a/{token}/ask",
            json={
                "question": "Did the candidate build Mars rockets at SpaceX in 2019?",
                "access_method": "webmcp",
                "tool": "ask_cv",
            },
        )
        assert unsupported_res.status_code == 200
        udata = unsupported_res.json()
        assert udata["answer"] == "No verified evidence was found for this specific claim."
        assert udata["confidence"] == "unavailable"
        assert udata["evidence"] == []
        assert udata["source"] == "cv-assistant"

        # 5. Verify interaction was recorded in database with access_method="webmcp" and tool="ask_cv"
        async with AsyncSessionLocal() as session:
            stmt = select(Interaction).where(Interaction.request_id == data["request_id"])
            interaction = (await session.execute(stmt)).scalar_one_or_none()
            assert interaction is not None
            assert interaction.access_method == "webmcp"
            assert interaction.tool == "ask_cv"
            assert interaction.event_type == "WEBMCP_CALL"
            assert interaction.latency_ms is not None
            assert interaction.latency_ms >= 0
            assert interaction.client_type == "ai_agent"

        # 6. Test WebMCP invocation using X-Access-Method HTTP header
        header_payload = {
            "question": "What cybersecurity and zero trust experience does he have?"
        }
        ask_hdr_res = await client.post(
            f"/a/{token}/ask",
            json=header_payload,
            headers={"X-Access-Method": "webmcp"}
        )
        assert ask_hdr_res.status_code == 200
        hdr_data = ask_hdr_res.json()
        async with AsyncSessionLocal() as session:
            stmt = select(Interaction).where(Interaction.request_id == hdr_data["request_id"])
            interaction = (await session.execute(stmt)).scalar_one_or_none()
            assert interaction is not None
            assert interaction.access_method == "webmcp"
            assert interaction.tool == "ask_cv"

        # 7. Test token isolation: invalid/unknown token returns 404
        bad_token_res = await client.post(
            "/a/invalid_token_12345/ask",
            json={"question": "Who is the candidate?", "access_method": "webmcp"}
        )
        assert bad_token_res.status_code == 404

        # 8. Test error handling: empty/blank question returns 400
        empty_q_res = await client.post(
            f"/a/{token}/ask",
            json={"question": "   ", "access_method": "webmcp"}
        )
        assert empty_q_res.status_code == 400
