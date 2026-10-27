import pytest
import io
import os
from httpx import AsyncClient, ASGITransport
from reportlab.pdfgen import canvas
from pypdf import PdfReader
from backend.app.main import app
from backend.app.config import settings


def create_sample_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(595, 842))
    c.drawString(50, 800, "Sample Candidate - Manual Custom CV")
    c.drawString(50, 780, "Technology Executive & Strategic Leader")
    c.save()
    buf.seek(0)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_attached_cv_stamping_and_template_logging():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a mock manually crafted PDF CV
        sample_cv_bytes = create_sample_pdf()

        files = {
            "cv_file": ("sample_candidate_cv.pdf", sample_cv_bytes, "application/pdf")
        }
        data = {
            "company": "Nordic Enterprise Bank",
            "role": "Head of Engineering & Resilience",
            "job_description": "Fintech and large-scale transformation leadership.",
            "notes": "Emphasize DORA compliance and team management."
        }

        res = await client.post("/admin/applications", data=data, files=files)
        assert res.status_code == 201
        res_data = res.json()

        token = res_data["token"]
        app_id = res_data["id"]
        log_path = res_data["application_log"]

        # 1. Verify application log file was created following _application template
        assert os.path.exists(log_path)
        with open(log_path, "r", encoding="utf-8") as f:
            log_content = f.read()
        assert "Nordic Enterprise Bank" in log_content
        assert "Head of Engineering & Resilience" in log_content
        assert token in log_content
        assert "sample_candidate_cv.pdf" in log_content

        # 2. Download the augmented PDF and verify stamping
        pdf_res = await client.get(f"/admin/applications/{app_id}/pdf")
        assert pdf_res.status_code == 200
        reader = PdfReader(io.BytesIO(pdf_res.content))

        # Check that original text remains
        page_text = reader.pages[0].extract_text()
        assert "Sample Candidate - Manual Custom CV" in page_text

        # Check that unique URL footer was stamped
        expected_url = f"{settings.BASE_URL}/a/{token}"
        assert expected_url in page_text
        assert "Extended profile & supporting evidence:" in page_text

        # Check metadata
        metadata = reader.metadata
        assert f"Extended professional profile: {expected_url}" in metadata.subject


@pytest.mark.asyncio
async def test_attached_cv_multi_page_and_additional_docs():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a 2-page PDF with custom mediabox
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(612, 792))
        c.drawString(50, 750, "Page 1 - Candidate Header")
        c.showPage()
        c.drawString(50, 750, "Page 2 - Candidate References & Signature")
        c.save()
        two_page_cv_bytes = buf.getvalue()

        cl_buf = io.BytesIO()
        cl_c = canvas.Canvas(cl_buf, pagesize=(612, 792))
        cl_c.drawString(50, 750, "Cover Letter Content for Hiring Manager")
        cl_c.save()
        cl_bytes = cl_buf.getvalue()

        ref_doc_bytes = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF"

        files = [
            ("cv_file", ("CV_HOLM_CTO.pdf", two_page_cv_bytes, "application/pdf")),
            ("cover_letter_file", ("Cover_Letter.pdf", cl_bytes, "application/pdf")),
            ("additional_files", ("Reference_Letter.pdf", ref_doc_bytes, "application/pdf")),
        ]
        data = {
            "company": "Example Security",
            "role": "Chief Technology Officer",
            "job_description": "Global scale security platform leadership.",
            "notes": "Direct interview candidate package.",
            "additional_titles": ["CEO Recommendation Letter"]
        }

        res = await client.post("/admin/applications", data=data, files=files)
        assert res.status_code == 201
        res_data = res.json()

        assert res_data["has_cv"] is True
        assert res_data["has_cover_letter"] is True
        assert res_data["additional_documents_count"] == 1

        app_id = res_data["id"]
        pdf_res = await client.get(f"/admin/applications/{app_id}/pdf")
        assert pdf_res.status_code == 200
        reader = PdfReader(io.BytesIO(pdf_res.content))
        assert len(reader.pages) == 2
        last_page_text = reader.pages[1].extract_text()
        assert "Extended profile & supporting evidence:" in last_page_text
