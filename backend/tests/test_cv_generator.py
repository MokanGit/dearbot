import os
from pypdf import PdfReader
from backend.app.services.cv_generator import CVGeneratorService
from backend.app.config import settings


def test_cv_generation_and_metadata():
    generator = CVGeneratorService()
    test_token = "test_token_128bit_entropy_abc123"
    company = "Acme Bank"
    role = "CTO"

    pdf_path = generator.generate_cv(test_token, company, role)
    assert os.path.exists(pdf_path)
    assert os.path.getsize(pdf_path) > 1000

    # Inspect generated PDF
    reader = PdfReader(pdf_path)
    assert len(reader.pages) >= 1

    # Verify visible text contains candidate name and company/role
    page_text = reader.pages[0].extract_text()
    assert settings.CANDIDATE_NAME in page_text
    assert company in page_text
    assert role in page_text
    assert test_token in page_text

    # Verify P0 requirement: visible link text
    expected_url = f"{settings.BASE_URL}/a/{test_token}"
    assert expected_url in page_text

    # Verify PDF metadata
    metadata = reader.metadata
    assert metadata is not None
    assert metadata.author == settings.CANDIDATE_NAME
    assert f"Extended professional profile: {expected_url}" in metadata.subject
    assert "DearBot" in metadata.get("/Keywords", "")

    # Clean up test file
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
