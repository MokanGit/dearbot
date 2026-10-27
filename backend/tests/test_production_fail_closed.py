import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.config import settings
from backend.app.models import Application, Document, utc_now
from backend.app.services.ai import AnswerSynthesizer, UnavailableLLMProvider, MockLLMProvider


@pytest.mark.asyncio
async def test_production_fails_closed_without_synthetic_fallback(db_session):
    # Set to production mode with no API keys
    orig_env = settings.ENV
    orig_gemini_key = settings.GEMINI_API_KEY
    orig_openai_key = settings.OPENAI_API_KEY
    settings.ENV = "production"
    settings.GEMINI_API_KEY = None
    settings.OPENAI_API_KEY = None

    try:
        synthesizer = AnswerSynthesizer()
        # Must select UnavailableLLMProvider, NEVER MockLLMProvider
        assert isinstance(synthesizer.provider, UnavailableLLMProvider)
        assert not isinstance(synthesizer.provider, MockLLMProvider)

        # Setup test app and doc
        uid = str(uuid.uuid4())[:8]
        app_record = Application(
            company="FailClosed Bank",
            role="Chief Information Security Officer",
            job_description="Security leadership",
            token=f"token_fc_{uid}",
        )
        doc = Document(
            google_file_id=f"g_fc_{uid}",
            title="Overview",
            filename="overview.md",
            content_markdown="# Cybersecurity\nISMS and ISO 27001",
            content_hash=f"hash_fc_{uid}",
            classification="public",
            last_modified=utc_now(),
            last_synced=utc_now(),
        )
        db_session.add(app_record)
        db_session.add(doc)
        await db_session.commit()

        # 1. Answer question directly via synthesizer
        res = await synthesizer.answer_question("Tell me about cybersecurity", app_record, [doc])
        assert res["status"] == "service_unavailable"
        assert res["confidence"] == "unavailable"
        assert "AI reasoning service is temporarily unavailable" in res["answer"]
        # Must NOT contain hardcoded mock strings
        assert "extensive cybersecurity and resilience leadership experience" not in res["answer"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 2. Test REST POST /a/{token}/ask
            post_res = await client.post(
                f"/a/{app_record.token}/ask",
                json={"question": "What is his experience in cybersecurity?"}
            )
            assert post_res.status_code == 200
            data = post_res.json()
            assert data["confidence"] == "unavailable"
            assert "AI reasoning service is temporarily unavailable" in data["answer"]
            assert len(data["evidence"]) == 0

            # 3. Test MCP tools/call ask_about_candidate returns JSON-RPC -32000
            mcp_res = await client.post(
                f"/mcp/{app_record.token}",
                json={
                    "jsonrpc": "2.0",
                    "id": 101,
                    "method": "tools/call",
                    "params": {
                        "name": "ask_about_candidate",
                        "arguments": {"question": "What is his experience in cybersecurity?"}
                    }
                }
            )
            assert mcp_res.status_code == 200
            mcp_data = mcp_res.json()
            assert "error" in mcp_data
            assert mcp_data["error"]["code"] == -32000
            assert "AI reasoning service is temporarily unavailable" in mcp_data["error"]["message"]

            # 4. Test /health reflects degraded status and misconfigured LLM
            health_res = await client.get("/health")
            assert health_res.status_code == 200
            hdata = health_res.json()
            assert hdata["status"] == "degraded"
            assert hdata["environment"] == "production"
            assert hdata["llm"]["status"] == "misconfigured"
            assert hdata["llm"]["configured"] is False

    finally:
        settings.ENV = orig_env
        settings.GEMINI_API_KEY = orig_gemini_key
        settings.OPENAI_API_KEY = orig_openai_key


@pytest.mark.asyncio
async def test_health_check_healthy_when_configured(db_session):
    orig_env = settings.ENV
    orig_llm_provider = settings.LLM_PROVIDER
    orig_gemini_key = settings.GEMINI_API_KEY
    settings.ENV = "production"
    settings.LLM_PROVIDER = "gemini"
    settings.GEMINI_API_KEY = "test_mock_gemini_key"

    try:
        # Ensure at least one public doc exists
        uid = str(uuid.uuid4())[:8]
        doc = Document(
            google_file_id=f"g_health_{uid}",
            title="Public Overview",
            filename=f"overview_{uid}.md",
            content_markdown="# Public Profile",
            content_hash=f"hash_h_{uid}",
            classification="public",
            last_modified=utc_now(),
            last_synced=utc_now(),
        )
        db_session.add(doc)
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            health_res = await client.get("/health")
            assert health_res.status_code == 200
            hdata = health_res.json()
            assert hdata["status"] == "healthy"
            assert hdata["llm"]["status"] == "operational"
            assert hdata["llm"]["configured"] is True
            assert hdata["corpus"]["public_documents_count"] >= 1
    finally:
        settings.ENV = orig_env
        settings.LLM_PROVIDER = orig_llm_provider
        settings.GEMINI_API_KEY = orig_gemini_key
