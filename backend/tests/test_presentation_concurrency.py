import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func
from backend.app.main import app
from backend.app.database import AsyncSessionLocal
from backend.app.models import Application, Interaction, Document
from backend.app.services import ai as ai_module
from backend.app.services import telemetry as telemetry_module


@pytest.mark.asyncio
async def test_presentation_session_30_attendees_and_10_webmcp_agents(monkeypatch):
    """
    Simulates a live presentation session behind a shared conference Wi-Fi NAT IP:
    - 30 attendees simultaneously load the CV page (GET /a/{token}/profile.json + POST /a/{token}/view)
    - 10 AI agents simultaneously invoke WebMCP tools (POST /a/{token}/ask with access_method='webmcp')
    Verifies:
    - 100% HTTP 200 success (no 429 rate-limit false positives, no SQLite lock errors)
    - In-flight IP telemetry deduplication executes only 1 external IP lookup for the shared NAT IP
    - All 70 interactions (30 PROFILE_JSON + 30 PROFILE_VIEW + 10 WEBMCP_CALL) are persisted cleanly
    """
    shared_conference_ip = "8.8.8.8"
    from backend.app.config import settings
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    telemetry_module._IP_CACHE.clear()
    telemetry_module._INFLIGHT_LOOKUPS.clear()

    lookup_counter = {"count": 0}

    async def fake_lookup_ip_once(ip_address: str) -> dict:
        lookup_counter["count"] += 1
        await asyncio.sleep(0.05)  # Simulate external geo-IP latency
        res = {
            "reverse_dns": "conference-nat.example.org",
            "country": "Sweden",
            "city": "Stockholm",
            "region": "Stockholm",
            "isp": "Conference WiFi ISP",
            "organization": "Tech Summit Venue",
            "asn": "AS64512",
        }
        telemetry_module._IP_CACHE[ip_address] = res
        return res

    monkeypatch.setattr(telemetry_module, "_lookup_ip_once", fake_lookup_ip_once)

    async def fake_answer_question(self, question: str, application, docs):
        await asyncio.sleep(0.08)  # Simulate concurrent LLM generation window
        return {
            "answer": f"Verified grounded answer for: {question}",
            "evidence": [{"source_title": "Canonical CV", "excerpt": "CTO & Architecture Leadership"}],
            "confidence": "high",
            "model_name": "gemini-3-flash-preview",
        }

    monkeypatch.setattr(ai_module.AnswerSynthesizer, "answer_question", fake_answer_question)

    import uuid
    suffix = uuid.uuid4().hex[:8]
    token = f"presentation_concurrency_tok_{suffix}"
    async with AsyncSessionLocal() as session:
        doc = Document(
            google_file_id=f"presentation_doc_{suffix}",
            filename="01_canonical_cv.md",
            title="Canonical CV",
            content_markdown="Sample Candidate — CTO & Product Technology Executive with cloud architecture and AI governance track record.",
            content_hash=f"hash_{suffix}",
            classification="public",
            is_active=True,
        )
        app_record = Application(
            company="Presentation Demo Corp",
            role="Chief Technology Officer",
            job_description="Executive technology leadership, cloud architecture, and AI governance.",
            token=token,
            cv_version="v1.0",
        )
        session.add(doc)
        session.add(app_record)
        await session.commit()
        app_id = app_record.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"X-Forwarded-For": shared_conference_ip}

        async def simulate_human_attendee(idx: int):
            r_profile, r_view = await asyncio.gather(
                client.get(
                    f"/a/{token}/profile.json",
                    headers={**headers, "User-Agent": f"Mozilla/5.0 (Macintosh; Attendee-{idx})"},
                ),
                client.post(
                    f"/a/{token}/view",
                    json={"device_fingerprint": f"attendee_fp_{idx}"},
                    headers={**headers, "User-Agent": f"Mozilla/5.0 (Macintosh; Attendee-{idx})"},
                ),
            )
            return r_profile, r_view

        async def simulate_webmcp_agent(idx: int):
            tool = "ask_cv" if idx % 2 == 0 else "get_experience"
            return await client.post(
                f"/a/{token}/ask",
                json={
                    "question": f"Agent {idx}: What is the candidate's track record in cloud architecture and leadership?",
                    "access_method": "webmcp",
                    "tool": tool,
                },
                headers={**headers, "User-Agent": f"Claude-User/1.0 WebMCP-Agent-{idx}"},
            )

        attendee_tasks = [simulate_human_attendee(i) for i in range(30)]
        agent_tasks = [simulate_webmcp_agent(i) for i in range(10)]

        results = await asyncio.gather(*attendee_tasks, *agent_tasks)

    attendee_results = results[:30]
    agent_results = results[30:]

    for idx, (r_profile, r_view) in enumerate(attendee_results):
        assert r_profile.status_code == 200, f"Attendee {idx} profile.json failed: {r_profile.text}"
        assert r_view.status_code == 200, f"Attendee {idx} view failed: {r_view.text}"

    for idx, r_ask in enumerate(agent_results):
        assert r_ask.status_code == 200, f"WebMCP Agent {idx} ask failed: {r_ask.text}"
        payload = r_ask.json()
        assert payload["confidence"] == "high"
        assert "Verified grounded answer" in payload["answer"]

    # All 70 requests shared the same conference IP simultaneously — deduplication should perform 1 lookup
    assert lookup_counter["count"] == 1

    # Verify all 70 interactions were persisted without any dropped rows or lock errors
    async with AsyncSessionLocal() as session:
        count_stmt = select(func.count(Interaction.id)).where(Interaction.application_id == app_id)
        total_logged = (await session.execute(count_stmt)).scalar_one()
        assert total_logged == 70
