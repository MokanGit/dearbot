import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.services.classifier import classify_client
from backend.app.config import settings


def test_client_classifier():
    # ChatGPT
    c_type, c_name = classify_client("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ChatGPT-User/1.0; +https://openai.com/bot)")
    assert c_type == "ai_agent"
    assert c_name == "ChatGPT"

    # Claude
    c_type, c_name = classify_client("ClaudeBot/1.0; +claudebot@anthropic.com")
    assert c_type == "ai_agent"
    assert c_name == "Claude"

    # Perplexity
    c_type, c_name = classify_client("PerplexityBot/1.0 (+https://www.perplexity.ai/perplexitybot)")
    assert c_type == "ai_agent"
    assert c_name == "Perplexity"

    # Googlebot
    c_type, c_name = classify_client("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)")
    assert c_type == "known_bot"
    assert c_name == "Googlebot"

    # Standard Chrome browser
    c_type, c_name = classify_client("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
    assert c_type == "browser"
    assert c_name == "Google Chrome"


@pytest.mark.asyncio
async def test_full_api_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check
        resp = await client.get("/health")
        assert resp.status_code == 200

        # 2. Sync knowledge base
        sync_res = await client.post("/admin/sync")
        assert sync_res.status_code == 200
        assert sync_res.json()["total_documents"] >= 3

        # 3. Create application
        create_payload = {
            "company": "Acme Bank",
            "role": "Chief Technology Officer",
            "job_description": "Fintech executive needed to manage 80+ engineers and oversee cybersecurity & regulatory audits.",
            "notes": "Emphasis on resilience and team leadership"
        }
        app_res = await client.post("/admin/applications", json=create_payload)
        assert app_res.status_code == 201
        app_data = app_res.json()
        token = app_data["token"]
        app_id = app_data["id"]

        assert len(token) >= 24
        assert app_data["profile_url"].endswith(f"/a/{token}")

        # 4. Human browser visits profile
        view_res = await client.get(
            f"/a/{token}/view",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128.0.0.0 Safari/537.36"}
        )
        assert view_res.status_code == 200

        # 5. AI Agent discovers profile.json
        profile_json_res = await client.get(
            f"/a/{token}/profile.json",
            headers={"User-Agent": "ChatGPT-User/1.0 (+https://openai.com/bot)"}
        )
        assert profile_json_res.status_code == 200
        pj_data = profile_json_res.json()
        assert pj_data["name"] == settings.CANDIDATE_NAME
        assert pj_data["capabilities"]["ask"] == f"/a/{token}/ask"
        # Ensure private job description is NOT leaked in profile.json
        assert "job_description" not in pj_data

        # 6. Recruiter / AI Agent asks question via /ask
        ask_payload = {
            "question": "What cybersecurity and regulatory resilience experience does the candidate have?"
        }
        ask_res = await client.post(
            f"/a/{token}/ask",
            json=ask_payload,
            headers={"User-Agent": "ChatGPT-User/1.0 (+https://openai.com/bot)"}
        )
        assert ask_res.status_code == 200
        ask_data = ask_res.json()
        assert ask_data["confidence"] == "high"
        assert len(ask_data["evidence"]) > 0
        assert "request_id" in ask_data

        # 7. Check Admin detail analytics
        detail_res = await client.get(f"/admin/applications/{app_id}")
        assert detail_res.status_code == 200
        detail_data = detail_res.json()

        # Check metrics: 2 views (1 view + 1 profile.json) and 1 question
        assert detail_data["metrics"]["profile_views"] == 2
        assert detail_data["metrics"]["questions_count"] == 1
        assert "ChatGPT" in detail_data["metrics"]["client_breakdown"]

        # Check timeline has all 3 interactions (QUESTION, PROFILE_JSON, PROFILE_VIEW)
        assert len(detail_data["timeline"]) == 3
        question_item = next(t for t in detail_data["timeline"] if t.get("event_type") == "QUESTION")
        assert question_item["client_name"] == "ChatGPT"
        assert question_item["question"] == ask_payload["question"]

        # 8. Test token revocation
        revoke_res = await client.post(f"/admin/applications/{app_id}/revoke")
        assert revoke_res.status_code == 200
        assert revoke_res.json()["status"] == "revoked"

        # Ask question after revocation must return 410 Gone
        revoked_ask = await client.post(f"/a/{token}/ask", json=ask_payload)
        assert revoked_ask.status_code == 410


@pytest.mark.asyncio
async def test_three_tier_ai_discovery_and_get_ask():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create application
        create_res = await client.post(
            "/admin/applications",
            json={
                "company": "Tiered Discovery Corp",
                "role": "Chief Technology Officer",
                "job_description": "Fintech and cloud resilience leadership."
            }
        )
        assert create_res.status_code == 201
        token = create_res.json()["token"]

        # 1. Level 1 - Check profile.json has 3-tier instructions
        profile_res = await client.get(f"/a/{token}/profile.json")
        assert profile_res.status_code == 200
        pdata = profile_res.json()
        assert "instructions_for_ai" in pdata
        instructions = pdata["instructions_for_ai"]
        assert "tier_1_url_get" in instructions
        assert "tier_2_api_post" in instructions
        assert "tier_3_mcp" in instructions
        assert len(instructions["tier_1_url_get"]["ready_to_use_links"]) >= 4

        # 2. Level 1 - GET /a/{token}/ask without q parameter returns discovery catalog
        catalog_res = await client.get(f"/a/{token}/ask")
        assert catalog_res.status_code == 200
        catalog_data = catalog_res.json()
        assert catalog_data["status"] == "ready"
        assert len(catalog_data["suggested_urls"]) >= 4

        # 3. Level 1 - GET /a/{token}/ask?q=... returns factual grounded response
        get_ask_res = await client.get(
            f"/a/{token}/ask?q=What+leadership+experience+does+the+candidate+have",
            headers={"User-Agent": "PerplexityBot/1.0"}
        )
        assert get_ask_res.status_code == 200
        get_ask_data = get_ask_res.json()
        assert "leadership" in get_ask_data["answer"].lower() or "cito" in get_ask_data["answer"].lower()
        assert get_ask_data["confidence"] in ["high", "medium"]
        assert len(get_ask_data["evidence"]) > 0
        assert "request_id" in get_ask_data
