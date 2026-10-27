import pytest
import os
from httpx import AsyncClient, ASGITransport
from pypdf import PdfReader
from backend.app.main import app
from backend.app.config import settings


@pytest.mark.asyncio
async def test_full_acceptance_scenario():
    """
    Direct verification of Section 36 & 37 from the MVP Brief:
    1. Candidate updates/syncs professional material.
    2. Candidate creates: Company: Acme Bank, Role: CTO, Job Description: ...
    3. System generates: unique URL https://.../a/{token}
    4. System generates PDF CV containing that visible URL and metadata.
    5. Recruiter or AI opens URL.
    6. Visitor asks about the candidate's regulated-technology experience.
    7. System retrieves factual evidence without hallucination.
    8. Supporting sources shown.
    9. Candidate sees the question, timestamp and AI client in Acme Bank dashboard.
    10. Another application (AI Director) uses identical factual KB but role-specific lens.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 1: Sync Knowledge Base
        sync_res = await client.post("/admin/sync")
        assert sync_res.status_code == 200
        sync_data = sync_res.json()
        assert sync_data["total_documents"] >= 3

        # Step 2 & 3: Create Application A (Acme Bank - CTO)
        app_a_payload = {
            "company": "Acme Bank",
            "role": "CTO",
            "job_description": "Fintech and regulated banking environment requiring large-scale engineering leadership and resilience.",
            "notes": "Highlight regulatory resilience and cloud migration"
        }
        res_a = await client.post("/admin/applications", json=app_a_payload)
        assert res_a.status_code == 201
        app_a = res_a.json()
        token_a = app_a["token"]
        id_a = app_a["id"]

        # Step 4: Verify Generated PDF CV contains visible URL and metadata
        pdf_res = await client.get(f"/admin/applications/{id_a}/pdf")
        assert pdf_res.status_code == 200
        pdf_bytes = pdf_res.content

        # Inspect PDF content
        import io
        reader = PdfReader(io.BytesIO(pdf_bytes))
        page_text = reader.pages[0].extract_text()
        expected_url_a = f"{settings.BASE_URL}/a/{token_a}"
        assert expected_url_a in page_text
        assert "Extended profile & supporting evidence" in page_text
        assert "Acme Bank" in page_text

        # Inspect PDF metadata
        assert f"Extended professional profile: {expected_url_a}" in reader.metadata.subject

        # Step 5: Recruiter visits profile (human browser)
        await client.get(
            f"/a/{token_a}/view",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128.0.0.0 Safari/537.36"}
        )

        # AI Agent (ChatGPT) discovers profile.json
        pj_res = await client.get(
            f"/a/{token_a}/profile.json",
            headers={"User-Agent": "ChatGPT-User/1.0 (+https://openai.com/bot)"}
        )
        assert pj_res.status_code == 200
        assert pj_res.json()["capabilities"]["ask"] == f"/a/{token_a}/ask"

        # Step 6, 7 & 8: AI Agent asks about regulated tech leadership
        ask_payload = {
            "question": "What experience does the candidate have running technology in regulated organisations?"
        }
        ask_res = await client.post(
            f"/a/{token_a}/ask",
            json=ask_payload,
            headers={"User-Agent": "ChatGPT-User/1.0 (+https://openai.com/bot)"}
        )
        assert ask_res.status_code == 200
        ask_data = ask_res.json()
        assert ask_data["confidence"] == "high"
        assert "fictional sample evidence" in ask_data["answer"].lower()
        assert len(ask_data["evidence"]) > 0
        assert any(k in e["source_title"] for e in ask_data["evidence"] for k in ["Experience", "Overview", "CV", "Cv"])

        # Step 9: Candidate inspects Acme Bank dashboard
        detail_res = await client.get(f"/admin/applications/{id_a}")
        assert detail_res.status_code == 200
        detail = detail_res.json()

        assert detail["metrics"]["profile_views"] == 2  # 1 view + 1 profile.json
        assert detail["metrics"]["questions_count"] == 1
        assert detail["metrics"]["client_breakdown"]["ChatGPT"] == 2  # 1 profile.json + 1 ask
        assert detail["timeline"][0]["question"] == ask_payload["question"]
        assert detail["timeline"][0]["client_name"] == "ChatGPT"

        # Step 10: Create Application B (Example AI - Director of AI)
        app_b_payload = {
            "company": "Example AI",
            "role": "Director of AI",
            "job_description": "Enterprise AI governance and machine learning deployments."
        }
        res_b = await client.post("/admin/applications", json=app_b_payload)
        assert res_b.status_code == 201
        app_b = res_b.json()
        token_b = app_b["token"]

        # Tokens and URLs must be unique
        assert token_a != token_b
        assert app_a["profile_url"] != app_b["profile_url"]

        # Asking undocumented question on Application B must not hallucinate
        res_undoc = await client.post(
            f"/a/{token_b}/ask",
            json={"question": "What nuclear reactor physics experience does the candidate have?"}
        )
        assert res_undoc.status_code == 200
        assert res_undoc.json()["confidence"] == "unavailable"
        assert "No verified evidence was found for this specific claim." in res_undoc.json()["answer"]
