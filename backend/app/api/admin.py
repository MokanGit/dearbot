import os
import io
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
import json
import mimetypes
import re
import zipfile
from backend.app.database import get_db
from backend.app.models import Application, Interaction, Document, ApplicationDocument, utc_now, generate_token
from backend.app.config import settings
from backend.app.services.google_drive import GoogleDriveService
from backend.app.services.cv_generator import CVGeneratorService
from backend.app.services.auth import verify_admin_token
from backend.app.services.ai import extract_cv_metadata, AnswerSynthesizer
from backend.app.services.cleanup import DataCleanupService
from backend.app.services.job_tailor import (
    normalize_job_url,
    fetch_job_page_and_screenshot,
    analyze_job_posting,
    render_match_analysis_markdown,
    stream_tailored_cv,
    stream_tailored_cover_letter,
    render_markdown_cv_to_pdf_bytes,
    render_markdown_cover_letter_to_pdf_bytes,
)

router = APIRouter(
    prefix="/admin",
    tags=["Admin & Analytics"],
    dependencies=[Depends(verify_admin_token)]
)
drive_service = GoogleDriveService()
cv_generator = CVGeneratorService()
ai_synthesizer = AnswerSynthesizer()


class CreateApplicationRequest(BaseModel):
    company: str
    role: str
    job_description: str
    notes: Optional[str] = None
    cv_version: Optional[str] = "2026-09"


class CreateApplicationFromUrlRequest(BaseModel):
    url: str
    notes: Optional[str] = None
    cv_version: Optional[str] = "2026-10"


@router.post("/sync")
async def sync_knowledge_base(session: AsyncSession = Depends(get_db)):
    """Synchronize the configured local or advanced evidence source."""
    result = await drive_service.sync_documents(session)
    return result


@router.get("/documents")
async def list_documents(session: AsyncSession = Depends(get_db)):
    """Lists all canonical documents currently stored in the knowledge base."""
    stmt = select(Document).order_by(Document.filename)
    docs = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": d.id,
            "title": d.title,
            "filename": d.filename,
            "google_file_id": d.google_file_id,
            "classification": getattr(d, "classification", "internal"),
            "classification_source": getattr(d, "classification_source", "auto_default"),
            "manually_approved_at": d.manually_approved_at.isoformat() if d.manually_approved_at else None,
            "is_active": getattr(d, "is_active", True),
            "content_hash": d.content_hash[:8],
            "last_synced": d.last_synced.isoformat(),
            "character_count": len(d.content_markdown)
        }
        for d in docs
    ]


@router.get("/documents/pre-publication-summary")
async def get_pre_publication_summary(session: AsyncSession = Depends(get_db)):
    """
    Pre-publication security audit endpoint listing exact public documents,
    character counts, estimated token usage, and approval timestamps.
    """
    stmt = select(Document).order_by(Document.filename)
    all_docs = (await session.execute(stmt)).scalars().all()

    active_public = [d for d in all_docs if d.classification == "public" and d.is_active]
    active_internal = [d for d in all_docs if d.classification == "internal" and d.is_active]
    inactive = [d for d in all_docs if not d.is_active]

    total_chars = sum(len(d.content_markdown) for d in active_public)
    est_tokens = int(total_chars / 4)

    return {
        "status": "ready",
        "total_documents": len(all_docs),
        "active_public_count": len(active_public),
        "active_internal_count": len(active_internal),
        "inactive_count": len(inactive),
        "total_public_characters": total_chars,
        "estimated_public_tokens": est_tokens,
        "public_documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "title": d.title,
                "character_count": len(d.content_markdown),
                "estimated_tokens": int(len(d.content_markdown) / 4),
                "classification_source": d.classification_source,
                "manually_approved_at": d.manually_approved_at.isoformat() if d.manually_approved_at else None,
                "last_synced": d.last_synced.isoformat()
            }
            for d in active_public
        ],
        "internal_documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "title": d.title,
                "character_count": len(d.content_markdown),
                "estimated_tokens": int(len(d.content_markdown) / 4),
                "classification_source": d.classification_source,
                "manually_approved_at": d.manually_approved_at.isoformat() if d.manually_approved_at else None,
                "last_synced": d.last_synced.isoformat()
            }
            for d in active_internal
        ]
    }


class UpdateClassificationRequest(BaseModel):
    classification: str  # "public" or "internal"


@router.patch("/documents/{doc_id}/classification")
async def update_document_classification(
    doc_id: str,
    body: UpdateClassificationRequest,
    session: AsyncSession = Depends(get_db)
):
    """Allows an authorized administrator to toggle a document's classification between public and internal with durable approval."""
    stmt = select(Document).where(Document.id == doc_id)
    result = await session.execute(stmt)
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    new_class = body.classification.strip().lower()
    if new_class not in ("public", "internal"):
        raise HTTPException(status_code=400, detail="Classification must be 'public' or 'internal'")

    doc.classification = new_class
    doc.classification_source = "admin_override"
    doc.manually_approved_at = utc_now()
    await session.commit()
    return {
        "status": "success",
        "id": doc.id,
        "title": doc.title,
        "classification": doc.classification,
        "classification_source": doc.classification_source,
        "manually_approved_at": doc.manually_approved_at.isoformat()
    }


@router.get("/applications")
async def list_applications(session: AsyncSession = Depends(get_db)):
    """Lists all created applications with summary analytics and document indicators."""
    stmt = select(Application).order_by(Application.created_at.desc())
    apps = (await session.execute(stmt)).scalars().all()

    response = []
    for app in apps:
        # Aggregate interactions
        views_stmt = select(func.count()).select_from(Interaction).where(
            Interaction.application_id == app.id,
            Interaction.event_type.in_(["PROFILE_VIEW", "PROFILE_JSON"])
        )
        questions_stmt = select(func.count()).select_from(Interaction).where(
            Interaction.application_id == app.id,
            Interaction.event_type == "QUESTION"
        )
        ai_agents_stmt = select(func.count()).select_from(Interaction).where(
            Interaction.application_id == app.id,
            Interaction.client_type == "ai_agent"
        )
        docs_count_stmt = select(func.count()).select_from(ApplicationDocument).where(
            ApplicationDocument.application_id == app.id
        )

        views_count = (await session.execute(views_stmt)).scalar() or 0
        questions_count = (await session.execute(questions_stmt)).scalar() or 0
        ai_agents_count = (await session.execute(ai_agents_stmt)).scalar() or 0
        docs_count = (await session.execute(docs_count_stmt)).scalar() or 0

        response.append({
            "id": app.id,
            "token": app.token,
            "company": app.company,
            "role": app.role,
            "cv_version": app.cv_version,
            "created_at": app.created_at.isoformat(),
            "is_active": app.is_active,
            "profile_url": f"{settings.BASE_URL}/a/{app.token}",
            "pdf_url": f"/admin/applications/{app.id}/pdf",
            "has_cv": bool(app.pdf_path and os.path.exists(app.pdf_path)),
            "has_cover_letter": bool(app.cover_letter_path or app.cover_letter_text),
            "cover_letter_filename": app.cover_letter_filename,
            "documents_count": docs_count,
            "stats": {
                "profile_views": views_count,
                "questions": questions_count,
                "ai_agent_interactions": ai_agents_count
            }
        })

    return response


from fastapi import Request
from backend.app.services.application_logger import ApplicationLoggerService

app_logger = ApplicationLoggerService()


MAX_SINGLE_FILE_SIZE = 50 * 1024 * 1024   # 50 MB
MAX_TOTAL_UPLOAD_SIZE = 200 * 1024 * 1024  # 200 MB
ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".rtf", ".odt", ".png", ".jpg", ".jpeg"}

VALIDATED_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".txt": "text/plain",
    ".rtf": "application/rtf",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[^\w\.-]', '_', os.path.basename(name)).strip()
    return cleaned or "document.pdf"


async def _read_upload_file_bounded(upload_file, max_single: int, current_total: int, max_total: int) -> bytes:
    """
    Reads an uploaded file chunk-by-chunk to prevent unbounded memory allocation,
    enforcing per-file (50 MB) and cumulative request (200 MB) size limits.
    """
    content = bytearray()
    chunk_size = 1024 * 1024  # 1 MB
    filename = getattr(upload_file, "filename", "uploaded_file")
    while True:
        chunk = await upload_file.read(chunk_size)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > max_single:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File '{filename}' exceeds the maximum allowed file size of 50 MB."
            )
        if current_total + len(content) > max_total:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Total uploaded files exceed the maximum allowed cumulative size of 200 MB."
            )
    return bytes(content)


def _validate_upload_content(filename: str, content: bytes) -> str:
    """Validate an allowed document by signature and, where possible, structure."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported document format '{ext or 'unknown'}'.")
    if not content:
        raise HTTPException(status_code=400, detail=f"Uploaded document '{filename}' is empty.")

    valid = False
    try:
        if ext == ".pdf":
            if content.startswith(b"%PDF-"):
                from pypdf import PdfReader
                valid = len(PdfReader(io.BytesIO(content)).pages) > 0
        elif ext in {".jpg", ".jpeg"}:
            valid = content.startswith(b"\xff\xd8\xff") and content.rstrip().endswith(b"\xff\xd9")
        elif ext == ".png":
            valid = content.startswith(b"\x89PNG\r\n\x1a\n") and b"IEND" in content[-32:]
        elif ext == ".rtf":
            valid = content.lstrip().startswith(b"{\\rtf")
        elif ext == ".doc":
            valid = content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
        elif ext in {".docx", ".odt"}:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
                if ext == ".docx":
                    valid = "[Content_Types].xml" in names and "word/document.xml" in names
                else:
                    valid = (
                        "mimetype" in names
                        and archive.read("mimetype")[:128] == b"application/vnd.oasis.opendocument.text"
                    )
        elif ext == ".txt":
            decoded = content.decode("utf-8")
            valid = "\x00" not in decoded
    except (OSError, UnicodeDecodeError, ValueError, zipfile.BadZipFile):
        valid = False

    if not valid:
        raise HTTPException(
            status_code=400,
            detail=f"Uploaded document '{filename}' does not match the expected {ext} file format.",
        )
    return VALIDATED_MIME_TYPES[ext]


def _download_headers() -> dict[str, str]:
    return {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    }


@router.post("/applications", status_code=status.HTTP_201_CREATED)
async def create_application(
    request: Request,
    session: AsyncSession = Depends(get_db)
):
    """
    Creates a new job application:
    1. Generates 128-bit cryptographically random token
    2. If candidate attaches a manual PDF CV, stamps the unique URL and metadata into it
    3. Handles Cover Letter (uploaded document or direct text)
    4. Handles arbitrary Additional Documents (certificates, references, transcripts)
    5. Logs the application in the applications folder following _application template
    6. Returns profile URL, PDF download URL, and document summary
    """
    content_type = request.headers.get("content-type", "")
    attached_pdf_bytes = None
    attached_filename = None
    cover_letter_file = None
    cover_letter_text = None
    additional_files = []
    additional_titles = []
    cumulative_bytes = 0

    if "multipart/form-data" in content_type:
        try:
            form = await request.form()
        except Exception as form_err:
            print(f"Error reading multipart form: {form_err}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Could not parse uploaded files: {form_err}. Please ensure file sizes are within 50MB."
            )

        company = str(form.get("company", "")).strip()
        role = str(form.get("role", "")).strip()
        job_description = str(form.get("job_description", "")).strip()
        notes = str(form.get("notes", "")).strip() if form.get("notes") else None
        cv_version = str(form.get("cv_version", "2026-09"))
        cover_letter_text = str(form.get("cover_letter_text", "")).strip() or None

        # CV file
        file_upload = form.get("cv_file")
        if file_upload and hasattr(file_upload, "read") and getattr(file_upload, "filename", ""):
            attached_filename = getattr(file_upload, "filename", "attached_cv.pdf")
            attached_pdf_bytes = await _read_upload_file_bounded(
                file_upload,
                max_single=MAX_SINGLE_FILE_SIZE,
                current_total=cumulative_bytes,
                max_total=MAX_TOTAL_UPLOAD_SIZE
            )
            cumulative_bytes += len(attached_pdf_bytes)

            # Validate that uploaded CV is a genuine readable PDF
            if not attached_pdf_bytes.startswith(b"%PDF-"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Uploaded CV '{attached_filename}' is not a valid PDF file (missing %PDF- header)."
                )
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(attached_pdf_bytes))
                if len(reader.pages) == 0:
                    raise ValueError("Empty PDF")
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Uploaded CV '{attached_filename}' is corrupt or unreadable as a PDF."
                )

        # Cover letter file
        cl_upload = form.get("cover_letter_file")
        if cl_upload and hasattr(cl_upload, "read") and getattr(cl_upload, "filename", ""):
            cl_name = getattr(cl_upload, "filename", "")
            cl_ext = os.path.splitext(cl_name)[1].lower()
            if cl_ext and cl_ext not in ALLOWED_DOCUMENT_EXTENSIONS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cover letter format '{cl_ext}' is not supported. Allowed: {', '.join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))}"
                )
            cover_letter_file = cl_upload

        # Additional documents
        raw_add_files = form.getlist("additional_files") or form.getlist("additional_files[]")
        for f in raw_add_files:
            if hasattr(f, "read") and getattr(f, "filename", ""):
                doc_name = getattr(f, "filename", "")
                doc_ext = os.path.splitext(doc_name)[1].lower()
                if doc_ext and doc_ext not in ALLOWED_DOCUMENT_EXTENSIONS:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Document '{doc_name}' has unsupported format '{doc_ext}'. Allowed: {', '.join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))}"
                    )
                additional_files.append(f)

        raw_titles = form.getlist("additional_titles") or form.getlist("additional_titles[]")
        additional_titles = [str(t).strip() for t in raw_titles if str(t).strip()]
    else:
        body = await request.json()
        company = str(body.get("company", "")).strip()
        role = str(body.get("role", "")).strip()
        job_description = str(body.get("job_description", "")).strip()
        notes = str(body.get("notes", "")).strip() if body.get("notes") else None
        cv_version = str(body.get("cv_version", "2026-09"))
        cover_letter_text = str(body.get("cover_letter_text", "")).strip() or None

    if not company or not role or not job_description:
        raise HTTPException(status_code=400, detail="Company, role, and job_description are required")

    token = generate_token()
    app_media_dir = os.path.join("backend", "data", "applications_media", token)
    os.makedirs(app_media_dir, exist_ok=True)

    # 1. Generate custom PDF CV (stamping candidate's attached PDF with URL & metadata tag if provided)
    pdf_path = cv_generator.generate_cv(
        token=token,
        company=company,
        role=role,
        attached_pdf_bytes=attached_pdf_bytes
    )

    # 2. Handle Cover Letter
    cover_letter_path = None
    cover_letter_filename = None
    extracted_cl_text = ""
    if cover_letter_file:
        cl_raw_name = getattr(cover_letter_file, "filename", "cover_letter.pdf")
        cl_ext = os.path.splitext(cl_raw_name)[1].lower()
        if cl_ext and cl_ext not in ALLOWED_DOCUMENT_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cover letter format '{cl_ext}' is not supported. Allowed: {', '.join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))}"
            )

        cl_filename = _safe_filename(cl_raw_name)
        cl_dest = os.path.join(app_media_dir, f"cover_letter_{cl_filename}")
        cl_bytes = await _read_upload_file_bounded(
            cover_letter_file,
            max_single=MAX_SINGLE_FILE_SIZE,
            current_total=cumulative_bytes,
            max_total=MAX_TOTAL_UPLOAD_SIZE
        )
        cumulative_bytes += len(cl_bytes)
        _validate_upload_content(cl_raw_name, cl_bytes)

        with open(cl_dest, "wb") as f:
            f.write(cl_bytes)
        cover_letter_path = cl_dest
        cover_letter_filename = getattr(cover_letter_file, "filename", cl_filename)

        if cl_ext == ".pdf":
            try:
                from pypdf import PdfReader
                cl_reader = PdfReader(io.BytesIO(cl_bytes))
                extracted_cl_text = "\n".join([page.extract_text() or "" for page in cl_reader.pages])
            except Exception as e:
                print(f"Could not extract text from cover letter PDF: {e}")
        elif cl_ext in [".txt", ".rtf", ".odt"]:
            try:
                extracted_cl_text = cl_bytes.decode("utf-8", errors="ignore")
            except Exception:
                pass

    # 3. Extract CV metadata (candidate name & title) from submitted/generated CV
    cv_meta = extract_cv_metadata(attached_pdf_bytes or pdf_path)
    candidate_name = cv_meta.get("name") or settings.CANDIDATE_NAME
    candidate_headline = cv_meta.get("headline") or settings.CANDIDATE_HEADLINE

    # 4. Generate cover letter summary & fit highlights
    effective_cl_text = cover_letter_text or extracted_cl_text or None
    cl_summary_data = await ai_synthesizer.generate_cover_letter_summary(
        cover_letter_text=effective_cl_text,
        role=role,
        company=company,
        job_description=job_description
    )
    cover_letter_summary_json = json.dumps(cl_summary_data)

    # 5. Generate dynamic suggested questions derived from job requirements
    suggested_q_list = await ai_synthesizer.generate_suggested_questions(
        job_description=job_description,
        role=role,
        company=company,
        candidate_name=candidate_name
    )
    suggested_questions_json = json.dumps(suggested_q_list)

    # 6. Log application in application folder following the _application template
    log_path = app_logger.log_application(
        token=token,
        company=company,
        role=role,
        job_description=job_description,
        notes=notes,
        attached_filename=attached_filename
    )

    app = Application(
        token=token,
        company=company,
        role=role,
        job_description=job_description,
        notes=notes,
        cv_version=cv_version,
        pdf_path=pdf_path,
        cover_letter_path=cover_letter_path,
        cover_letter_filename=cover_letter_filename,
        cover_letter_text=cover_letter_text or (extracted_cl_text if extracted_cl_text else None),
        candidate_name=candidate_name,
        candidate_headline=candidate_headline,
        cover_letter_summary=cover_letter_summary_json,
        suggested_questions=suggested_questions_json,
        created_at=utc_now()
    )
    session.add(app)
    await session.flush()

    # 4. Handle Additional Documents
    added_docs = []
    for idx, doc_file in enumerate(additional_files):
        doc_filename_raw = getattr(doc_file, "filename", f"document_{idx+1}.pdf")
        doc_ext = os.path.splitext(doc_filename_raw)[1].lower()
        if doc_ext and doc_ext not in ALLOWED_DOCUMENT_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Document '{doc_filename_raw}' has unsupported format '{doc_ext}'. Allowed: {', '.join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))}"
            )

        doc_filename = _safe_filename(doc_filename_raw)
        title = additional_titles[idx] if idx < len(additional_titles) and additional_titles[idx] else os.path.splitext(doc_filename_raw)[0]
        dest_path = os.path.join(app_media_dir, f"doc_{idx+1}_{doc_filename}")
        content = await _read_upload_file_bounded(
            doc_file,
            max_single=MAX_SINGLE_FILE_SIZE,
            current_total=cumulative_bytes,
            max_total=MAX_TOTAL_UPLOAD_SIZE
        )
        cumulative_bytes += len(content)
        validated_mime = _validate_upload_content(doc_filename_raw, content)

        with open(dest_path, "wb") as f:
            f.write(content)

        file_size = len(content)
        doc_model = ApplicationDocument(
            application_id=app.id,
            title=title,
            filename=doc_filename_raw,
            file_path=dest_path,
            file_size=file_size,
            mime_type=validated_mime,
            created_at=utc_now()
        )
        session.add(doc_model)
        added_docs.append(doc_model)

    await session.commit()
    await session.refresh(app)

    return {
        "id": app.id,
        "token": app.token,
        "company": app.company,
        "role": app.role,
        "profile_url": f"{settings.BASE_URL}/a/{app.token}",
        "pdf_download_url": f"/admin/applications/{app.id}/pdf",
        "cover_letter_download_url": f"/admin/applications/{app.id}/cover-letter" if (app.cover_letter_path or app.cover_letter_text) else None,
        "has_cv": True,
        "has_cover_letter": bool(app.cover_letter_path or app.cover_letter_text),
        "cover_letter_filename": app.cover_letter_filename,
        "additional_documents_count": len(added_docs),
        "application_log": log_path,
        "created_at": app.created_at.isoformat()
    }


@router.post("/applications/from-url-stream")
async def create_application_from_url_stream(
    body: CreateApplicationFromUrlRequest,
    session: AsyncSession = Depends(get_db),
):
    """
    Streams real-time progress (SSE) while:
    1. Fetching the job advertisement webpage and capturing a live screendump
    2. Analyzing the role, company, language, and key requirements
    3. Generating and streaming an optimal, role-tailored CV (PDF stamped with /a/{token})
    4. Generating and streaming a tailored Personal Letter / Cover Letter (PDF + text)
    5. Saving the complete Application package to the database
    """
    try:
        normalized_url = normalize_job_url(body.url)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    notes = (body.notes or "").strip() or None
    cv_version = (body.cv_version or "2026-10").strip()

    async def event_generator():
        def _sse(payload: dict) -> str:
            return f"data: {json.dumps(payload)}\n\n"

        try:
            # Step 1: Fetch webpage & capture screendump
            yield _sse({
                "type": "status",
                "step": "fetching_page",
                "progress": 10,
                "message": "Fetching job ad webpage & capturing live screendump...",
            })
            page_data = await fetch_job_page_and_screenshot(normalized_url)
            yield _sse({
                "type": "screendump",
                "step": "fetching_page",
                "progress": 24,
                "url": page_data["url"],
                "domain": page_data["domain"],
                "page_title": page_data["page_title"],
                "site_name": page_data["site_name"],
                "screenshot_data_url": page_data["screenshot_data_url"],
                "message": f"Captured webpage snapshot from {page_data['domain']}",
            })

            # Step 2: Analyze job requirements & positioning
            yield _sse({
                "type": "status",
                "step": "analyzing_job",
                "progress": 32,
                "message": "Extracting company, role, language & key requirements...",
            })
            job_info = await analyze_job_posting(page_data, custom_notes=notes)
            company = job_info["company"]
            role = job_info["role"]
            job_description = job_info["clean_job_description"]

            yield _sse({
                "type": "job_analyzed",
                "step": "analyzing_job",
                "progress": 44,
                "company": company,
                "role": role,
                "language": job_info["language"],
                "positioning_angle": job_info["positioning_angle"],
                "role_fit_proposition": job_info.get("role_fit_proposition", ""),
                "key_requirements": job_info["key_requirements"],
                "ats_priority_skills": job_info.get("ats_priority_skills", []),
                "message": f"Target identified: {role} at {company} ({job_info['positioning_angle']})",
            })

            # Load canonical documents (syncing from local synced_docs if DB is empty)
            doc_stmt = select(Document).where(Document.is_active == True)
            docs = list((await session.execute(doc_stmt)).scalars().all())
            if not docs:
                await drive_service.sync_documents(session)
                docs = list((await session.execute(doc_stmt)).scalars().all())

            # Step 3: Stream Tailored CV creation & stamp PDF
            yield _sse({
                "type": "status",
                "step": "generating_cv",
                "progress": 50,
                "message": f"Crafting optimal tailored CV for {role} at {company}...",
            })
            cv_markdown = ""
            async for item in stream_tailored_cv(job_info, docs, custom_notes=notes):
                if item.get("type") == "cv_chunk":
                    chars = item.get("chars", 0)
                    prog = min(69, 50 + int(chars / 280))
                    yield _sse({
                        "type": "cv_stream",
                        "step": "generating_cv",
                        "progress": prog,
                        "delta": item.get("delta", ""),
                        "section": item.get("section", "Tailored CV"),
                        "chars": chars,
                        "message": f"Writing CV — {item.get('section', 'Profile')} ({chars} chars)...",
                    })
                elif item.get("type") == "cv_done":
                    cv_markdown = item.get("markdown", "")

            token = generate_token()
            app_media_dir = os.path.join("backend", "data", "applications_media", token)
            os.makedirs(app_media_dir, exist_ok=True)

            # Save Job Description, Match Analysis, and Tailored CV markdown sources
            jd_md_path = os.path.join(app_media_dir, "01_Job_Description.md")
            with open(jd_md_path, "w", encoding="utf-8") as f:
                f.write(f"# Job Advertisement — {role} at {company}\n\n- **Source URL:** {normalized_url}\n\n{job_description}\n")

            match_md_path = os.path.join(app_media_dir, "02_Match_Analysis.md")
            with open(match_md_path, "w", encoding="utf-8") as f:
                f.write(render_match_analysis_markdown(job_info, normalized_url))

            cv_md_path = os.path.join(app_media_dir, "03_Tailored_CV.md")
            with open(cv_md_path, "w", encoding="utf-8") as f:
                f.write(cv_markdown)

            raw_cv_pdf_bytes = render_markdown_cv_to_pdf_bytes(cv_markdown)
            pdf_path = cv_generator.generate_cv(
                token=token,
                company=company,
                role=role,
                attached_pdf_bytes=raw_cv_pdf_bytes,
            )

            yield _sse({
                "type": "cv_ready",
                "step": "generating_cv",
                "progress": 73,
                "chars": len(cv_markdown),
                "markdown": cv_markdown,
                "message": "Tailored CV PDF rendered & digitally stamped with verification link.",
            })

            # Step 4: Stream Tailored Cover Letter / Personal Letter creation
            yield _sse({
                "type": "status",
                "step": "generating_cover_letter",
                "progress": 76,
                "message": f"Drafting tailored Personal Letter for {company}...",
            })
            cl_markdown = ""
            async for item in stream_tailored_cover_letter(
                job_info, cv_markdown, docs, custom_notes=notes
            ):
                if item.get("type") == "cl_chunk":
                    chars = item.get("chars", 0)
                    prog = min(90, 76 + int(chars / 180))
                    yield _sse({
                        "type": "cl_stream",
                        "step": "generating_cover_letter",
                        "progress": prog,
                        "delta": item.get("delta", ""),
                        "chars": chars,
                        "message": f"Drafting Personal Letter ({chars} chars)...",
                    })
                elif item.get("type") == "cl_done":
                    cl_markdown = item.get("markdown", "")

            cl_md_path = os.path.join(app_media_dir, "04_Cover_Letter.md")
            with open(cl_md_path, "w", encoding="utf-8") as f:
                f.write(cl_markdown)

            safe_comp = _safe_filename(company.replace(" ", "_"))
            cover_letter_filename = f"Personal_Letter_{settings.CANDIDATE_NAME.replace(' ', '_')}_{safe_comp}.pdf"
            cover_letter_path = os.path.join(app_media_dir, f"cover_letter_{cover_letter_filename}")
            cl_pdf_bytes = render_markdown_cover_letter_to_pdf_bytes(
                cl_markdown, company=company, role=role
            )
            with open(cover_letter_path, "wb") as f:
                f.write(cl_pdf_bytes)

            yield _sse({
                "type": "cl_ready",
                "step": "generating_cover_letter",
                "progress": 93,
                "chars": len(cl_markdown),
                "markdown": cl_markdown,
                "message": "Personal Letter PDF & inline recruiter text ready.",
            })

            # Step 5: Finalize package, fit highlights, suggested questions & DB save
            yield _sse({
                "type": "status",
                "step": "finalizing",
                "progress": 96,
                "message": "Generating executive fit highlights & finalizing application package...",
            })

            cv_meta = extract_cv_metadata(raw_cv_pdf_bytes)
            md_headline = None
            for md_line in cv_markdown.splitlines():
                stripped_md = md_line.replace("\xa0", " ").strip()
                if stripped_md.startswith("## ") and not stripped_md.upper().startswith("## EXECUTIVE") and not stripped_md.upper().startswith("## SAMMANFATTNING"):
                    candidate_h = re.sub(r"[\s\-–—:|]+$", "", stripped_md[3:].strip())
                    if len(candidate_h) >= 8:
                        md_headline = candidate_h
                        break
            candidate_name = cv_meta.get("name") or settings.CANDIDATE_NAME
            candidate_headline = md_headline or cv_meta.get("headline") or settings.CANDIDATE_HEADLINE

            cl_summary_data = await ai_synthesizer.generate_cover_letter_summary(
                cover_letter_text=cl_markdown,
                role=role,
                company=company,
                job_description=job_description,
            )
            suggested_q_list = await ai_synthesizer.generate_suggested_questions(
                job_description=job_description,
                role=role,
                company=company,
                candidate_name=candidate_name,
            )

            combined_notes = f"Source URL: {normalized_url}"
            if notes:
                combined_notes += f" | Notes: {notes}"

            log_path = app_logger.log_application(
                token=token,
                company=company,
                role=role,
                job_description=job_description,
                notes=combined_notes,
                attached_filename=f"Tailored_CV_{safe_comp}.pdf",
            )

            app = Application(
                token=token,
                company=company,
                role=role,
                job_description=job_description,
                notes=combined_notes,
                cv_version=cv_version,
                pdf_path=pdf_path,
                cover_letter_path=cover_letter_path,
                cover_letter_filename=cover_letter_filename,
                cover_letter_text=cl_markdown,
                candidate_name=candidate_name,
                candidate_headline=candidate_headline,
                cover_letter_summary=json.dumps(cl_summary_data),
                suggested_questions=json.dumps(suggested_q_list),
                created_at=utc_now(),
            )
            session.add(app)
            await session.commit()
            await session.refresh(app)

            yield _sse({
                "type": "completed",
                "step": "completed",
                "progress": 100,
                "message": "Application package ready!",
                "result": {
                    "id": app.id,
                    "token": app.token,
                    "company": app.company,
                    "role": app.role,
                    "language": job_info["language"],
                    "positioning_angle": job_info["positioning_angle"],
                    "profile_url": f"{settings.BASE_URL}/a/{app.token}",
                    "pdf_download_url": f"/admin/applications/{app.id}/pdf",
                    "cover_letter_download_url": f"/admin/applications/{app.id}/cover-letter",
                    "has_cv": True,
                    "has_cover_letter": True,
                    "cover_letter_filename": app.cover_letter_filename,
                    "cover_letter_text": cl_markdown,
                    "cv_markdown": cv_markdown,
                    "additional_documents_count": 0,
                    "application_log": log_path,
                    "created_at": app.created_at.isoformat(),
                },
            })
        except Exception as exc:
            print(f"Error in create_application_from_url_stream: {exc}")
            yield _sse({
                "type": "error",
                "step": "error",
                "message": f"Failed to generate application from URL: {exc}",
            })

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/applications/{application_id}")
async def get_application_detail(
    application_id: str,
    session: AsyncSession = Depends(get_db)
):
    """Detailed analytics for a specific application: views, question timeline, client breakdown, documents."""
    stmt = select(Application).where(Application.id == application_id)
    app = (await session.execute(stmt)).scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    # Fetch all interactions
    int_stmt = select(Interaction).where(
        Interaction.application_id == app.id
    ).order_by(Interaction.timestamp.desc())
    interactions = (await session.execute(int_stmt)).scalars().all()

    # Fetch all attached additional documents
    docs_stmt = select(ApplicationDocument).where(
        ApplicationDocument.application_id == app.id
    ).order_by(ApplicationDocument.created_at.asc())
    attached_docs = (await session.execute(docs_stmt)).scalars().all()

    # Metrics
    profile_views = 0
    questions_count = 0
    client_counts = {}
    question_timeline = []

    organizations = set()

    for item in interactions:
        client_label = item.client_name or item.client_type or "Unknown"
        client_counts[client_label] = client_counts.get(client_label, 0) + 1

        if item.organization and item.organization not in ["Local / Private Network", "Internal"]:
            organizations.add(item.organization)

        if item.event_type in ["PROFILE_VIEW", "PROFILE_JSON"]:
            profile_views += 1
        elif item.event_type == "QUESTION":
            questions_count += 1

        parsed_device = None
        if item.device_metadata:
            try:
                parsed_device = json.loads(item.device_metadata)
            except Exception:
                parsed_device = None

        question_timeline.append({
            "id": item.id,
            "timestamp": item.timestamp.isoformat(),
            "event_type": item.event_type,
            "question": item.question,
            "answer": item.answer,
            "confidence": item.confidence,
            "client_type": item.client_type,
            "client_name": item.client_name or "Unknown Client",
            "request_id": item.request_id,
            "ip_address": item.ip_address,
            "organization": item.organization,
            "geo_country": item.geo_country,
            "geo_city": item.geo_city,
            "reverse_dns": item.reverse_dns,
            "isp": item.isp,
            "asn": item.asn,
            "referer": item.referer,
            "accept_language": item.accept_language,
            "device_fingerprint": item.device_fingerprint,
            "device_metadata": parsed_device
        })

    documents_list = [
        {
            "id": d.id,
            "title": d.title,
            "filename": d.filename,
            "file_size": d.file_size,
            "mime_type": d.mime_type,
            "created_at": d.created_at.isoformat(),
            "download_url": f"/admin/applications/{app.id}/documents/{d.id}"
        }
        for d in attached_docs
    ]

    return {
        "application": {
            "id": app.id,
            "token": app.token,
            "company": app.company,
            "role": app.role,
            "job_description": app.job_description,
            "notes": app.notes,
            "cv_version": app.cv_version,
            "created_at": app.created_at.isoformat(),
            "is_active": app.is_active,
            "profile_url": f"{settings.BASE_URL}/a/{app.token}",
            "pdf_url": f"/admin/applications/{app.id}/pdf",
            "has_cv": bool(app.pdf_path and os.path.exists(app.pdf_path)),
            "cover_letter": {
                "has_file": bool(app.cover_letter_path and os.path.exists(app.cover_letter_path)),
                "filename": app.cover_letter_filename,
                "text": app.cover_letter_text,
                "download_url": f"/admin/applications/{app.id}/cover-letter" if (app.cover_letter_path or app.cover_letter_text) else None,
            } if (app.cover_letter_path or app.cover_letter_text) else None,
            "candidate": {
                "name": app.candidate_name or settings.CANDIDATE_NAME,
                "headline": app.candidate_headline or settings.CANDIDATE_HEADLINE
            },
            "cover_letter_summary": json.loads(app.cover_letter_summary) if app.cover_letter_summary else None,
            "suggested_questions": json.loads(app.suggested_questions) if app.suggested_questions else None,
            "additional_documents": documents_list
        },
        "metrics": {
            "profile_views": profile_views,
            "questions_count": questions_count,
            "client_breakdown": client_counts,
            "organizations": sorted(list(organizations))
        },
        "timeline": question_timeline
    }


@router.post("/applications/{application_id}/revoke")
async def revoke_application(
    application_id: str,
    session: AsyncSession = Depends(get_db)
):
    """
    Immediately revokes an application token and permanently purges all visitor
    interaction telemetry in accordance with the application lifecycle privacy policy.
    """
    stmt = select(Application).where(Application.id == application_id)
    app = (await session.execute(stmt)).scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    app.revoked_at = utc_now()

    # Purge all visitor interaction telemetry immediately upon deactivation
    await session.execute(delete(Interaction).where(Interaction.application_id == app.id))

    await session.commit()
    return {
        "status": "revoked",
        "application_id": app.id,
        "revoked_at": app.revoked_at.isoformat(),
        "telemetry_purged": True
    }


@router.delete("/applications/{identifier}")
async def delete_application(
    identifier: str,
    session: AsyncSession = Depends(get_db)
):
    """
    Permanently deletes an application record, removes associated files on disk,
    and purges all visitor interaction telemetry (identified by UUID or Token).
    """
    stmt = select(Application).where(
        (Application.id == identifier) | (Application.token == identifier)
    )
    app = (await session.execute(stmt)).scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    return await DataCleanupService.delete_application_permanently(app, session)


@router.post("/cleanup")
async def run_data_cleanup(
    retention_days: int = 30,
    session: AsyncSession = Depends(get_db)
):
    """
    Executes 30-day post-revocation data lifecycle retention cleanup.
    """
    return await DataCleanupService.cleanup_expired_revoked_applications(
        session, retention_days=retention_days
    )


@router.get("/applications/{application_id}/pdf")
async def download_cv_pdf(
    application_id: str,
    session: AsyncSession = Depends(get_db)
):
    """Streams the generated PDF CV for the given application."""
    stmt = select(Application).where(Application.id == application_id)
    app = (await session.execute(stmt)).scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if not app.pdf_path or not os.path.exists(app.pdf_path):
        # Regenerate on the fly if missing
        app.pdf_path = cv_generator.generate_cv(app.token, app.company, app.role)
        await session.commit()

    candidate_slug = re.sub(r"[^A-Za-z0-9_-]+", "_", settings.CANDIDATE_NAME).strip("_") or "Candidate"
    company_slug = re.sub(r"[^A-Za-z0-9_-]+", "_", app.company).strip("_") or "Application"
    filename = f"CV_{candidate_slug}_{company_slug}.pdf"
    return FileResponse(
        path=app.pdf_path,
        filename=filename,
        media_type="application/pdf",
        headers=_download_headers(),
    )


@router.get("/applications/{application_id}/cover-letter")
async def download_cover_letter(
    application_id: str,
    session: AsyncSession = Depends(get_db)
):
    """Streams the uploaded cover letter or text file for the given application."""
    stmt = select(Application).where(Application.id == application_id)
    app = (await session.execute(stmt)).scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if app.cover_letter_path and os.path.exists(app.cover_letter_path):
        candidate_slug = re.sub(r"[^A-Za-z0-9_-]+", "_", settings.CANDIDATE_NAME).strip("_") or "Candidate"
        company_slug = re.sub(r"[^A-Za-z0-9_-]+", "_", app.company).strip("_") or "Application"
        filename = app.cover_letter_filename or f"Cover_Letter_{candidate_slug}_{company_slug}.pdf"
        mime, _ = mimetypes.guess_type(filename)
        return FileResponse(
            path=app.cover_letter_path,
            filename=filename,
            media_type=mime or "application/pdf",
            headers=_download_headers(),
        )
    elif app.cover_letter_text:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(app.cover_letter_text)
    else:
        raise HTTPException(status_code=404, detail="No cover letter found for this application")


@router.get("/applications/{application_id}/documents/{doc_id}")
async def download_additional_document(
    application_id: str,
    doc_id: str,
    session: AsyncSession = Depends(get_db)
):
    """Streams an attached additional document for the given application."""
    stmt = select(ApplicationDocument).where(
        ApplicationDocument.id == doc_id,
        ApplicationDocument.application_id == application_id
    )
    doc = (await session.execute(stmt)).scalar_one_or_none()
    if not doc or not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="Document not found")

    return FileResponse(
        path=doc.file_path,
        filename=doc.filename,
        media_type=doc.mime_type or "application/octet-stream",
        headers=_download_headers(),
    )
