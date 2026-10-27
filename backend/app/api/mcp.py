import asyncio
import json
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.database import get_db, commit_interaction
from backend.app.models import Application, Interaction, Document, utc_now, generate_uuid
from backend.app.config import settings
from backend.app.services.ai import AnswerSynthesizer
from backend.app.services.classifier import classify_client
from backend.app.services.security import (
    get_client_ip,
    rate_limiter,
    verify_application_quota,
    validate_and_sanitize_question
)
from backend.app.services.telemetry import enrich_ip_intelligence
from backend.app.services.google_drive import GoogleDriveService

router = APIRouter(prefix="/mcp", tags=["Model Context Protocol (MCP)"])
synthesizer = AnswerSynthesizer()
drive_service = GoogleDriveService()


class MCPRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int
    method: str
    params: Optional[Dict[str, Any]] = None


async def get_valid_app_for_mcp(token: str, session: AsyncSession) -> Application:
    stmt = select(Application).where(Application.token == token)
    app = (await session.execute(stmt)).scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Invalid MCP token")
    if not app.is_active:
        raise HTTPException(status_code=410, detail="Token revoked")
    return app


@router.post("/{token}")
async def handle_mcp_request(
    token: str,
    rpc: MCPRpcRequest,
    request: Request,
    user_agent: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db)
):
    """
    Stateless HTTP Model Context Protocol (MCP) endpoint.
    Exposes candidate tools:
    - tools/list
    - tools/call (get_profile, ask_about_candidate, get_evidence)
    Uses the exact same factual knowledge base, application context, and logging.
    """
    app = await get_valid_app_for_mcp(token, session)
    client_type, client_name = classify_client(user_agent or "MCP-Client")

    # 1. Tool discovery
    if rpc.method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": rpc.id,
            "result": {
                "tools": [
                    {
                        "name": "get_profile",
                        "description": "Returns candidate summary, core competencies and contact profile capabilities.",
                        "inputSchema": {"type": "object", "properties": {}}
                    },
                    {
                        "name": "ask_about_candidate",
                        "description": f"Answers factual questions about {settings.CANDIDATE_NAME}'s background, prioritized for the specific role context.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string", "description": f"The specific question about {settings.CANDIDATE_NAME}'s background"}
                            },
                            "required": ["question"]
                        }
                    },
                    {
                        "name": "get_evidence",
                        "description": "Retrieves the exact canonical source document and excerpts for a given source title.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "source_title": {"type": "string", "description": "Title of the source document"}
                            },
                            "required": ["source_title"]
                        }
                    }
                ]
            }
        }

    # 2. Tool execution
    if rpc.method == "tools/call":
        params = rpc.params or {}
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "get_profile":
            return {
                "jsonrpc": "2.0",
                "id": rpc.id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({
                                "name": settings.CANDIDATE_NAME,
                                "headline": settings.CANDIDATE_HEADLINE,
                                "summary": settings.CANDIDATE_SUMMARY,
                                "cv_version": app.cv_version
                            }, indent=2)
                        }
                    ]
                }
            }

        elif tool_name == "ask_about_candidate":
            raw_question = args.get("question", "")
            client_ip = get_client_ip(request)

            # 1. Rate limiting per IP
            try:
                rate_limiter.check_rate_limit(client_ip)
            except HTTPException as e:
                return {
                    "jsonrpc": "2.0",
                    "id": rpc.id,
                    "error": {"code": -32000, "message": str(e.detail)}
                }

            # 2. Per-token Application question quota (100 questions across all channels)
            try:
                await verify_application_quota(app, session)
            except HTTPException as e:
                return {
                    "jsonrpc": "2.0",
                    "id": rpc.id,
                    "error": {"code": -32000, "message": str(e.detail)}
                }

            # 3. Question sanitization, length bounds and context stuffing defense
            try:
                question = validate_and_sanitize_question(raw_question)
            except HTTPException as e:
                return {
                    "jsonrpc": "2.0",
                    "id": rpc.id,
                    "error": {"code": -32602, "message": str(e.detail)}
                }

            # Fetch only public canonical docs
            docs_stmt = select(Document).where(Document.classification == "public").order_by(Document.filename)
            docs = (await session.execute(docs_stmt)).scalars().all()
            if not docs:
                await drive_service.sync_documents(session)
                docs = (await session.execute(docs_stmt)).scalars().all()

            if session.in_transaction() and not (session.new or session.dirty or session.deleted):
                await session.commit()

            result, net_info = await asyncio.gather(
                synthesizer.answer_question(question, app, docs),
                enrich_ip_intelligence(client_ip),
            )

            if result.get("status") == "service_unavailable":
                return {
                    "jsonrpc": "2.0",
                    "id": rpc.id,
                    "error": {
                        "code": -32000,
                        "message": result.get("answer", "AI reasoning service is temporarily unavailable.")
                    }
                }

            # Log MCP_CALL interaction with telemetry
            req_id = f"mcp_{generate_uuid()[:12]}"
            interaction = Interaction(
                application_id=app.id,
                timestamp=utc_now(),
                event_type="MCP_CALL",
                access_method="mcp",
                tool="ask_about_candidate",
                question=question,
                answer=result.get("answer"),
                confidence=result.get("confidence"),
                evidence_sources=json.dumps(result.get("evidence", [])),
                client_type="ai_agent",
                client_name=client_name or "MCP Agent",
                user_agent=user_agent,
                request_id=req_id,
                ip_address=client_ip,
                reverse_dns=net_info.get("reverse_dns"),
                geo_country=net_info.get("country"),
                geo_city=net_info.get("city"),
                geo_region=net_info.get("region"),
                isp=net_info.get("isp"),
                organization=net_info.get("organization"),
                asn=net_info.get("asn"),
            )
            await commit_interaction(session, interaction)

            return {
                "jsonrpc": "2.0",
                "id": rpc.id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2)
                        }
                    ]
                }
            }

        elif tool_name == "get_evidence":
            source_title = args.get("source_title", "").lower().strip()
            # Only allow queries against public evidence documents
            stmt = select(Document).where(Document.classification == "public")
            docs = (await session.execute(stmt)).scalars().all()
            if not docs:
                await drive_service.sync_documents(session)
                docs = (await session.execute(stmt)).scalars().all()
            matched = [d for d in docs if source_title in d.title.lower() or source_title in d.filename.lower()]

            if not matched:
                return {
                    "jsonrpc": "2.0",
                    "id": rpc.id,
                    "result": {"content": [{"type": "text", "text": "Evidence document not found or access restricted."}]}
                }

            doc = matched[0]
            # Bound excerpt to prevent raw document dumping (max 1200 chars)
            max_chars = 1200
            content = doc.content_markdown
            if len(content) > max_chars:
                cut_point = content.rfind("\n\n", 0, max_chars)
                if cut_point > 300:
                    excerpt = content[:cut_point]
                else:
                    excerpt = content[:max_chars]
                excerpt += "\n\n... [Evidence bounded to approved public excerpt]"
            else:
                excerpt = content

            return {
                "jsonrpc": "2.0",
                "id": rpc.id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"# {doc.title} (Verified Public Evidence)\n\n{excerpt}"
                        }
                    ]
                }
            }

        return {
            "jsonrpc": "2.0",
            "id": rpc.id,
            "error": {"code": -32601, "message": f"Method '{tool_name}' not found"}
        }

    return {
        "jsonrpc": "2.0",
        "id": rpc.id,
        "error": {"code": -32601, "message": f"Unsupported method: {rpc.method}"}
    }
