import io
import pytest
from httpx import AsyncClient, ASGITransport
from reportlab.pdfgen import canvas
from pypdf import PdfReader
from sqlalchemy import select

from backend.app.main import app
from backend.app.database import AsyncSessionLocal
from backend.app.models import Application, Interaction, ApplicationDocument


def _make_sample_pdf(text: str = "Sample CV") -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 700, text)
    c.save()
    buf.seek(0)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_application_documents_full_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create a dummy CV PDF, Cover Letter PDF, and Additional Document PDF
        cv_bytes = _make_sample_pdf("Sample Candidate - Executive CV")
        cl_bytes = _make_sample_pdf("Personal Cover Letter for Acme Corp")
        doc1_bytes = _make_sample_pdf("Reference Letter from Previous CEO")
        doc2_bytes = _make_sample_pdf("ISO 27001 Lead Auditor Certificate")

        # 2. Upload via multipart form
        files = [
            ("cv_file", ("sample_candidate_cv.pdf", cv_bytes, "application/pdf")),
            ("cover_letter_file", ("acme_cover_letter.pdf", cl_bytes, "application/pdf")),
            ("additional_files", ("reference_ceo.pdf", doc1_bytes, "application/pdf")),
            ("additional_files", ("cert_iso27001.pdf", doc2_bytes, "application/pdf")),
        ]
        data = {
            "company": "Acme Nordic",
            "role": "Chief Technology Officer",
            "job_description": "Lead technology strategy and engineering scale.",
            "notes": "Recruiter expressed strong interest in security & DORA experience.",
            "additional_titles": ["Reference Letter - CEO", "ISO 27001 Certificate"],
        }

        create_res = await client.post("/admin/applications", data=data, files=files)
        assert create_res.status_code == 201, create_res.text
        res_data = create_res.json()

        token = res_data["token"]
        app_id = res_data["id"]
        assert res_data["has_cv"] is True
        assert res_data["has_cover_letter"] is True
        assert res_data["additional_documents_count"] == 2

        # 3. Query public info endpoint
        info_res = await client.get(f"/a/{token}/info")
        assert info_res.status_code == 200
        info_data = info_res.json()
        assert info_data["company"] == "Acme Nordic"
        assert info_data["role"] == "Chief Technology Officer"
        docs_info = info_data["documents"]
        assert docs_info["has_cv"] is True
        assert docs_info["has_cover_letter"] is True
        assert len(docs_info["additional_documents"]) == 2
        assert docs_info["additional_documents"][0]["title"] == "Reference Letter - CEO"
        assert docs_info["additional_documents"][1]["title"] == "ISO 27001 Certificate"

        doc1_id = docs_info["additional_documents"][0]["id"]
        doc2_id = docs_info["additional_documents"][1]["id"]

        # 4. Download CV and verify the tag was stamped
        cv_download_res = await client.get(f"/a/{token}/cv")
        assert cv_download_res.status_code == 200
        assert cv_download_res.headers["content-type"] == "application/pdf"
        assert cv_download_res.headers["x-content-type-options"] == "nosniff"
        assert cv_download_res.headers["cache-control"] == "private, no-store"
        reader = PdfReader(io.BytesIO(cv_download_res.content))
        metadata = reader.metadata
        assert token in str(metadata) or "/a/" in str(metadata)

        # 5. Download Cover Letter
        cl_download_res = await client.get(f"/a/{token}/cover-letter")
        assert cl_download_res.status_code == 200
        assert cl_download_res.headers["content-type"] == "application/pdf"
        assert len(cl_download_res.content) > 0

        # 6. Download Additional Document
        doc1_download_res = await client.get(f"/a/{token}/documents/{doc1_id}")
        assert doc1_download_res.status_code == 200
        assert doc1_download_res.headers["content-type"] == "application/pdf"
        assert "attachment" in doc1_download_res.headers["content-disposition"].lower()
        assert doc1_download_res.headers["x-content-type-options"] == "nosniff"
        assert len(doc1_download_res.content) > 0

        # 7. Verify interaction telemetry logged in database
        async with AsyncSessionLocal() as session:
            events_stmt = select(Interaction.event_type).where(Interaction.application_id == app_id)
            logged_events = (await session.execute(events_stmt)).scalars().all()
            assert "CV_DOWNLOAD" in logged_events
            assert "COVER_LETTER_DOWNLOAD" in logged_events
            assert "DOCUMENT_DOWNLOAD" in logged_events


@pytest.mark.asyncio
async def test_rejects_mismatched_upload_content():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/admin/applications",
            data={
                "company": "Example Corp",
                "role": "Engineering Lead",
                "job_description": "Lead a software engineering team.",
            },
            files=[
                ("additional_files", ("not-really-a-document.pdf", b"<script>alert(1)</script>", "application/pdf")),
            ],
        )

    assert response.status_code == 400
    assert "does not match" in response.json()["detail"]
