import asyncio
import io
import json
import re
from typing import List, Dict, Any, Optional, Union
import httpx
from pypdf import PdfReader
from backend.app.config import settings
from backend.app.models import Document, Application

try:
    from langsmith import traceable
except ImportError:
    def traceable(*args, **kwargs):
        def decorator(func):
            return func
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        return decorator


def extract_cv_metadata(pdf_source: Union[bytes, bytearray, str]) -> Dict[str, str]:
    """
    Extracts candidate name and professional title/tagline from a PDF CV.
    Filters out running page headers, contact labels, section headers, and document titles.
    Falls back to settings defaults if not clearly extractable.
    """
    import os

    name = settings.CANDIDATE_NAME
    headline = settings.CANDIDATE_HEADLINE

    try:
        if isinstance(pdf_source, str):
            if not os.path.exists(pdf_source):
                return {"name": name, "headline": headline}
            reader = PdfReader(pdf_source)
        elif isinstance(pdf_source, (bytes, bytearray)):
            reader = PdfReader(io.BytesIO(pdf_source))
        else:
            return {"name": name, "headline": headline}

        if len(reader.pages) == 0:
            return {"name": name, "headline": headline}

        # Check PDF metadata Author if available and non-generic
        meta = reader.metadata or {}
        author = meta.get("/Author") or meta.get("Author")
        if (
            author 
            and author.strip() 
            and 2 <= len(author.strip()) <= 60 
            and not any(w in author.lower() for w in [
                "unknown", "anonymous", "untitled", "user", "admin", 
                "author", "adobe", "word", "writer", "reportlab", "pdf", "microsoft"
            ])
        ):
            name = author.strip()

        # Extract text from page 0
        page_0_text = reader.pages[0].extract_text() or ""

        # 1. Check for explicit "Name:" / "Namn:" field
        name_found_explicit = False
        name_match = re.search(r'(?:^|\n)\s*(?:Name|Namn)\s*:\s*([^\n\r]+)', page_0_text, re.IGNORECASE)
        if name_match:
            candidate_val = name_match.group(1).strip()
            candidate_val = re.sub(r'\s+(?:Adress|Address|E-mail|Email|Phone|LinkedIn|Tel).*$', '', candidate_val, flags=re.IGNORECASE).strip()
            if 2 <= len(candidate_val) <= 60 and not re.search(r'^(?:cv|page|resume)\b', candidate_val, re.IGNORECASE):
                name = candidate_val
                name_found_explicit = True

        # 2. Extract lines to find candidate name (if not set by explicit field) and headline/tagline
        raw_lines = [line.strip() for line in page_0_text.splitlines() if line.strip()]

        def is_header_or_running_text(l: str) -> bool:
            low = l.lower()
            if re.search(r'^(?:cv|curriculum\s+vitae|resume)\b', low):
                return True
            if re.search(r'\bpage\s*\d+\b', low) or re.search(r'\bsida\s*\d+\b', low):
                return True
            return False

        def is_contact_line(l: str) -> bool:
            low = l.lower()
            if any(k in low for k in ["@", "http://", "https://", "linkedin.com", "github.com"]):
                return True
            if re.search(r'^(?:name|namn|adress|address|e-mail|email|phone|tel|telefon|mobil|linkedin|contact)\s*:', low):
                return True
            return False

        def is_section_title(l: str) -> bool:
            low = l.lower()
            section_keywords = [
                "executive summary", "core strengths", "education", 
                "education and professional development", "professional experience", 
                "selected professional leadership", "key expertise & core competencies",
                "key expertise", "experience", "summary", "profile", "skills", 
                "current technology", "languages", "competencies", "work history", 
                "employment history", "earlier career"
            ]
            clean_l = re.sub(r'^[•\-\*\s]+', '', low).strip()
            return clean_l in section_keywords or any(clean_l.startswith(k) and len(clean_l) <= len(k) + 3 for k in section_keywords)

        candidate_taglines = []
        name_extracted_from_lines = name_found_explicit

        for line in raw_lines:
            clean = re.sub(r'^[•\-\*\s]+', '', line).strip()
            if not clean:
                continue

            if is_header_or_running_text(clean) or is_contact_line(clean) or is_section_title(clean):
                continue

            # If name has not been definitively found, the first valid short non-header line is the candidate's name
            if not name_extracted_from_lines:
                words = clean.split()
                if 2 <= len(words) <= 4 and 2 <= len(clean) <= 50 and not clean.endswith(".") and not any(c in clean for c in [":", "@", "/", "\\", "(", ")"]):
                    name = clean
                    name_extracted_from_lines = True
                    continue

            # If this line is the candidate's name itself, skip
            if clean.lower() == name.lower() or f"name: {name.lower()}" == clean.lower():
                continue

            # Check if this line is a suitable professional headline/tagline
            # Length between 4 and 120 chars, not a sentence ending in '.', max 12 words
            if 4 <= len(clean) <= 120 and not clean.endswith(".") and len(clean.split()) <= 12:
                candidate_taglines.append(clean)

        if candidate_taglines:
            headline = candidate_taglines[0]

    except Exception as e:
        print(f"Notice: Could not parse CV metadata from PDF: {e}")

    # Normalize non-breaking spaces and strip trailing hyphens/dashes from PDF line wraps
    name = name.replace("\xa0", " ").strip()
    headline = re.sub(r"[\s\-–—:|]+$", "", headline.replace("\xa0", " ").strip()).strip()

    # Final sanity cleanup
    if re.search(r'^(?:cv|page|resume)\b', name, re.IGNORECASE) or "page" in name.lower():
        name = settings.CANDIDATE_NAME
    if not headline or re.search(r'^(?:cv|page|resume)\b', headline, re.IGNORECASE) or "page" in headline.lower():
        headline = "CTO & Product Technology Executive"

    return {"name": name, "headline": headline}


def generate_default_cover_letter_summary(
    cover_letter_text: Optional[str],
    role: str,
    company: str,
    job_description: str
) -> Dict[str, Any]:
    """Deterministic fallback for cover letter summary with 3-5 fit bullet points."""
    text = (cover_letter_text or "").strip()
    lowered = (text + " " + (job_description or "")).lower()
    
    bullets = []
    
    if any(k in lowered for k in ["leadership", "scale", "team", "manage", "executive", "transform", "cito", "cto"]):
        bullets.append(f"Executive Leadership & Scale: Track record driving organizational vision, building high-performing cross-functional teams, and steering strategic technology roadmaps as needed for {role}.")
    
    if any(k in lowered for k in ["security", "cyber", "dora", "resilience", "iso", "compliance", "regulatory", "risk"]):
        bullets.append(f"Operational Resilience & Security: Proven expertise establishing robust security postures, regulatory readiness (DORA, ISO 27001), and enterprise-grade reliability.")
    
    if any(k in lowered for k in ["cloud", "architecture", "microservices", "modernization", "platform", "azure", "aws", "api"]):
        bullets.append(f"Modern Technology Architecture: Deep hands-on experience modernizing legacy systems, migrating complex workloads to cloud platforms, and engineering scalable architectures.")
    
    if any(k in lowered for k in ["ai", "data", "machine learning", "governance", "analytics"]):
        bullets.append(f"Practical AI & Data Governance: Strategic experience formulating ethical AI governance frameworks compliant with the EU AI Act while maximizing operational automation.")
    
    if any(k in lowered for k in ["banking", "finance", "credit", "financial", "fintech", "payment"]):
        bullets.append(f"Domain Alignment in Financial Systems: Direct experience modernizing regulated financial operations, self-service portals, and transaction engines.")
    
    if len(bullets) < 3:
        bullets.append(f"Strategic Alignment: Dedicated commitment to accelerating {company}'s strategic goals and delivering measurable business outcomes.")
    if len(bullets) < 3:
        bullets.append(f"Delivery & Execution Excellence: Proven ability to balance high-level technical direction with pragmatic execution and delivery.")
    
    bullets = bullets[:5]
    
    summary = (
        f"The candidate's application for {role} at {company} emphasizes strong strategic alignment, "
        f"executive technical leadership, and extensive experience delivering measurable business transformation. "
        f"The candidate highlights key competencies directly aligned with {company}'s core requirements."
    )
    
    return {
        "summary": summary,
        "fit_highlights": bullets
    }


def generate_default_suggested_questions(
    job_description: str,
    role: str,
    company: str,
    candidate_name: str
) -> List[str]:
    """Generates 4 suggested screening questions derived from the job description requirements."""
    jd_lower = (job_description or "").lower()
    first_name = candidate_name.split()[0] if candidate_name else "the candidate"
    
    questions = []
    
    if any(k in jd_lower for k in ["leadership", "manage", "team", "organization", "scale", "director", "head", "lead"]):
        questions.append(f"What technology leadership and organizational scale experience does {first_name} have?")
    
    if any(k in jd_lower for k in ["bank", "banking", "finance", "financial", "credit", "fintech", "payment", "regulated"]):
        questions.append(f"What experience does {first_name} have with financial services, credit management and regulated environments?")
    
    if any(k in jd_lower for k in ["security", "cyber", "cybersecurity", "dora", "isms", "resilience", "iso 27001", "compliance", "risk"]):
        questions.append(f"Can you provide examples of {first_name}'s cybersecurity, operational resilience, and regulatory compliance work?")
    
    if any(k in jd_lower for k in ["ai", "data", "machine learning", "ml", "governance", "analytics", "automation"]):
        questions.append(f"How has {first_name} formulated and operationalized enterprise AI governance frameworks?")
    
    if any(k in jd_lower for k in ["cloud", "aws", "azure", "architecture", "microservices", "kubernetes", "devops"]):
        questions.append(f"What is {first_name}'s track record in large-scale cloud architecture and modernization?")
        
    if any(k in jd_lower for k in ["product", "customer", "portal", "self-service", "digital", "transformation"]):
        questions.append(f"How has {first_name} driven digital transformation and customer portal modernizations?")

    defaults = [
        f"What technology leadership and organizational scale experience does {first_name} have?",
        f"What experience does {first_name} have with financial services, credit management and banking regulations?",
        f"Can you provide examples of {first_name}'s cybersecurity, resilience and DORA readiness work?",
        f"How has {first_name} formulated and operationalized enterprise AI governance frameworks?"
    ]
    
    for d in defaults:
        if len(questions) >= 4:
            break
        if d not in questions:
            questions.append(d)
            
    return questions[:4]


SYSTEM_PROMPT_TEMPLATE = """<role>
You are an evidence-grounded career-writing assistant. Answer the visitor's question about the candidate using ONLY the supplied application context and canonical knowledge base documents.
</role>

<objective>
Create a specific, credible answer that clearly connects the candidate's actions to business or engineering outcomes. Emphasize leadership, collaboration, innovation, and measurable impact when supported by the evidence.
</objective>

<target_application>
Target Company: {company}
Target Role: {role}
Job Context / Requirements:
{job_description}
</target_application>

<instructions>
1. Identify the experiences in the knowledge base most relevant to the question.
2. Synthesize them into a concise, specific response (120-220 words) rather than listing raw document contents.
3. Use concrete technologies, practices, scope, metrics, and outcomes ONLY when explicitly supported by the supplied documents.
4. Do NOT invent employers, projects, metrics, team sizes, certifications, tools, or responsibilities.
5. If the supplied documents do NOT contain verified evidence supporting the specific claim, credential, metric, or topic asked about, do NOT guess or extrapolate. Instead return:
   - "answer": "No verified evidence was found for this specific claim."
   - "confidence": "unavailable"
   - "evidence": []
6. Return valid JSON matching this exact schema (with no markdown code fences):
{{
  "answer": "string",
  "confidence": "high | medium | low | unavailable",
  "evidence": [
    {{
      "source_title": "Exact document title from the knowledge base",
      "excerpt": "Short verbatim or faithful supporting quote/fact from that document"
    }}
  ]
}}
</instructions>
"""


def _normalize_match_text(text: str) -> str:
    """Normalizes text for fuzzy title comparison."""
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()


def _strip_json_fences(raw_text: str) -> str:
    """Strips optional ```json ... ``` markdown fences around JSON."""
    cleaned = (raw_text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    return cleaned.strip()


def validate_and_filter_llm_response(
    raw_result: Dict[str, Any],
    documents: List[Document],
    model_name: str
) -> Dict[str, Any]:
    """
    Validates model output structure, bounds confidence values, sanitizes answer length,
    and ensures cited evidence titles map strictly to approved active documents in the database.
    """
    if isinstance(raw_result.get("answer"), str):
        candidate_ans = _strip_json_fences(raw_result["answer"])
        if candidate_ans.startswith("{") and candidate_ans.endswith("}"):
            try:
                inner = json.loads(candidate_ans)
                if isinstance(inner, dict) and "answer" in inner:
                    raw_result = {**raw_result, **inner}
            except Exception:
                pass

    answer = str(raw_result.get("answer") or "").strip()
    if len(answer) > 6000:
        answer = answer[:6000] + "..."

    raw_conf = str(raw_result.get("confidence") or "high").lower().strip()
    confidence = raw_conf if raw_conf in ("high", "medium", "low", "unavailable") else "high"

    ans_low = answer.lower()
    no_evidence_phrases = (
        "no verified evidence was found",
        "does not provide enough evidence",
        "no evidence in the provided",
        "no supporting evidence",
        "not mentioned in the provided",
        "cannot verify this claim",
    )
    if confidence == "unavailable" or any(p in ans_low for p in no_evidence_phrases):
        if not answer or "no verified evidence" in ans_low:
            answer = "No verified evidence was found for this specific claim."
        return {
            "answer": answer,
            "evidence": [],
            "confidence": "unavailable",
            "model_name": str(raw_result.get("model_name") or model_name),
            "source": "cv-assistant",
            "status": "ok",
        }

    valid_doc_titles = {d.title.lower(): d.title for d in documents}
    valid_doc_filenames = {d.filename.lower(): d.title for d in documents}

    raw_evidence = raw_result.get("evidence") or []
    validated_evidence = []
    if isinstance(raw_evidence, list):
        for ev in raw_evidence:
            if not isinstance(ev, dict):
                continue
            src = str(ev.get("source_title") or "").strip()
            excerpt = str(ev.get("excerpt") or "").strip()
            if not src or not excerpt:
                continue

            src_low = src.lower()
            src_norm = _normalize_match_text(src)
            src_words = set(w for w in src_norm.split() if len(w) >= 3)
            matched_title = None

            if src_low in valid_doc_titles:
                matched_title = valid_doc_titles[src_low]
            elif src_low in valid_doc_filenames:
                matched_title = valid_doc_filenames[src_low]
            else:
                for d in documents:
                    d_norm = _normalize_match_text(d.title)
                    d_fname_norm = _normalize_match_text(d.filename)
                    if src_norm in d_norm or d_norm in src_norm or src_norm in d_fname_norm:
                        matched_title = d.title
                        break
                    d_words = set(w for w in d_norm.split() if len(w) >= 3)
                    if src_words and (src_words.issubset(d_words) or d_words.issubset(src_words)):
                        matched_title = d.title
                        break
                    if src_words and d_words and len(src_words.intersection(d_words)) >= 2:
                        matched_title = d.title
                        break
                if not matched_title and len(documents) == 1:
                    matched_title = documents[0].title

            if matched_title:
                validated_evidence.append({
                    "source_title": matched_title,
                    "excerpt": excerpt[:500]
                })

    # Fallback: if the model provided a grounded answer with high/medium confidence
    # but omitted structured evidence array (e.g. plain prose), link to matching document
    if not validated_evidence and confidence in ("high", "medium") and documents and answer:
        ans_words = set(w for w in _normalize_match_text(answer).split() if len(w) >= 4)
        for d in documents:
            paragraphs = [
                p.strip()
                for p in re.split(r"\n\s*\n", d.content_markdown or "")
                if len(p.strip()) >= 40 and not p.strip().startswith("#")
            ]
            best_para = None
            best_score = 0
            for p in paragraphs:
                p_words = set(w for w in _normalize_match_text(p).split() if len(w) >= 4)
                score = len(ans_words.intersection(p_words))
                if score > best_score:
                    best_score = score
                    best_para = p
            if best_para and best_score >= 2:
                clean_excerpt = re.sub(r"\s+", " ", best_para).strip()[:320]
                validated_evidence.append({
                    "source_title": d.title,
                    "excerpt": clean_excerpt,
                })
                break

    resolved_model_name = str(raw_result.get("model_name") or model_name)

    return {
        "answer": answer,
        "evidence": validated_evidence,
        "confidence": confidence,
        "model_name": resolved_model_name,
        "source": "cv-assistant",
    }


def build_knowledge_context(documents: List[Document]) -> str:
    """Combines all canonical markdown documents into a clean structured string."""
    parts = []
    for doc in documents:
        parts.append(f"=== SOURCE DOCUMENT: {doc.title} (File: {doc.filename}) ===\n{doc.content_markdown}\n")
    return "\n".join(parts)


def serialize_application_context(
    application: Application,
    question: str,
    documents: List[Document]
) -> Dict[str, Any]:
    """
    Serializes Application, question, and Document models into pure JSON-compatible data.
    Ensures no ORM instances or object representations leak into LangSmith traces.
    """
    return {
        "company": str(application.company or ""),
        "role": str(application.role or ""),
        "job_description": str(application.job_description or ""),
        "question": str(question or ""),
        "documents": [
            {
                "id": str(doc.id) if doc.id is not None else None,
                "title": str(doc.title or ""),
                "filename": str(doc.filename or ""),
                "classification": str(doc.classification or "public"),
                "content_markdown": str(doc.content_markdown or "")
            }
            for doc in documents
        ]
    }


def render_qa_messages(
    template_variables: Dict[str, Any]
) -> List[Dict[str, str]]:
    """
    Renders the exact system and user messages from sanitized JSON template variables.
    """
    system_instruction = SYSTEM_PROMPT_TEMPLATE.format(
        company=template_variables.get("company", ""),
        role=template_variables.get("role", ""),
        job_description=template_variables.get("job_description", "")
    )
    
    docs_context = "\n".join([
        f"=== SOURCE DOCUMENT: {d['title']} (File: {d['filename']}) ===\n{d['content_markdown']}\n"
        for d in template_variables.get("documents", [])
    ])
    
    user_prompt = f"CANONICAL PROFESSIONAL KNOWLEDGE BASE:\n{docs_context}\n\nVISITOR QUESTION:\n{template_variables.get('question', '')}\n"
    
    return [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_prompt}
    ]


@traceable(name="Mock.invoke", run_type="llm")
async def invoke_mock(
    messages: List[Dict[str, str]],
    template_variables: Dict[str, Any],
    model: str
) -> Dict[str, Any]:
    """Deterministic offline mock model execution traced as an LLM run."""
    q = template_variables.get("question", "").lower()
    docs = template_variables.get("documents", [])
    full_text = " ".join([d.get("content_markdown", "").lower() for d in docs])
    role = template_variables.get("role", "")
    company = template_variables.get("company", "")

    # Security check: prompt injection attempts
    if any(term in q for term in ["ignore instructions", "reveal prompt", "system prompt", "dump all documents"]):
        return {
            "answer": "I am designed exclusively to answer factual questions about my professional background and experience.",
            "evidence": [],
            "confidence": "low"
        }

    has_cyber = bool(re.search(r'\b(cyber|cybersecurity|security|dora|isms|resilience)\b', q))
    has_leadership = bool(re.search(r'\b(leadership|team|teams|manage|management|cito|cto)\b', q))
    has_ai = bool(re.search(r'\b(ai|ml|machine learning|governance)\b', q))
    has_banking = bool(re.search(r'\b(bank|banking|financial|credit|regulated)\b', q))

    def _get_best_source(keywords: List[str], fallback: str) -> str:
        for kw in keywords:
            for d in docs:
                if kw.lower() in d.get("title", "").lower() or kw.lower() in d.get("filename", "").lower():
                    return d.get("title", "")
        if docs:
            return docs[0].get("title", "")
        return fallback

    evidence = []

    if has_cyber and ("cybersecurity" in full_text or "isms" in full_text or "security" in full_text):
        evidence.append({
            "source_title": _get_best_source(["cybersecurity", "security", "experience"], "Fictional Development Profile"),
            "excerpt": "The fictional sample profile documents security and operational-resilience responsibilities."
        })
        if len(docs) > 1:
            evidence.append({
                "source_title": _get_best_source(["cybersecurity", "grc", "overview"], "Cybersecurity, Operational Resilience & GRC"),
                "excerpt": "The sample evidence describes reviewable security-governance practices."
            })
        return {
            "answer": f"The supplied sample evidence contains security and operational-resilience experience relevant to the {role} position at {company}. This offline response is fictional development data, not a claim about a real candidate.",
            "evidence": evidence,
            "confidence": "high"
        }

    if has_ai:
        evidence.append({
            "source_title": _get_best_source(["ai", "governance", "overview"], "AI, Machine Learning & Data Governance"),
            "excerpt": "Prototyped an evidence-linked knowledge assistant with human review."
        })
        return {
            "answer": f"For the {role} role at {company}, the fictional sample evidence demonstrates an evidence-linked assistant with human review and separation between source documents and generated prose.",
            "evidence": evidence,
            "confidence": "high"
        }

    has_cloud = bool(re.search(r'\b(cloud|azure|aws|architecture|infrastructure|modernization|togaf|safe)\b', q))

    if has_leadership or has_banking or has_cloud:
        evidence.append({
            "source_title": _get_best_source(["experience", "overview", "cv"], "Selected Experience — Fictional Example"),
            "excerpt": "Defined a platform modernization roadmap and coordinated engineering, security, and product planning."
        })
        return {
            "answer": f"The fictional sample evidence demonstrates technology leadership and platform planning relevant to the {role} position at {company}. Replace the seed documents with verified candidate material before using this response externally.",
            "evidence": evidence,
            "confidence": "high"
        }

    return {
        "answer": "No verified evidence was found for this specific claim.",
        "evidence": [],
        "confidence": "unavailable"
    }


DEFAULT_GEMINI_FALLBACK_MODELS = [
    "gemini-3.6-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.7-flash",
    "gemini-flash-latest",
]

GEMINI_MODEL_NAMES = {
    "gemini-3.6-flash": "Google Gemini 3.6 Flash",
    "gemini-3-flash-preview": "Google Gemini 3 Flash",
    "gemini-3.1-flash-lite": "Google Gemini 3.1 Flash Lite",
    "gemini-3.5-flash": "Google Gemini 3.5 Flash",
    "gemini-3.7-flash": "Google Gemini 3.7 Flash",
    "gemini-flash-latest": "Google Gemini Flash",
}

_MODEL_COOLDOWN_UNTIL: Dict[str, float] = {}
_SHARED_LLM_CLIENT: Optional[httpx.AsyncClient] = None


def _get_llm_http_client(request_timeout: float = 12.0) -> httpx.AsyncClient:
    global _SHARED_LLM_CLIENT
    if _SHARED_LLM_CLIENT is None or _SHARED_LLM_CLIENT.is_closed:
        _SHARED_LLM_CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(request_timeout, connect=min(5.0, request_timeout)),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=25),
        )
    return _SHARED_LLM_CLIENT


@traceable(name="Gemini.generateContent", run_type="llm")
async def _invoke_gemini_model(
    client: httpx.AsyncClient,
    model_name: str,
    attempt: int,
    url: str,
    payload: Dict[str, Any]
) -> httpx.Response:
    """Traced individual HTTP attempt to a specific Gemini model endpoint."""
    return await client.post(url, json=payload)


@traceable(name="Gemini.invoke", run_type="llm")
async def invoke_gemini(
    messages: List[Dict[str, str]],
    template_variables: Dict[str, Any],
    model: str,
    api_key: str,
    fallback_models: Optional[List[str]] = None,
    request_timeout: float = 12.0
) -> Dict[str, Any]:
    """Traced LLM call executing Google Gemini inference with fast failover, connection pooling, and 429 cooldown."""
    import time as _time

    system_text = next((m["content"] for m in messages if m.get("role") == "system"), "")
    user_text = next((m["content"] for m in messages if m.get("role") == "user"), "")

    payload = {
        "system_instruction": {
            "parts": [{"text": system_text}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_text}]
            }
        ],
        "generationConfig": {
            "temperature": 0.2
        }
    }

    fallbacks = fallback_models or DEFAULT_GEMINI_FALLBACK_MODELS
    all_candidates = [model] + [m for m in fallbacks if m != model]
    now_ts = _time.time()
    active_candidates = [m for m in all_candidates if _MODEL_COOLDOWN_UNTIL.get(m, 0.0) <= now_ts]
    cooldown_candidates = [m for m in all_candidates if _MODEL_COOLDOWN_UNTIL.get(m, 0.0) > now_ts]
    candidate_models = active_candidates + cooldown_candidates
    last_exception = None

    client = _get_llm_http_client(request_timeout)
    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        for attempt in range(2):
            try:
                resp = await _invoke_gemini_model(
                    client=client,
                    model_name=model_name,
                    attempt=attempt,
                    url=url,
                    payload=payload
                )
                if resp.status_code == 200:
                    _MODEL_COOLDOWN_UNTIL.pop(model_name, None)
                    data = resp.json()
                    parts = data["candidates"][0]["content"].get("parts", [])
                    non_thought_parts = [
                        p.get("text", "") for p in parts if not p.get("thought") and "text" in p
                    ]
                    text_response = (
                        "\n".join(non_thought_parts)
                        if non_thought_parts
                        else (parts[0].get("text", "") if parts else "")
                    ).strip()
                    cleaned_json = _strip_json_fences(text_response)
                    try:
                        raw_parsed = json.loads(cleaned_json)
                        if not isinstance(raw_parsed, dict):
                            raw_parsed = {"answer": text_response}
                    except Exception:
                        raw_parsed = {"answer": text_response}
                    raw_parsed.setdefault(
                        "model_name",
                        GEMINI_MODEL_NAMES.get(model_name, f"Google Gemini ({model_name})")
                    )
                    return raw_parsed
                elif resp.status_code == 429:
                    _MODEL_COOLDOWN_UNTIL[model_name] = _time.time() + 60.0
                    resp.raise_for_status()
                elif resp.status_code in (500, 503) and attempt == 0:
                    await asyncio.sleep(0.3)
                    continue
                else:
                    resp.raise_for_status()
            except httpx.TimeoutException as err:
                last_exception = err
                # Do not retry a model that already timed out; fail over immediately
                break
            except httpx.HTTPStatusError as err:
                last_exception = err
                if err.response is not None and err.response.status_code == 429:
                    _MODEL_COOLDOWN_UNTIL[model_name] = _time.time() + 60.0
                # Fail over immediately on 429 (quota) or 4xx; only retry 500/503 once
                if err.response is not None and err.response.status_code not in (500, 503):
                    break
                await asyncio.sleep(0.3)
            except Exception as err:
                last_exception = err
                break

    if last_exception:
        raise last_exception
    raise RuntimeError("Failed to generate answer from Gemini provider.")


@traceable(name="OpenAI.invoke", run_type="llm")
async def invoke_openai(
    messages: List[Dict[str, str]],
    template_variables: Dict[str, Any],
    model: str,
    api_key: str
) -> Dict[str, Any]:
    """Traced LLM call executing OpenAI Chat Completions inference."""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    candidate_models = [model] + [m for m in ["gpt-4.1-mini", "gpt-4o-mini", "gpt-4o"] if m != model]
    last_err = None
    async with httpx.AsyncClient(timeout=25.0) as client:
        for om in candidate_models:
            payload = {
                "model": om,
                "messages": messages,
                "temperature": 0.2
            }
            try:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                cleaned_json = _strip_json_fences(content)
                try:
                    raw_parsed = json.loads(cleaned_json)
                    if not isinstance(raw_parsed, dict):
                        raw_parsed = {"answer": content}
                except Exception:
                    raw_parsed = {"answer": content}
                raw_parsed.setdefault("model_name", f"OpenAI ({om})")
                return raw_parsed
            except Exception as err:
                last_err = err
                continue
    if last_err:
        raise last_err
    raise RuntimeError("Failed to generate answer from OpenAI provider.")


class MockLLMProvider:
    """Deterministic offline provider for fast unit tests and verification."""

    def get_model_name(self) -> str:
        return "Mock AI Engine (Offline / Test)"

    async def generate_answer(
        self,
        question: str,
        application: Application,
        documents: List[Document]
    ) -> Dict[str, Any]:
        template_variables = serialize_application_context(application, question, documents)
        messages = render_qa_messages(template_variables)
        raw_parsed = await invoke_mock(
            messages=messages,
            template_variables=template_variables,
            model=self.get_model_name()
        )
        return validate_and_filter_llm_response(raw_parsed, documents, self.get_model_name())

    async def stream_answer(
        self,
        question: str,
        application: Application,
        documents: List[Document]
    ):
        result = await self.generate_answer(question, application, documents)
        words = result["answer"].split()
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield {"type": "token", "content": chunk}
            await asyncio.sleep(0.01)

        yield {
            "type": "metadata",
            "model_name": self.get_model_name(),
            "confidence": result.get("confidence", "medium"),
            "evidence": result.get("evidence", []),
            "status": "ok"
        }


class GeminiLLMProvider:
    """Calls Google Gemini API with automatic model cascade failover and OpenAI backup."""

    FALLBACK_MODELS = DEFAULT_GEMINI_FALLBACK_MODELS

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def get_model_name(self) -> str:
        return GEMINI_MODEL_NAMES.get(self.model, f"Google Gemini ({self.model})")

    async def generate_answer(
        self,
        question: str,
        application: Application,
        documents: List[Document]
    ) -> Dict[str, Any]:
        template_variables = serialize_application_context(application, question, documents)
        messages = render_qa_messages(template_variables)
        try:
            raw_parsed = await invoke_gemini(
                messages=messages,
                template_variables=template_variables,
                model=self.model,
                api_key=self.api_key,
                fallback_models=self.FALLBACK_MODELS
            )
        except Exception as gemini_err:
            if settings.OPENAI_API_KEY:
                print(f"Notice: Gemini cascade failed ({gemini_err}); failing over to OpenAI.")
                raw_parsed = await invoke_openai(
                    messages=messages,
                    template_variables=template_variables,
                    model=settings.OPENAI_MODEL or "gpt-4.1-mini",
                    api_key=settings.OPENAI_API_KEY,
                )
            else:
                raise gemini_err
        return validate_and_filter_llm_response(raw_parsed, documents, self.get_model_name())

    async def stream_answer(
        self,
        question: str,
        application: Application,
        documents: List[Document]
    ):
        result = await self.generate_answer(question, application, documents)
        words = result["answer"].split()
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield {"type": "token", "content": chunk}
            await asyncio.sleep(0.015)

        yield {
            "type": "metadata",
            "model_name": result.get("model_name") or self.get_model_name(),
            "confidence": result.get("confidence", "medium"),
            "evidence": result.get("evidence", []),
            "status": "ok"
        }

    async def generate_cover_letter_summary(
        self,
        cover_letter_text: Optional[str],
        role: str,
        company: str,
        job_description: str
    ) -> Dict[str, Any]:
        prompt = f"""You are an executive talent evaluator. Given the candidate's Cover Letter (or career background) and the target Role & Job Description, generate:
1. "summary": A concise 2-3 sentence overview of the candidate's core motivation, strategic alignment, and value proposition for the role.
2. "fit_highlights": An array of 3 to 5 clear, high-impact bullet points explaining explicitly why the candidate fits the role and requirements.

Target Role: {role}
Company: {company}
Job Description:
{job_description}

Cover Letter / Context:
{cover_letter_text or "General application context"}

Return valid JSON with keys: "summary" (string), "fit_highlights" (array of 3-5 strings).
"""
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json", "temperature": 0.2}
        }
        candidate_models = [self.model] + [m for m in self.FALLBACK_MODELS if m != self.model]
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=5.0)) as client:
            for model_name in candidate_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        text_response = data["candidates"][0]["content"]["parts"][0]["text"]
                        return json.loads(text_response)
                except Exception:
                    continue
        return generate_default_cover_letter_summary(cover_letter_text, role, company, job_description)

    async def generate_suggested_questions(
        self,
        job_description: str,
        role: str,
        company: str,
        candidate_name: str
    ) -> List[str]:
        prompt = f"""Given the job description and requirements for {role} at {company}, generate 4 concise, high-impact screening questions that a recruiter or hiring manager would ask {candidate_name} to verify their experience against the stated requirements.

Job Description & Requirements:
{job_description}

Return valid JSON matching schema:
{{"questions": ["question 1", "question 2", "question 3", "question 4"]}}
"""
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json", "temperature": 0.2}
        }
        candidate_models = [self.model] + [m for m in self.FALLBACK_MODELS if m != self.model]
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=5.0)) as client:
            for model_name in candidate_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        text_response = data["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = json.loads(text_response)
                        if isinstance(parsed.get("questions"), list) and len(parsed["questions"]) > 0:
                            return parsed["questions"][:4]
                except Exception:
                    continue
        return generate_default_suggested_questions(job_description, role, company, candidate_name)


class OpenAILLMProvider:
    """Calls OpenAI Chat Completions API (e.g. gpt-5.6-terra)."""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def get_model_name(self) -> str:
        name_map = {
            "gpt-5.6-terra": "OpenAI GPT-5.6 Terra",
            "gpt-4o": "OpenAI GPT-4o",
            "gpt-4o-mini": "OpenAI GPT-4o Mini",
        }
        return name_map.get(self.model, f"OpenAI ({self.model})")

    async def generate_answer(
        self,
        question: str,
        application: Application,
        documents: List[Document]
    ) -> Dict[str, Any]:
        template_variables = serialize_application_context(application, question, documents)
        messages = render_qa_messages(template_variables)
        raw_parsed = await invoke_openai(
            messages=messages,
            template_variables=template_variables,
            model=self.model,
            api_key=self.api_key
        )
        return validate_and_filter_llm_response(raw_parsed, documents, self.get_model_name())

    async def stream_answer(
        self,
        question: str,
        application: Application,
        documents: List[Document]
    ):
        result = await self.generate_answer(question, application, documents)
        words = result["answer"].split()
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield {"type": "token", "content": chunk}
            await asyncio.sleep(0.015)

        yield {
            "type": "metadata",
            "model_name": self.get_model_name(),
            "confidence": result.get("confidence", "medium"),
            "evidence": result.get("evidence", []),
            "status": "ok"
        }

    async def generate_cover_letter_summary(
        self,
        cover_letter_text: Optional[str],
        role: str,
        company: str,
        job_description: str
    ) -> Dict[str, Any]:
        url = "https://api.openai.com/v1/chat/completions"
        prompt = f"""You are an executive talent evaluator. Given the candidate's Cover Letter (or career background) and the target Role & Job Description, generate:
1. "summary": A concise 2-3 sentence overview of the candidate's core motivation, strategic alignment, and value proposition for the role.
2. "fit_highlights": An array of 3 to 5 clear, high-impact bullet points explaining explicitly why the candidate fits the role and requirements.

Target Role: {role}
Company: {company}
Job Description:
{job_description}

Cover Letter / Context:
{cover_letter_text or "General application context"}

Return valid JSON with keys: "summary" (string), "fit_highlights" (array of 3-5 strings).
"""
        messages = [{"role": "user", "content": prompt}]
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    return json.loads(content)
        except Exception:
            pass
        return generate_default_cover_letter_summary(cover_letter_text, role, company, job_description)

    async def generate_suggested_questions(
        self,
        job_description: str,
        role: str,
        company: str,
        candidate_name: str
    ) -> List[str]:
        url = "https://api.openai.com/v1/chat/completions"
        prompt = f"""Given the job description and requirements for {role} at {company}, generate 4 concise, high-impact screening questions that a recruiter or hiring manager would ask {candidate_name} to verify their experience against the stated requirements.

Job Description & Requirements:
{job_description}

Return valid JSON matching schema:
{{"questions": ["question 1", "question 2", "question 3", "question 4"]}}
"""
        messages = [{"role": "user", "content": prompt}]
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    if isinstance(parsed.get("questions"), list) and len(parsed["questions"]) > 0:
                        return parsed["questions"][:4]
        except Exception:
            pass
        return generate_default_suggested_questions(job_description, role, company, candidate_name)


class UnavailableLLMProvider:
    """Fail-closed provider returning truthful service-unavailable responses in production."""

    def __init__(self, reason: str = "AI reasoning service is temporarily unavailable."):
        self.reason = reason

    def get_model_name(self) -> str:
        return "AI Service Unavailable (Fail-Closed)"

    async def generate_answer(
        self,
        question: str,
        application: Application,
        documents: List[Document]
    ) -> Dict[str, Any]:
        return {
            "answer": (
                "AI reasoning service is temporarily unavailable. Upstream AI credentials are not configured "
                f"or the inference engine is offline. Please review the attached verified documents directly or contact {settings.CANDIDATE_NAME}."
            ),
            "evidence": [],
            "confidence": "unavailable",
            "model_name": self.get_model_name(),
            "status": "service_unavailable"
        }

    async def stream_answer(
        self,
        question: str,
        application: Application,
        documents: List[Document]
    ):
        res = await self.generate_answer(question, application, documents)
        yield {"type": "token", "content": res["answer"]}
        yield {
            "type": "metadata",
            "model_name": self.get_model_name(),
            "confidence": "unavailable",
            "evidence": [],
            "status": "service_unavailable"
        }

    async def generate_cover_letter_summary(
        self,
        cover_letter_text: Optional[str],
        role: str,
        company: str,
        job_description: str
    ) -> Dict[str, Any]:
        return generate_default_cover_letter_summary(cover_letter_text, role, company, job_description)

    async def generate_suggested_questions(
        self,
        job_description: str,
        role: str,
        company: str,
        candidate_name: str
    ) -> List[str]:
        return generate_default_suggested_questions(job_description, role, company, candidate_name)


class AnswerSynthesizer:
    """Synthesizes role-aware answers strictly grounded in canonical professional facts."""

    def __init__(self):
        self.provider = None
        self.init_provider()

    def init_provider(self):
        import os
        provider_name = settings.LLM_PROVIDER.lower()
        is_test = (
            settings.ENV.lower() in ("test", "testing") or
            bool(os.environ.get("PYTEST_CURRENT_TEST"))
        )

        if provider_name == "gemini" and settings.GEMINI_API_KEY:
            self.provider = GeminiLLMProvider(settings.GEMINI_API_KEY, settings.GEMINI_MODEL)
        elif provider_name == "openai" and settings.OPENAI_API_KEY:
            self.provider = OpenAILLMProvider(settings.OPENAI_API_KEY, settings.OPENAI_MODEL)
        elif settings.ENV.lower() == "production":
            self.provider = UnavailableLLMProvider("Production AI credentials not configured.")
        elif is_test or provider_name == "mock":
            self.provider = MockLLMProvider()
        else:
            self.provider = UnavailableLLMProvider("AI credentials (GEMINI_API_KEY / OPENAI_API_KEY) are not configured.")

    def get_model_name(self) -> str:
        self.init_provider()
        if hasattr(self.provider, "get_model_name"):
            return self.provider.get_model_name()
        return "AI Engine"

    @traceable(run_type="chain", name="AnswerSynthesizer.answer_question")
    async def answer_question(
        self,
        question: str,
        application: Application,
        documents: List[Document]
    ) -> Dict[str, Any]:
        self.init_provider()
        try:
            result = await self.provider.generate_answer(question, application, documents)

            answer = result.get("answer", "")
            evidence = result.get("evidence", [])
            confidence = result.get("confidence", "medium")
            model_name = result.get("model_name", self.get_model_name())
            status_code = result.get("status", "ok")

            return {
                "answer": answer,
                "evidence": evidence,
                "confidence": confidence,
                "model_name": model_name,
                "status": status_code
            }
        except Exception as e:
            print(f"Error in AnswerSynthesizer: {e}")
            return {
                "answer": (
                    "AI reasoning service encountered an error while synthesizing the answer. "
                    f"Please review the attached verified documents directly or contact {settings.CANDIDATE_NAME}."
                ),
                "evidence": [],
                "confidence": "unavailable",
                "model_name": self.get_model_name(),
                "status": "service_unavailable"
            }

    @traceable(run_type="chain", name="AnswerSynthesizer.stream_answer")
    async def stream_answer(
        self,
        question: str,
        application: Application,
        documents: List[Document]
    ):
        self.init_provider()
        try:
            if hasattr(self.provider, "stream_answer"):
                async for chunk in self.provider.stream_answer(question, application, documents):
                    yield chunk
            else:
                res = await self.answer_question(question, application, documents)
                yield {"type": "token", "content": res["answer"]}
                yield {
                    "type": "metadata",
                    "model_name": res.get("model_name", self.get_model_name()),
                    "confidence": res.get("confidence", "medium"),
                    "evidence": res.get("evidence", []),
                    "status": res.get("status", "ok")
                }
        except Exception as e:
            print(f"Error streaming in AnswerSynthesizer: {e}")
            yield {
                "type": "token",
                "content": "AI reasoning service encountered an error while streaming the answer."
            }
            yield {
                "type": "metadata",
                "model_name": self.get_model_name(),
                "confidence": "unavailable",
                "evidence": [],
                "status": "service_unavailable"
            }

    @traceable(run_type="chain", name="AnswerSynthesizer.generate_cover_letter_summary")
    async def generate_cover_letter_summary(
        self,
        cover_letter_text: Optional[str],
        role: str,
        company: str,
        job_description: str
    ) -> Dict[str, Any]:
        self.init_provider()
        try:
            if hasattr(self.provider, "generate_cover_letter_summary"):
                res = await self.provider.generate_cover_letter_summary(
                    cover_letter_text, role, company, job_description
                )
                if isinstance(res, dict) and "summary" in res and "fit_highlights" in res:
                    return res
        except Exception as e:
            print(f"Error in generate_cover_letter_summary: {e}")
        return generate_default_cover_letter_summary(cover_letter_text, role, company, job_description)

    @traceable(run_type="chain", name="AnswerSynthesizer.generate_suggested_questions")
    async def generate_suggested_questions(
        self,
        job_description: str,
        role: str,
        company: str,
        candidate_name: str
    ) -> List[str]:
        self.init_provider()
        try:
            if hasattr(self.provider, "generate_suggested_questions"):
                questions = await self.provider.generate_suggested_questions(
                    job_description, role, company, candidate_name
                )
                if isinstance(questions, list) and len(questions) > 0:
                    return questions[:4]
        except Exception as e:
            print(f"Error in generate_suggested_questions: {e}")
        return generate_default_suggested_questions(job_description, role, company, candidate_name)
