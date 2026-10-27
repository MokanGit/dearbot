import asyncio
import json
import time
import os
import mimetypes
import re
import urllib.parse
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Header, Query
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.database import get_db, AsyncSessionLocal, commit_interaction
from backend.app.models import Application, Interaction, Document, ApplicationDocument, utc_now, generate_uuid
from backend.app.config import settings
from backend.app.services.classifier import classify_client
from backend.app.services.ai import (
    AnswerSynthesizer, 
    generate_default_cover_letter_summary, 
    generate_default_suggested_questions
)
from backend.app.services.google_drive import GoogleDriveService
from backend.app.services.security import (
    validate_and_sanitize_question,
    rate_limiter,
    get_client_ip,
    verify_application_quota
)
from backend.app.services.telemetry import enrich_ip_intelligence

router = APIRouter(prefix="/a", tags=["Public Profile & AI Discovery"])
synthesizer = AnswerSynthesizer()
drive_service = GoogleDriveService()


def _download_headers() -> dict[str, str]:
    return {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    }


class AskRequest(BaseModel):
    question: str
    access_method: Optional[str] = None  # "web", "get", "api", "mcp", "webmcp"
    tool: Optional[str] = None  # "ask_cv", "get_cv_summary", etc.
    device_fingerprint: Optional[str] = None
    device_metadata: Optional[dict] = None


class ViewRequest(BaseModel):
    device_fingerprint: Optional[str] = None
    device_metadata: Optional[dict] = None


class EvidenceItem(BaseModel):
    source_title: str
    excerpt: str


class AskResponse(BaseModel):
    answer: str
    evidence: list[EvidenceItem]
    confidence: str
    request_id: str
    model_name: Optional[str] = None
    source: str = "cv-assistant"


def _clean_public_headline(text: Optional[str]) -> str:
    import re
    raw = (text or settings.CANDIDATE_HEADLINE or "").replace("\xa0", " ").strip()
    cleaned = re.sub(r"[\s\-–—:|]+$", "", raw).strip()
    return cleaned or settings.CANDIDATE_HEADLINE


async def get_valid_application(token: str, session: AsyncSession) -> Application:
    stmt = select(Application).where(Application.token == token)
    app = (await session.execute(stmt)).scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application profile not found")
    if not app.is_active:
        raise HTTPException(status_code=410, detail="This profile link has been revoked or expired")
    return app


async def _extract_request_telemetry(request: Request) -> dict:
    client_ip = get_client_ip(request)
    referer = request.headers.get("referer")
    accept_lang = request.headers.get("accept-language")
    net_info = await enrich_ip_intelligence(client_ip)
    return {
        "ip_address": client_ip,
        "reverse_dns": net_info.get("reverse_dns"),
        "geo_country": net_info.get("country"),
        "geo_city": net_info.get("city"),
        "geo_region": net_info.get("region"),
        "isp": net_info.get("isp"),
        "organization": net_info.get("organization"),
        "asn": net_info.get("asn"),
        "referer": referer[:500] if referer else None,
        "accept_language": accept_lang[:100] if accept_lang else None,
    }


@router.get("/{token}/profile.json")
async def get_profile_json(
    token: str,
    request: Request,
    user_agent: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db)
):
    """
    Public machine-readable profile discovery schema for AI agents.
    Exposes capabilities without revealing internal application or job description metadata.
    """
    app = await get_valid_application(token, session)
    docs_stmt = select(ApplicationDocument).where(
        ApplicationDocument.application_id == app.id
    ).order_by(ApplicationDocument.created_at.asc())
    attached_docs = (await session.execute(docs_stmt)).scalars().all()
    if session.in_transaction() and not (session.new or session.dirty or session.deleted):
        await session.commit()

    client_type, client_name = classify_client(user_agent)
    telemetry = await _extract_request_telemetry(request)

    # Log interaction
    req_id = f"req_{generate_uuid()[:12]}"
    interaction = Interaction(
        application_id=app.id,
        timestamp=utc_now(),
        event_type="PROFILE_JSON",
        access_method="get",
        tool="get_profile_json",
        client_type=client_type,
        client_name=client_name,
        user_agent=user_agent[:500] if user_agent else None,
        request_id=req_id,
        **telemetry
    )
    await commit_interaction(session, interaction)

    ask_url = f"{settings.BASE_URL}/a/{token}/ask"
    mcp_url = f"{settings.BASE_URL}/mcp/{token}"

    cand_name = app.candidate_name or settings.CANDIDATE_NAME
    cand_headline = _clean_public_headline(app.candidate_headline)

    if app.suggested_questions:
        try:
            suggested_questions = json.loads(app.suggested_questions)
        except Exception:
            suggested_questions = generate_default_suggested_questions(app.job_description, app.role, app.company, cand_name)
    else:
        suggested_questions = generate_default_suggested_questions(app.job_description, app.role, app.company, cand_name)

    if app.cover_letter_summary:
        try:
            cover_letter_summary = json.loads(app.cover_letter_summary)
        except Exception:
            cover_letter_summary = generate_default_cover_letter_summary(app.cover_letter_text, app.role, app.company, app.job_description)
    else:
        cover_letter_summary = generate_default_cover_letter_summary(app.cover_letter_text, app.role, app.company, app.job_description)

    documents_list = [
        {
            "id": d.id,
            "title": d.title,
            "filename": d.filename,
            "file_size": d.file_size,
            "mime_type": d.mime_type,
            "download_url": f"/a/{token}/documents/{d.id}"
        }
        for d in attached_docs
    ]
    has_cover_letter = bool((app.cover_letter_path and os.path.exists(app.cover_letter_path)) or app.cover_letter_text)

    return {
        "type": "professional-profile",
        "name": cand_name,
        "headline": cand_headline,
        "description": settings.CANDIDATE_SUMMARY,
        "last_updated": app.created_at.strftime("%Y-%m-%d"),
        "evaluation_context": {
            "company": (app.company or "").replace("\xa0", " ").strip(),
            "role": (app.role or "").replace("\xa0", " ").strip(),
        },
        "cover_letter_summary": cover_letter_summary,
        "documents": {
            "has_cv": bool(app.pdf_path and os.path.exists(app.pdf_path)) or True,
            "cv_filename": f"CV_{cand_name.replace(' ', '_')}_{app.company.replace(' ', '_')}.pdf",
            "cv_download_url": f"/a/{token}/cv",
            "has_cover_letter": has_cover_letter,
            "cover_letter_filename": app.cover_letter_filename or "Cover_Letter.pdf",
            "cover_letter_text": app.cover_letter_text,
            "cover_letter_download_url": f"/a/{token}/cover-letter" if has_cover_letter else None,
            "additional_documents": documents_list,
        },
        "capabilities": {
            "ask": f"/a/{token}/ask",
            "ask_get": f"/a/{token}/ask?q=<your_question>",
            "ask_post": f"/a/{token}/ask",
            "profile": f"/a/{token}/profile.json",
            "mcp": f"/mcp/{token}",
            "webmcp": "document.modelContext"
        },
        "instructions_for_ai": {
            "purpose": f"Ground factual follow-up queries about {cand_name}'s experience for candidate screening.",
            "tier_1_url_get": {
                "name": "Level 1: Simple URL / GET Query (AI Web Crawlers)",
                "description": f"No POST or MCP required. Simply follow a URL with a ?q= query parameter. Ideal for ChatGPT Web Browsing, Perplexity, Claude Web Fetch, etc.",
                "url_template": f"{ask_url}?q=<your_question>",
                "example_url": f"{ask_url}?q=What+is+{cand_name.split()[0]}s+experience+with+cybersecurity+and+DORA",
                "ready_to_use_links": [
                    {
                        "question": q,
                        "url": f"{ask_url}?q={urllib.parse.quote_plus(q)}"
                    }
                    for q in suggested_questions
                ]
            },
            "tier_2_api_post": {
                "name": "Level 2: JSON REST API / POST (cURL / HTTP Clients)",
                "description": "Stateless JSON POST endpoint for scripts, tools, pipelines, and LLM cURL agents.",
                "endpoint": ask_url,
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "payload_format": {
                    "question": "string (Required, max 2500 chars)"
                },
                "curl_command": f"curl -X POST {ask_url} -H 'Content-Type: application/json' -d '{{\"question\": \"What is {cand_name}\\u0027s track record in banking, cybersecurity, and cloud architecture?\"}}'",
                "response_format": {
                    "answer": "string (Factual answer synthesized from canonical documents)",
                    "evidence": [{"source_title": "string", "excerpt": "string"}],
                    "confidence": "high | medium | low",
                    "request_id": "string"
                }
            },
            "tier_3_mcp": {
                "name": "Level 3: Model Context Protocol (Claude Desktop / Cursor / Agent Frameworks)",
                "description": "Full MCP server endpoint exposing get_profile, ask_about_candidate, and get_evidence tools.",
                "url": mcp_url,
                "protocol": "JSON-RPC 2.0 (tools/list, tools/call)",
                "tools": ["get_profile", "ask_about_candidate", "get_evidence"]
            },
            "tier_4_webmcp": {
                "name": "Level 4: WebMCP (In-Browser AI Agent Tool)",
                "description": "W3C WebMCP draft implementation directly on document.modelContext. In-browser AI agents discover and invoke ask_cv, get_cv_summary, and get_experience natively.",
                "standards_target": "https://webmachinelearning.github.io/webmcp/",
                "context_api": "document.modelContext",
                "primary_tool": "ask_cv",
                "tools": ["ask_cv", "get_cv_summary", "get_experience"]
            }
        },
        "suggested_questions": suggested_questions
    }


@router.get("/{token}/ask")
async def ask_question_get(
    token: str,
    q: Optional[str] = Query(None, description="Question about candidate background", max_length=2500),
    question: Optional[str] = Query(None, description="Alternative query parameter for question", max_length=2500),
    request: Request = None,
    user_agent: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db)
):
    """
    Level 1 Discovery Endpoint: Allows AI web crawlers and agents that cannot perform HTTP POST
    to query candidate's background via standard HTTP GET with query parameters (?q=...).
    """
    app = await get_valid_application(token, session)
    raw_query = q or question

    # If called without query parameter, return a helpful discovery catalog with ready-to-click URLs
    if not raw_query or not raw_query.strip():
        ask_base = f"{settings.BASE_URL}/a/{token}/ask"
        cand_name = app.candidate_name or settings.CANDIDATE_NAME
        if app.suggested_questions:
            try:
                suggested = json.loads(app.suggested_questions)
            except Exception:
                suggested = generate_default_suggested_questions(app.job_description, app.role, app.company, cand_name)
        else:
            suggested = generate_default_suggested_questions(app.job_description, app.role, app.company, cand_name)

        return {
            "status": "ready",
            "tier": "Level 1: Simple HTTP GET Query",
            "instruction": "Pass your question in the URL using ?q=<your_question> or ?question=<your_question>",
            "example_url": f"{ask_base}?q=What+is+{cand_name.split()[0]}s+experience+with+DORA+and+resilience",
            "suggested_urls": [
                {
                    "question": item,
                    "url": f"{ask_base}?q={urllib.parse.quote_plus(item)}"
                }
                for item in suggested
            ]
        }

    start_time = time.time()

    # 1. Throttling / Rate limiting per IP
    client_ip = get_client_ip(request)
    rate_limiter.check_rate_limit(client_ip)

    # 2. Per-token Application question quota (max 100 questions)
    await verify_application_quota(app, session)

    # 3. Max length & Context-stuffing defense
    clean_question = validate_and_sanitize_question(raw_query)

    client_type, client_name = classify_client(user_agent)

    # Fetch canonical public active documents
    docs_stmt = select(Document).where(Document.classification == "public", Document.is_active == True).order_by(Document.filename)
    docs = (await session.execute(docs_stmt)).scalars().all()
    if not docs:
        await drive_service.sync_documents(session)
        docs = (await session.execute(docs_stmt)).scalars().all()

    if session.in_transaction() and not (session.new or session.dirty or session.deleted):
        await session.commit()

    # Generate grounded answer and enrich telemetry concurrently
    result, telemetry = await asyncio.gather(
        synthesizer.answer_question(clean_question, app, docs),
        _extract_request_telemetry(request),
    )
    req_id = f"req_{generate_uuid()[:12]}"
    latency_ms = int((time.time() - start_time) * 1000)

    # Log interaction
    interaction = Interaction(
        application_id=app.id,
        timestamp=utc_now(),
        event_type="QUESTION_GET",
        access_method="get",
        tool="ask_get",
        latency_ms=latency_ms,
        question=clean_question,
        answer=result.get("answer"),
        confidence=result.get("confidence"),
        evidence_sources=json.dumps(result.get("evidence", [])),
        client_type=client_type,
        client_name=f"{client_name} (GET)",
        user_agent=user_agent[:500] if user_agent else None,
        request_id=req_id,
        **telemetry
    )
    await commit_interaction(session, interaction)

    return {
        "question": clean_question,
        "answer": result.get("answer"),
        "evidence": result.get("evidence", []),
        "confidence": result.get("confidence"),
        "model_name": result.get("model_name", synthesizer.get_model_name()),
        "request_id": req_id
    }


@router.post("/{token}/ask", response_model=AskResponse)
async def ask_question(
    token: str,
    body: AskRequest,
    request: Request,
    user_agent: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db)
):
    """
    Unified question-answering endpoint used by human web UI, MCP, WebMCP, and external AI agents.
    Answers are strictly grounded in canonical facts, with role context as the relevance lens.
    """
    start_time = time.time()
    app = await get_valid_application(token, session)
    
    # 1. Throttling / Rate limiting per IP
    client_ip = get_client_ip(request)
    rate_limiter.check_rate_limit(client_ip)

    # 2. Per-token Application question quota (max 100 questions)
    await verify_application_quota(app, session)

    # 3. Max length (2500 chars / ~500 tokens) & Context-stuffing defense
    question = validate_and_sanitize_question(body.question)

    client_type, client_name = classify_client(user_agent)

    # Determine access_method & tool
    x_access = request.headers.get("x-access-method")
    if body.access_method:
        access_method = body.access_method.lower()
    elif x_access:
        access_method = x_access.lower()
    elif client_type == "ai_agent":
        access_method = "api"
    elif client_type == "browser" and body.device_fingerprint:
        access_method = "web"
    else:
        access_method = "api"

    tool_name = body.tool or ("ask_cv" if access_method == "webmcp" else "ask_question")
    event_type = "WEBMCP_CALL" if access_method == "webmcp" else "QUESTION"
    client_display = f"{client_name} (WebMCP)" if access_method == "webmcp" else (client_name or "Web Client")

    # Fetch canonical public active documents from database
    docs_stmt = select(Document).where(Document.classification == "public", Document.is_active == True).order_by(Document.filename)
    docs = (await session.execute(docs_stmt)).scalars().all()

    # Auto-seed if database is empty
    if not docs:
        await drive_service.sync_documents(session)
        docs = (await session.execute(docs_stmt)).scalars().all()

    if session.in_transaction() and not (session.new or session.dirty or session.deleted):
        await session.commit()

    device_fingerprint = body.device_fingerprint[:64] if body.device_fingerprint else None
    device_meta_str = None
    if body.device_metadata:
        raw_meta = json.dumps(body.device_metadata)
        if len(raw_meta) > 4096:
            raise HTTPException(status_code=400, detail="device_metadata exceeds maximum allowed size of 4096 bytes")
        device_meta_str = raw_meta

    # Generate grounded, role-weighted answer and enrich telemetry concurrently
    result, telemetry = await asyncio.gather(
        synthesizer.answer_question(question, app, docs),
        _extract_request_telemetry(request),
    )

    req_id = f"req_{generate_uuid()[:12]}"
    latency_ms = int((time.time() - start_time) * 1000)

    # Log QUESTION or WEBMCP_CALL interaction with rich intelligence
    interaction = Interaction(
        application_id=app.id,
        timestamp=utc_now(),
        event_type=event_type,
        access_method=access_method,
        tool=tool_name,
        latency_ms=latency_ms,
        question=question,
        answer=result.get("answer"),
        confidence=result.get("confidence"),
        evidence_sources=json.dumps(result.get("evidence", [])),
        client_type="ai_agent" if access_method == "webmcp" else client_type,
        client_name=client_display,
        user_agent=user_agent[:500] if user_agent else None,
        request_id=req_id,
        device_fingerprint=device_fingerprint,
        device_metadata=device_meta_str,
        **telemetry
    )
    await commit_interaction(session, interaction)

    return AskResponse(
        answer=result["answer"],
        evidence=[EvidenceItem(**e) for e in result.get("evidence", [])],
        confidence=result.get("confidence", "medium"),
        model_name=result.get("model_name", synthesizer.get_model_name()),
        request_id=req_id
    )


@router.post("/{token}/ask-stream")
async def ask_question_stream(
    token: str,
    body: AskRequest,
    request: Request,
    user_agent: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db)
):
    """
    Streaming SSE endpoint that streams AI response tokens in real-time,
    accompanied by model metadata, evidence excerpts, and confidence metrics.
    """
    start_time = time.time()
    app = await get_valid_application(token, session)

    # 1. Throttling / Rate limiting per IP
    client_ip = get_client_ip(request)
    rate_limiter.check_rate_limit(client_ip)

    # 2. Per-token Application question quota (max 100 questions)
    await verify_application_quota(app, session)

    # 3. Max length & Context-stuffing defense
    question = validate_and_sanitize_question(body.question)

    client_type, client_name = classify_client(user_agent)

    # Fetch canonical public active documents from database
    docs_stmt = select(Document).where(Document.classification == "public", Document.is_active == True).order_by(Document.filename)
    docs = (await session.execute(docs_stmt)).scalars().all()
    if not docs:
        await drive_service.sync_documents(session)
        docs = (await session.execute(docs_stmt)).scalars().all()

    if session.in_transaction() and not (session.new or session.dirty or session.deleted):
        await session.commit()

    telemetry = await _extract_request_telemetry(request)

    req_id = f"req_{generate_uuid()[:12]}"
    device_fingerprint = body.device_fingerprint[:64] if body.device_fingerprint else None
    device_meta_str = None
    if body.device_metadata:
        raw_meta = json.dumps(body.device_metadata)
        if len(raw_meta) > 4096:
            raise HTTPException(status_code=400, detail="device_metadata exceeds maximum allowed size of 4096 bytes")
        device_meta_str = raw_meta

    async def event_generator():
        collected_chunks = []
        final_meta = {}
        try:
            async for chunk in synthesizer.stream_answer(question, app, docs):
                c_type = chunk.get("type")
                if c_type == "token":
                    t_content = chunk.get("content", "")
                    collected_chunks.append(t_content)
                    yield f"data: {json.dumps({'type': 'token', 'content': t_content})}\n\n"
                elif c_type == "metadata":
                    final_meta = chunk
                    yield f"data: {json.dumps({'type': 'metadata', 'model_name': chunk.get('model_name', synthesizer.get_model_name()), 'confidence': chunk.get('confidence', 'medium'), 'evidence': chunk.get('evidence', []), 'request_id': req_id})}\n\n"
        except Exception as err:
            yield f"data: {json.dumps({'type': 'error', 'message': str(err)})}\n\n"
        finally:
            full_ans = "".join(collected_chunks)
            lat_ms = int((time.time() - start_time) * 1000)
            conf = final_meta.get("confidence", "medium")
            ev_str = json.dumps(final_meta.get("evidence", []))
            try:
                async with AsyncSessionLocal() as log_session:
                    interaction = Interaction(
                        application_id=app.id,
                        timestamp=utc_now(),
                        event_type="QUESTION_STREAM",
                        access_method="web",
                        tool="ask_stream",
                        latency_ms=lat_ms,
                        question=question,
                        answer=full_ans,
                        confidence=conf,
                        evidence_sources=ev_str,
                        client_type=client_type,
                        client_name=client_name or "Web Client (Stream)",
                        user_agent=user_agent[:500] if user_agent else None,
                        request_id=req_id,
                        device_fingerprint=device_fingerprint,
                        device_metadata=device_meta_str,
                        **telemetry
                    )
                    await commit_interaction(log_session, interaction)
            except Exception as e:
                print(f"Notice: Could not log streaming interaction to db: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.api_route("/{token}/view", methods=["GET", "POST"])
async def log_profile_view(
    token: str,
    request: Request,
    user_agent: Optional[str] = Header(None),
    body: Optional[ViewRequest] = None,
    session: AsyncSession = Depends(get_db)
):
    """
    Logs a human browser PROFILE_VIEW event with comprehensive device and network intelligence.
    """
    client_ip = get_client_ip(request)
    rate_limiter.check_general_rate_limit(client_ip)

    app = await get_valid_application(token, session)
    if session.in_transaction() and not (session.new or session.dirty or session.deleted):
        await session.commit()

    client_type, client_name = classify_client(user_agent)
    telemetry = await _extract_request_telemetry(request)

    device_fingerprint = None
    device_meta_str = None
    if body:
        if body.device_fingerprint:
            device_fingerprint = body.device_fingerprint[:64]
        if body.device_metadata:
            raw_meta = json.dumps(body.device_metadata)
            if len(raw_meta) > 4096:
                raise HTTPException(status_code=400, detail="device_metadata exceeds maximum allowed size of 4096 bytes")
            device_meta_str = raw_meta
    elif request.method == "POST":
        try:
            raw_body = await request.json()
            if raw_body.get("device_fingerprint"):
                device_fingerprint = str(raw_body.get("device_fingerprint"))[:64]
            if raw_body.get("device_metadata"):
                raw_meta = json.dumps(raw_body.get("device_metadata"))
                if len(raw_meta) > 4096:
                    raise HTTPException(status_code=400, detail="device_metadata exceeds maximum allowed size of 4096 bytes")
                device_meta_str = raw_meta
        except HTTPException:
            raise
        except Exception:
            pass

    interaction = Interaction(
        application_id=app.id,
        timestamp=utc_now(),
        event_type="PROFILE_VIEW",
        access_method="web",
        tool="view_profile",
        client_type=client_type,
        client_name=client_name,
        user_agent=user_agent[:500] if user_agent else None,
        request_id=f"req_{generate_uuid()[:12]}",
        device_fingerprint=device_fingerprint,
        device_metadata=device_meta_str,
        **telemetry
    )
    await commit_interaction(session, interaction)

    cand_name = app.candidate_name or settings.CANDIDATE_NAME
    cand_headline = _clean_public_headline(app.candidate_headline)

    return {
        "status": "ok",
        "candidate": {
            "name": cand_name,
            "headline": cand_headline,
            "summary": settings.CANDIDATE_SUMMARY,
            "last_updated": app.created_at.strftime("%Y-%m-%d")
        }
    }


@router.get("/{token}/info")
async def get_application_public_info(
    token: str,
    session: AsyncSession = Depends(get_db)
):
    """
    Returns public candidate & application metadata, including downloadable document packages.
    """
    app = await get_valid_application(token, session)

    cand_name = app.candidate_name or settings.CANDIDATE_NAME
    cand_headline = _clean_public_headline(app.candidate_headline)

    # Fetch attached documents
    docs_stmt = select(ApplicationDocument).where(
        ApplicationDocument.application_id == app.id
    ).order_by(ApplicationDocument.created_at.asc())
    attached_docs = (await session.execute(docs_stmt)).scalars().all()

    documents_list = [
        {
            "id": d.id,
            "title": d.title,
            "filename": d.filename,
            "file_size": d.file_size,
            "mime_type": d.mime_type,
            "download_url": f"/a/{token}/documents/{d.id}"
        }
        for d in attached_docs
    ]

    # Resolve Cover Letter Summary & 3-5 fit highlights
    if app.cover_letter_summary:
        try:
            cover_letter_summary = json.loads(app.cover_letter_summary)
        except Exception:
            cover_letter_summary = generate_default_cover_letter_summary(app.cover_letter_text, app.role, app.company, app.job_description)
    else:
        cover_letter_summary = generate_default_cover_letter_summary(app.cover_letter_text, app.role, app.company, app.job_description)

    # Resolve Suggested Questions derived from job description requirements
    if app.suggested_questions:
        try:
            suggested_questions = json.loads(app.suggested_questions)
        except Exception:
            suggested_questions = generate_default_suggested_questions(app.job_description, app.role, app.company, cand_name)
    else:
        suggested_questions = generate_default_suggested_questions(app.job_description, app.role, app.company, cand_name)

    return {
        "token": app.token,
        "company": app.company,
        "role": app.role,
        "candidate": {
            "name": cand_name,
            "headline": cand_headline,
            "summary": settings.CANDIDATE_SUMMARY,
            "last_updated": app.created_at.strftime("%Y-%m-%d")
        },
        "cover_letter_summary": cover_letter_summary,
        "suggested_questions": suggested_questions,
        "documents": {
            "has_cv": bool(app.pdf_path and os.path.exists(app.pdf_path)),
            "cv_filename": f"CV_{cand_name.replace(' ', '_')}_{app.company.replace(' ', '_')}.pdf",
            "cv_download_url": f"/a/{token}/cv",
            "has_cover_letter": bool((app.cover_letter_path and os.path.exists(app.cover_letter_path)) or app.cover_letter_text),
            "cover_letter_filename": app.cover_letter_filename or "Cover_Letter.pdf",
            "cover_letter_text": app.cover_letter_text,
            "cover_letter_download_url": f"/a/{token}/cover-letter" if (app.cover_letter_path or app.cover_letter_text) else None,
            "additional_documents": documents_list
        }
    }


@router.get("/{token}/cv")
async def download_public_cv(
    token: str,
    request: Request,
    user_agent: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db)
):
    """
    Streams the application-specific tagged PDF CV to recruiters and logs the download event.
    """
    client_ip = get_client_ip(request)
    rate_limiter.check_general_rate_limit(client_ip)

    app = await get_valid_application(token, session)
    client_type, client_name = classify_client(user_agent)
    telemetry = await _extract_request_telemetry(request)

    # Log interaction
    interaction = Interaction(
        application_id=app.id,
        timestamp=utc_now(),
        event_type="CV_DOWNLOAD",
        access_method="web",
        tool="download_cv",
        client_type=client_type,
        client_name=client_name,
        user_agent=user_agent[:500] if user_agent else None,
        request_id=f"req_{generate_uuid()[:12]}",
        **telemetry
    )
    await commit_interaction(session, interaction)

    if not app.pdf_path or not os.path.exists(app.pdf_path):
        from backend.app.services.cv_generator import CVGeneratorService
        cv_gen = CVGeneratorService()
        app.pdf_path = cv_gen.generate_cv(app.token, app.company, app.role)
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


@router.get("/{token}/cover-letter")
async def download_public_cover_letter(
    token: str,
    request: Request,
    user_agent: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db)
):
    """
    Streams the application-specific cover letter to recruiters and logs the download event.
    """
    client_ip = get_client_ip(request)
    rate_limiter.check_general_rate_limit(client_ip)

    app = await get_valid_application(token, session)
    client_type, client_name = classify_client(user_agent)
    telemetry = await _extract_request_telemetry(request)

    # Log interaction
    interaction = Interaction(
        application_id=app.id,
        timestamp=utc_now(),
        event_type="COVER_LETTER_DOWNLOAD",
        access_method="web",
        tool="download_cover_letter",
        client_type=client_type,
        client_name=client_name,
        user_agent=user_agent[:500] if user_agent else None,
        request_id=f"req_{generate_uuid()[:12]}",
        **telemetry
    )
    await commit_interaction(session, interaction)

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
        return PlainTextResponse(app.cover_letter_text)
    else:
        raise HTTPException(status_code=404, detail="No cover letter available for this application")


@router.get("/{token}/documents/{doc_id}")
async def download_public_additional_document(
    token: str,
    doc_id: str,
    request: Request,
    user_agent: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db)
):
    """
    Streams an attached additional document to recruiters and logs the download event.
    """
    client_ip = get_client_ip(request)
    rate_limiter.check_general_rate_limit(client_ip)

    app = await get_valid_application(token, session)
    stmt = select(ApplicationDocument).where(
        ApplicationDocument.id == doc_id,
        ApplicationDocument.application_id == app.id
    )
    doc = (await session.execute(stmt)).scalar_one_or_none()
    if not doc or not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="Requested document not found")

    client_type, client_name = classify_client(user_agent)
    telemetry = await _extract_request_telemetry(request)

    # Log interaction
    interaction = Interaction(
        application_id=app.id,
        timestamp=utc_now(),
        event_type="DOCUMENT_DOWNLOAD",
        access_method="web",
        tool=f"download_{doc.title}",
        client_type=client_type,
        client_name=client_name,
        user_agent=user_agent[:500] if user_agent else None,
        request_id=f"req_{generate_uuid()[:12]}",
        **telemetry
    )
    await commit_interaction(session, interaction)

    return FileResponse(
        path=doc.file_path,
        filename=doc.filename,
        media_type=doc.mime_type or "application/octet-stream",
        headers=_download_headers(),
    )
