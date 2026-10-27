import io
import json
import pytest
from httpx import AsyncClient, ASGITransport
from reportlab.pdfgen import canvas
from pypdf import PdfReader

from backend.app.main import app
from backend.app.services.ai import (
    extract_cv_metadata,
    generate_default_cover_letter_summary,
    generate_default_suggested_questions,
    AnswerSynthesizer
)
from backend.app.config import settings


def _make_sample_cv_pdf(name: str, headline: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 750, name)
    c.drawString(72, 730, headline)
    c.drawString(72, 700, "Executive with 15+ years of engineering and leadership experience.")
    c.save()
    buf.seek(0)
    return buf.getvalue()


def _make_sample_cover_letter_pdf(content: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 750, "Cover Letter")
    c.drawString(72, 720, content)
    c.save()
    buf.seek(0)
    return buf.getvalue()


def _make_candidate_cv_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 780, "CV – Sample Candidate page 1")
    c.drawString(72, 760, "CV – Sample Candidate")
    c.drawString(72, 730, "Name: Sample Candidate")
    c.drawString(72, 715, "Address: Example Street 12, 111 22 Stockholm")
    c.drawString(72, 700, "E-mail: alex.morgan@example.com")
    c.drawString(72, 685, "Phone: +46 70 000 00 00")
    c.drawString(72, 670, "LinkedIn: https://www.linkedin.com/in/example-alex/")
    c.drawString(72, 640, "CTO & Product Technology Executive")
    c.drawString(72, 620, "Senior CTO/CIO and product-technology leader with executive responsibility for technology organizations...")
    c.save()
    buf.seek(0)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_extract_candidate_cv_header_and_tagline():
    cv_bytes = _make_candidate_cv_pdf()
    meta = extract_cv_metadata(cv_bytes)
    assert meta["name"] == "Sample Candidate"
    assert meta["headline"] == "CTO & Product Technology Executive"


@pytest.mark.asyncio
async def test_extract_cv_metadata_custom_pdf():
    cv_bytes = _make_sample_cv_pdf("Elin Lindqvist", "VP of Engineering & Cloud Architecture")
    meta = extract_cv_metadata(cv_bytes)
    assert meta["name"] == "Elin Lindqvist"
    assert "Engineering" in meta["headline"] or "Cloud" in meta["headline"]


@pytest.mark.asyncio
async def test_extract_cv_metadata_fallback():
    meta = extract_cv_metadata(b"")
    assert meta["name"] == settings.CANDIDATE_NAME
    assert meta["headline"] == settings.CANDIDATE_HEADLINE


@pytest.mark.asyncio
async def test_generate_cover_letter_summary():
    summary_data = generate_default_cover_letter_summary(
        cover_letter_text="I am writing to express my strong interest in the VP Engineering role at TechCorp. I have extensive background in scaling distributed teams, zero trust cybersecurity, and AWS cloud migrations.",
        role="VP Engineering",
        company="TechCorp",
        job_description="Seeking a leader with deep cloud architecture, cybersecurity, and team scaling track record."
    )
    assert "summary" in summary_data
    assert isinstance(summary_data["fit_highlights"], list)
    assert 3 <= len(summary_data["fit_highlights"]) <= 5
    bullets_text = " ".join(summary_data["fit_highlights"])
    assert "Leadership" in bullets_text or "Security" in bullets_text or "Architecture" in bullets_text


@pytest.mark.asyncio
async def test_generate_suggested_questions_from_requirements():
    questions = generate_default_suggested_questions(
        job_description="Requirements: 1. Deep expertise in banking and credit management regulations. 2. Hands-on experience with DORA compliance and cybersecurity. 3. Leading cloud transformations.",
        role="Head of Technology",
        company="Nordic Bank",
        candidate_name="Sample Candidate"
    )
    assert isinstance(questions, list)
    assert len(questions) == 4
    joined = " ".join(questions)
    assert "Sample" in joined
    assert "financial" in joined.lower() or "banking" in joined.lower() or "cybersecurity" in joined.lower() or "cloud" in joined.lower()


@pytest.mark.asyncio
async def test_recruiter_endpoints_with_cv_and_cover_letter():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create an application with attached custom CV and Cover Letter
        cv_bytes = _make_sample_cv_pdf("Sample Candidate", "Chief Information & Technology Officer")
        cl_bytes = _make_sample_cover_letter_pdf("Application statement highlighting technology governance and resilience.")

        files = [
            ("cv_file", ("custom_cv.pdf", cv_bytes, "application/pdf")),
            ("cover_letter_file", ("cover_letter.pdf", cl_bytes, "application/pdf")),
        ]
        data = {
            "company": "Fintech Global",
            "role": "Chief Information Officer",
            "job_description": "Must have extensive banking regulation, DORA resilience, and cloud migration background.",
            "notes": "Recruiter is focused on DORA audit readiness."
        }
        create_res = await client.post("/admin/applications", data=data, files=files)
        assert create_res.status_code == 201
        res_json = create_res.json()
        token = res_json["token"]

        # 1. Test GET /a/{token}/info
        info_res = await client.get(f"/a/{token}/info")
        assert info_res.status_code == 200
        info_data = info_res.json()

        assert info_data["candidate"]["name"] == "Sample Candidate"
        assert "Chief Information" in info_data["candidate"]["headline"] or "Technology" in info_data["candidate"]["headline"]
        
        # Verify cover letter summary and 3-5 fit highlights
        cl_summary = info_data.get("cover_letter_summary")
        assert cl_summary is not None
        assert "summary" in cl_summary
        assert isinstance(cl_summary["fit_highlights"], list)
        assert 3 <= len(cl_summary["fit_highlights"]) <= 5

        # Verify suggested questions derived from requirements
        sq = info_data.get("suggested_questions")
        assert sq is not None
        assert len(sq) == 4
        assert any("cybersecurity" in q.lower() or "resilience" in q.lower() or "financial" in q.lower() or "banking" in q.lower() for q in sq)

        # 2. Test GET /a/{token}/profile.json
        prof_res = await client.get(f"/a/{token}/profile.json")
        assert prof_res.status_code == 200
        prof_data = prof_res.json()
        assert prof_data["name"] == "Sample Candidate"
        assert len(prof_data["suggested_questions"]) == 4

        # 3. Test GET /a/{token}/ask catalog
        ask_catalog_res = await client.get(f"/a/{token}/ask")
        assert ask_catalog_res.status_code == 200
        catalog_data = ask_catalog_res.json()
        assert "suggested_urls" in catalog_data
        assert len(catalog_data["suggested_urls"]) == 4


@pytest.mark.asyncio
async def test_custom_candidate_name_from_cv():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        cv_bytes = _make_sample_cv_pdf("Sofia Bergström", "Principal Cloud Architect & VP Engineering")
        files = [
            ("cv_file", ("sofia_cv.pdf", cv_bytes, "application/pdf")),
        ]
        data = {
            "company": "ScaleTech AB",
            "role": "Chief Technology Officer",
            "job_description": "We require experience in Kubernetes, AWS, distributed team leadership, and high-load payments.",
        }

        create_res = await client.post("/admin/applications", data=data, files=files)
        assert create_res.status_code == 201
        res_json = create_res.json()
        token = res_json["token"]

        # Check /info
        info_res = await client.get(f"/a/{token}/info")
        assert info_res.status_code == 200
        info_data = info_res.json()
        assert info_data["candidate"]["name"] == "Sofia Bergström"
        assert "Principal Cloud Architect" in info_data["candidate"]["headline"]

        # Check /profile.json
        prof_res = await client.get(f"/a/{token}/profile.json")
        assert prof_res.status_code == 200
        prof_data = prof_res.json()
        assert prof_data["name"] == "Sofia Bergström"

        # Check /view
        view_res = await client.post(f"/a/{token}/view", json={})
        assert view_res.status_code == 200
        view_data = view_res.json()
        assert view_data["candidate"]["name"] == "Sofia Bergström"
