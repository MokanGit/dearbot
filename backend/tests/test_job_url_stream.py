import io
import json
import pytest
from httpx import AsyncClient, ASGITransport
from pypdf import PdfReader

from backend.app.main import app
from backend.app.services.job_tailor import normalize_job_url, _validate_public_http_url


@pytest.mark.asyncio
async def test_create_application_from_url_stream_full_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/admin/applications/from-url-stream",
            json={
                "url": "https://careers.example.com/jobs/chief-technology-officer",
                "notes": "Start the personal letter with a funny Norwegian joke (Swedish Norgehistoria) that is relevant to the role",
            },
        )
        assert res.status_code == 200
        assert "text/event-stream" in res.headers.get("content-type", "")

        events = []
        for raw_block in res.text.split("\n\n"):
            for line in raw_block.splitlines():
                if line.startswith("data:"):
                    events.append(json.loads(line[5:].strip()))

        event_types = [e.get("type") for e in events]
        assert "screendump" in event_types
        assert "job_analyzed" in event_types
        assert "cv_stream" in event_types
        assert "cv_ready" in event_types
        assert "cl_stream" in event_types
        assert "cl_ready" in event_types
        assert "completed" in event_types

        screendump_evt = next(e for e in events if e.get("type") == "screendump")
        assert screendump_evt["domain"] == "careers.example.com"
        assert screendump_evt["screenshot_data_url"].startswith("data:image/")

        analyzed_evt = next(e for e in events if e.get("type") == "job_analyzed")
        assert analyzed_evt.get("role_fit_proposition")
        assert isinstance(analyzed_evt.get("ats_priority_skills"), list)
        assert len(analyzed_evt["ats_priority_skills"]) > 0

        completed_evt = next(e for e in events if e.get("type") == "completed")
        result = completed_evt["result"]
        app_id = result["id"]
        token = result["token"]
        assert result["has_cv"] is True
        assert result["has_cover_letter"] is True
        assert f"/a/{token}" in result["profile_url"]

        # Verify Stamped Tailored CV PDF download
        cv_res = await client.get(f"/admin/applications/{app_id}/pdf")
        assert cv_res.status_code == 200
        assert cv_res.content.startswith(b"%PDF-")
        cv_reader = PdfReader(io.BytesIO(cv_res.content))
        assert len(cv_reader.pages) >= 1
        assert token in str(cv_reader.metadata) or "/a/" in str(cv_reader.metadata)

        # Verify Tailored Cover Letter (Personal Letter) PDF download
        cl_res = await client.get(f"/admin/applications/{app_id}/cover-letter")
        assert cl_res.status_code == 200
        assert cl_res.content.startswith(b"%PDF-")
        cl_reader = PdfReader(io.BytesIO(cl_res.content))
        assert len(cl_reader.pages) >= 1

        # Verify public profile.json includes cover letter metadata and Norgehistoria text
        pub_profile = await client.get(f"/a/{token}/profile.json")
        assert pub_profile.status_code == 200
        pub_data = pub_profile.json()
        assert pub_data["documents"]["has_cover_letter"] is True
        assert "Norgehistoria" in (pub_data["documents"]["cover_letter_text"] or "")
        assert not pub_data["headline"].endswith("-")

        # Clean up test application
        del_res = await client.delete(f"/admin/applications/{app_id}")
        assert del_res.status_code == 200


@pytest.mark.asyncio
async def test_create_application_from_url_rejects_empty_url():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/admin/applications/from-url-stream",
            json={"url": "   "},
        )
        assert res.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://[::1]/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost/internal",
    ],
)
async def test_job_url_rejects_private_and_metadata_destinations(url):
    with pytest.raises(ValueError, match="Local and private"):
        await _validate_public_http_url(url)


def test_job_url_rejects_credentials_and_nonstandard_ports():
    with pytest.raises(ValueError, match="credentials"):
        normalize_job_url("https://user:password@example.com/job")
    with pytest.raises(ValueError, match="standard HTTP"):
        normalize_job_url("https://example.com:8443/job")
