import asyncio
import base64
import html
import io
import ipaddress
import json
import os
import re
import socket
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import quote, urljoin, urlparse

import httpx
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer

from backend.app.config import settings
from backend.app.models import Document
from backend.app.services.ai import DEFAULT_GEMINI_FALLBACK_MODELS


BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
}


def normalize_job_url(raw_url: str) -> str:
    """Validates and normalizes a user-supplied job posting URL."""
    url = (raw_url or "").strip()
    if not url:
        raise ValueError("Job ad URL is required.")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"Invalid URL: {raw_url}")
    if parsed.username or parsed.password:
        raise ValueError("Job ad URLs must not contain credentials.")
    if parsed.port not in (None, 80, 443):
        raise ValueError("Job ad URLs may use only standard HTTP or HTTPS ports.")
    return url


def _is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.is_global


async def _validate_public_http_url(url: str) -> None:
    """Reject destinations that could reach local, private, or metadata services."""
    parsed = urlparse(normalize_job_url(url))
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise ValueError("Local and private job URL destinations are not allowed.")

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise ValueError("Local and private job URL destinations are not allowed.")
        return

    try:
        records = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError("Job ad hostname could not be resolved.") from exc

    addresses = {record[4][0] for record in records}
    if not addresses or any(not _is_public_address(value) for value in addresses):
        raise ValueError("Local and private job URL destinations are not allowed.")


async def _safe_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int,
    max_redirects: int = 3,
) -> httpx.Response:
    """Fetch a bounded public resource and revalidate every redirect target."""
    current_url = normalize_job_url(url)
    for _ in range(max_redirects + 1):
        await _validate_public_http_url(current_url)
        async with client.stream("GET", current_url) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("Redirect response did not include a destination.")
                current_url = urljoin(current_url, location)
                continue

            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise ValueError("Remote response exceeded the allowed size.")
            return httpx.Response(
                status_code=response.status_code,
                headers=response.headers,
                content=bytes(body),
                request=response.request,
            )
    raise ValueError("Remote response exceeded the redirect limit.")


def _extract_meta_content(raw_html: str, attr_name: str, attr_val: str) -> str:
    pattern1 = rf'<meta[^>]+{attr_name}=["\']{re.escape(attr_val)}["\'][^>]+content=["\']([^"\']+)["\']'
    m = re.search(pattern1, raw_html, re.IGNORECASE)
    if m:
        return html.unescape(m.group(1)).strip()
    pattern2 = rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+{attr_name}=["\']{re.escape(attr_val)}["\']'
    m2 = re.search(pattern2, raw_html, re.IGNORECASE)
    if m2:
        return html.unescape(m2.group(1)).strip()
    return ""


def _extract_json_ld_job_posting(raw_html: str) -> Dict[str, str]:
    """Extracts schema.org JobPosting fields if embedded in JSON-LD script tags."""
    result: Dict[str, str] = {}
    scripts = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        raw_html,
        re.IGNORECASE | re.DOTALL,
    )
    for script_body in scripts:
        try:
            data = json.loads(script_body.strip())
            candidates = data if isinstance(data, list) else [data]
            for item in list(candidates):
                if isinstance(item, dict) and "@graph" in item and isinstance(item["@graph"], list):
                    candidates.extend(item["@graph"])
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("@type") or "")
                if "JobPosting" in item_type:
                    title = str(item.get("title") or "").strip()
                    org = item.get("hiringOrganization")
                    company = ""
                    if isinstance(org, dict):
                        company = str(org.get("name") or "").strip()
                    elif isinstance(org, str):
                        company = org.strip()
                    desc_html = str(item.get("description") or "").strip()
                    desc_text = re.sub(r"<[^>]+>", " ", html.unescape(desc_html))
                    desc_text = re.sub(r"\s+", " ", desc_text).strip()
                    if title:
                        result["title"] = title
                    if company:
                        result["company"] = company
                    if desc_text:
                        result["description"] = desc_text
                    return result
        except Exception:
            continue
    return result


def _html_to_clean_text(raw_html: str) -> str:
    """Strips scripts, styles, and tags from HTML to produce clean readable text."""
    cleaned = re.sub(
        r"<(script|style|noscript|svg|header|footer|nav)[^>]*>.*?</\1>",
        " ",
        raw_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(r"<(br|p|div|li|tr|h[1-6]|section|article)[^>]*>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    lines = []
    for raw_line in cleaned.splitlines():
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if line and len(line) > 1:
            lines.append(line)
    return "\n".join(lines)[:25000]


def build_svg_screendump_data_url(
    url: str,
    domain: str,
    page_title: str,
    site_name: str,
    excerpt: str,
) -> str:
    """
    Creates a crisp browser-viewport visual screendump SVG (as a base64 data URI)
    representing the captured webpage when an external headless PNG screenshot is
    blocked or in offline test environments.
    """
    safe_url = html.escape((url or "")[:75])
    safe_domain = html.escape((domain or "job-board")[:40])
    safe_site = html.escape((site_name or domain or "Job Posting").upper()[:36])
    safe_title = html.escape((page_title or "Job Advertisement")[:68])
    safe_title_2 = html.escape((page_title or "")[68:130])

    raw_lines = [l.strip() for l in (excerpt or "").splitlines() if len(l.strip()) > 20]
    if not raw_lines and excerpt:
        words = excerpt.split()
        raw_lines = [" ".join(words[i : i + 12]) for i in range(0, min(len(words), 60), 12)]

    preview_lines = [html.escape(l[:88]) for l in raw_lines[:5]]
    while len(preview_lines) < 4:
        preview_lines.append("")

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="800" height="460" viewBox="0 0 800 460">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#f8fafc"/>
      <stop offset="100%" stop-color="#eef2ff"/>
    </linearGradient>
    <linearGradient id="Accent" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#0284c7"/>
      <stop offset="100%" stop-color="#2563eb"/>
    </linearGradient>
  </defs>
  <rect width="800" height="460" rx="14" fill="url(#bg)" stroke="#cbd5e1" stroke-width="2"/>
  <rect width="800" height="44" rx="14" fill="#0f172a"/>
  <rect y="28" width="800" height="16" fill="#0f172a"/>
  <circle cx="22" cy="22" r="6" fill="#ef4444"/>
  <circle cx="42" cy="22" r="6" fill="#f59e0b"/>
  <circle cx="62" cy="22" r="6" fill="#10b981"/>
  <rect x="92" y="10" width="580" height="24" rx="6" fill="#1e293b"/>
  <text x="106" y="26" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-size="11" fill="#94a3b8">{safe_url}</text>
  <rect x="688" y="11" width="94" height="22" rx="11" fill="#0284c7"/>
  <text x="735" y="26" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-size="10" font-weight="bold" fill="#ffffff">LIVE SNAPSHOT</text>

  <rect x="28" y="64" width="744" height="368" rx="12" fill="#ffffff" stroke="#e2e8f0" stroke-width="1.5"/>
  <rect x="28" y="64" width="744" height="6" rx="3" fill="url(#Accent)"/>

  <rect x="52" y="90" width="190" height="24" rx="6" fill="#e0f2fe"/>
  <text x="64" y="106" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-size="11" font-weight="bold" fill="#0369a1">{safe_site}</text>

  <text x="52" y="146" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-size="21" font-weight="bold" fill="#0f172a">{safe_title}</text>
  <text x="52" y="172" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-size="17" font-weight="bold" fill="#1e293b">{safe_title_2}</text>

  <line x1="52" y1="192" x2="748" y2="192" stroke="#e2e8f0" stroke-width="1"/>

  <text x="52" y="222" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-size="13" fill="#334155">{preview_lines[0]}</text>
  <text x="52" y="248" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-size="13" fill="#334155">{preview_lines[1]}</text>
  <text x="52" y="274" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-size="13" fill="#475569">{preview_lines[2]}</text>
  <text x="52" y="300" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-size="13" fill="#475569">{preview_lines[3]}</text>

  <rect x="52" y="336" width="696" height="68" rx="8" fill="#f8fafc" stroke="#e2e8f0" stroke-width="1"/>
  <text x="70" y="362" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-size="11" font-weight="bold" fill="#0f172a">SOURCE DOMAIN: {safe_domain}</text>
  <text x="70" y="384" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-size="11" fill="#64748b">Verified webpage content extracted for evidence-grounded CV &amp; Personal Letter tailoring</text>
</svg>"""
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


async def _capture_live_screenshot_data_url(url: str, og_image_url: str = "") -> Optional[str]:
    """
    Attempts to capture a live visual viewport screenshot PNG of the submitted URL
    via Microlink headless browser API, falling back to the page's og:image if available.
    """
    is_test = (
        settings.ENV.lower() in ("test", "testing")
        or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    )
    if is_test:
        return None

    timeout = httpx.Timeout(8.5, connect=4.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers=BROWSER_HEADERS) as client:
        # 1. Try Microlink headless Chromium screenshot
        try:
            api_url = f"https://api.microlink.io/?url={quote(url, safe='')}&screenshot=true&meta=false"
            resp = await _safe_get(client, api_url, max_bytes=1_000_000)
            if resp.status_code == 200:
                payload = resp.json()
                shot_url = (
                    payload.get("data", {})
                    .get("screenshot", {})
                    .get("url")
                )
                if shot_url:
                    img_resp = await _safe_get(client, shot_url, max_bytes=5_000_000)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1500:
                        ctype = img_resp.headers.get("content-type", "image/png").split(";")[0]
                        b64 = base64.b64encode(img_resp.content).decode("ascii")
                        return f"data:{ctype};base64,{b64}"
        except Exception:
            pass

        # 2. Fallback: Fetch page og:image if available
        if og_image_url and og_image_url.startswith(("http://", "https://")):
            try:
                img_resp = await _safe_get(client, og_image_url, max_bytes=5_000_000)
                if img_resp.status_code == 200 and len(img_resp.content) > 1500:
                    ctype = img_resp.headers.get("content-type", "image/png").split(";")[0]
                    if ctype.startswith("image/"):
                        b64 = base64.b64encode(img_resp.content).decode("ascii")
                        return f"data:{ctype};base64,{b64}"
            except Exception:
                pass

    return None


async def fetch_job_page_and_screenshot(raw_url: str) -> Dict[str, Any]:
    """
    Fetches the job ad webpage content, metadata, and captures a small screendump
    (live headless screenshot PNG or high-DPI visual snapshot card fallback).
    """
    url = normalize_job_url(raw_url)
    parsed = urlparse(url)
    domain = parsed.netloc

    page_title = ""
    site_name = domain
    og_description = ""
    og_image = ""
    json_ld_info: Dict[str, str] = {}
    extracted_text = ""

    is_test = (
        settings.ENV.lower() in ("test", "testing")
        or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    )
    if not is_test:
        await _validate_public_http_url(url)

    async def _fetch_direct_html() -> None:
        nonlocal page_title, site_name, og_description, og_image, json_ld_info, extracted_text
        if is_test and ("example.com" in domain or "test.local" in domain):
            page_title = "Chief Technology Officer (CTO) — Example SaaS AB"
            site_name = "Example SaaS Careers"
            extracted_text = (
                "Chief Technology Officer (CTO) at Example SaaS AB.\n"
                "We are looking for an experienced executive technology leader with a strong background "
                "in B2B SaaS, cloud architecture, cybersecurity, DORA/ISO 27001 governance, and AI adoption.\n"
                "Responsibilities include leading 80+ engineers across the Nordics, modernizing core platforms, "
                "and partnering with the CEO and board on technology strategy."
            )
            return

        timeout = httpx.Timeout(10.0, connect=4.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers=BROWSER_HEADERS) as client:
            try:
                resp = await _safe_get(client, url, max_bytes=2_000_000)
                if resp.status_code < 400 and resp.text:
                    raw_html = resp.text
                    title_m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
                    if title_m:
                        page_title = re.sub(r"\s+", " ", html.unescape(title_m.group(1))).strip()
                    og_title = _extract_meta_content(raw_html, "property", "og:title") or _extract_meta_content(raw_html, "name", "twitter:title")
                    if og_title and (not page_title or len(og_title) > len(page_title)):
                        page_title = og_title
                    og_description = (
                        _extract_meta_content(raw_html, "property", "og:description")
                        or _extract_meta_content(raw_html, "name", "description")
                    )
                    site_name = _extract_meta_content(raw_html, "property", "og:site_name") or domain
                    raw_og_img = _extract_meta_content(raw_html, "property", "og:image")
                    if raw_og_img:
                        og_image = urljoin(url, raw_og_img)
                    json_ld_info = _extract_json_ld_job_posting(raw_html)
                    extracted_text = _html_to_clean_text(raw_html)
            except Exception as exc:
                print(f"Notice: Direct HTML fetch for {url} encountered: {exc}")

            # If JS-rendered job board or sparse text, enrich via Jina Reader
            if len(extracted_text) < 600 and not is_test:
                try:
                    jina_url = f"https://r.jina.ai/{url}"
                    jina_resp = await _safe_get(client, jina_url, max_bytes=2_000_000)
                    if jina_resp.status_code == 200 and len(jina_resp.text.strip()) > len(extracted_text):
                        extracted_text = jina_resp.text.strip()[:25000]
                        if not page_title:
                            first_line = extracted_text.splitlines()[0].lstrip("# ").strip()
                            if first_line:
                                page_title = first_line[:120]
                except Exception:
                    pass

    await _fetch_direct_html()

    # Combine JSON-LD description, og_description, and visible page text
    combined_parts = []
    if page_title:
        combined_parts.append(f"PAGE TITLE: {page_title}")
    if json_ld_info.get("company"):
        combined_parts.append(f"JSON-LD COMPANY: {json_ld_info['company']}")
    if json_ld_info.get("title"):
        combined_parts.append(f"JSON-LD ROLE: {json_ld_info['title']}")
    if og_description:
        combined_parts.append(f"META SUMMARY: {og_description}")
    if json_ld_info.get("description"):
        combined_parts.append(f"STRUCTURED JOB DESCRIPTION:\n{json_ld_info['description']}")
    if extracted_text:
        combined_parts.append(f"WEBPAGE CONTENT:\n{extracted_text}")

    full_text = "\n\n".join(combined_parts).strip()
    if not full_text:
        full_text = f"Job posting URL: {url} (Domain: {domain})"

    # Capture live screenshot or fall back to deterministic SVG snapshot card
    live_screenshot = await _capture_live_screenshot_data_url(url, og_image_url=og_image)
    excerpt_for_card = og_description or json_ld_info.get("description") or extracted_text or url
    screenshot_data_url = live_screenshot or build_svg_screendump_data_url(
        url=url,
        domain=domain,
        page_title=page_title or json_ld_info.get("title") or f"Job Ad on {domain}",
        site_name=site_name or domain,
        excerpt=excerpt_for_card,
    )

    return {
        "url": url,
        "domain": domain,
        "page_title": page_title or json_ld_info.get("title") or domain,
        "site_name": site_name or domain,
        "json_ld_company": json_ld_info.get("company", ""),
        "json_ld_role": json_ld_info.get("title", ""),
        "raw_text": full_text[:22000],
        "screenshot_data_url": screenshot_data_url,
    }


def _heuristic_analyze_job_posting(page_data: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic fallback parser for job ad metadata and language detection."""
    raw_text = (page_data.get("raw_text", "") or "").replace("\xa0", " ")
    page_title = (page_data.get("page_title", "") or "").replace("\xa0", " ")
    domain = page_data.get("domain", "")

    company = (page_data.get("json_ld_company") or "").replace("\xa0", " ").strip()
    role = (page_data.get("json_ld_role") or "").replace("\xa0", " ").strip()

    if not role and page_title:
        parts = [p.strip() for p in re.split(r"\s+[\-\|–—•]\s+", page_title) if p.strip()]
        if len(parts) >= 2:
            role = parts[0]
            if not company:
                company = parts[1]
        else:
            role = page_title[:80]

    if not company:
        host = re.sub(r"^(www\.|careers\.|jobs\.|karriar\.)", "", domain.lower())
        company = host.split(".")[0].replace("-", " ").title() if host else "Target Company"
    if not role:
        role = "Chief Technology Officer (CTO)"

    low = raw_text.lower()
    sv_markers = [" och ", " att ", " för ", " med ", " som ", " är ", " vi söker ", " tjänsten ", " erfarenhet "]
    sv_hits = sum(1 for m in sv_markers if m in f" {low} ")
    language = "sv" if sv_hits >= 3 else "en"

    if any(k in low for k in ["ciso", "security", "säkerhet", "dora", "nis2", "iso 27001", "risk"]):
        positioning = "POS-03: Technology Security, Resilience & Governance Leader"
    elif any(k in low for k in ["interim", "transformation", "turnaround"]):
        positioning = "POS-05: Interim Executive / Transformation Lead"
    elif any(k in low for k in ["ai ", "artificial intelligence", "data governance", "analytics"]):
        positioning = "POS-04: AI & Data Governance Executive / Advisor"
    elif any(k in low for k in ["saas", "product", "engineering", "cto", "platform"]):
        positioning = "POS-02: CTO / CITO — Regulated Platform & Product Technology"
    else:
        positioning = "POS-01: Enterprise CIO / Head of IT"

    requirements = [
        "Senior executive technology and organizational leadership experience",
        "Modern cloud architecture, platform modernization, and delivery excellence",
        "Information security governance, operational resilience, and regulatory compliance",
        "AI adoption, data strategy, and business-aligned digital transformation",
    ]

    ats_skills = [
        "Technology Leadership (CTO/CIO/CITO)",
        "Engineering & IT Organization Leadership",
        "Cloud Architecture (Microsoft Azure)",
        "Platform Modernization & Data Center Consolidation",
        "Information Security Governance (ISO / ISMS / CSIRT)",
        "Regulatory Compliance (relevant supervisory authorities / GDPR / SOX)",
        "Enterprise AI Strategy & Multi-Agent Systems",
        "Agile Delivery & SAFe / TOGAF Governance",
        "Regulated Financial & Insurance Platforms",
        "Vendor & Sourcing Governance",
        "Budget Optimization & Cost Control",
        "Executive Stakeholder Alignment",
    ]

    objections = [
        "Employment type and chronology: make permanent, interim, and consulting work explicit using only the supplied evidence.",
    ]

    return {
        "company": company[:100].strip(),
        "role": re.sub(r"[\s\-–—:|]+$", "", role[:120]).strip(),
        "language": language,
        "positioning_angle": positioning,
        "role_fit_proposition": (
            f"The supplied candidate evidence should be evaluated against the requirements for {role} at {company}; "
            "unsupported experience must be presented as a gap rather than inferred."
        ),
        "key_requirements": requirements,
        "ats_priority_skills": ats_skills,
        "recruiter_objections_and_mitigation": objections,
        "experiences_to_expand": ["The most relevant evidence-backed roles and projects"],
        "experiences_to_compress": ["Older or less relevant entries, while preserving chronology"],
        "application_gaps": [],
        "clean_job_description": raw_text[:4500],
    }


def _normalize_parsed_job_info(parsed: Dict[str, Any], fallback_info: Dict[str, Any]) -> Dict[str, Any]:
    parsed["company"] = str(parsed.get("company") or fallback_info["company"]).replace("\xa0", " ").strip()[:100]
    raw_role = str(parsed.get("role") or fallback_info["role"]).replace("\xa0", " ").strip()[:120]
    parsed["role"] = re.sub(r"[\s\-–—:|]+$", "", raw_role).strip() or fallback_info["role"]
    lang = str(parsed.get("language") or "en").lower().strip()
    parsed["language"] = "sv" if lang.startswith("sv") else "en"
    for k in (
        "key_requirements",
        "ats_priority_skills",
        "recruiter_objections_and_mitigation",
        "experiences_to_expand",
        "experiences_to_compress",
        "application_gaps",
    ):
        if not isinstance(parsed.get(k), list) or not parsed.get(k):
            parsed[k] = fallback_info.get(k, [])
    if not parsed.get("role_fit_proposition"):
        parsed["role_fit_proposition"] = fallback_info["role_fit_proposition"]
    if not parsed.get("clean_job_description"):
        parsed["clean_job_description"] = fallback_info["clean_job_description"]
    return parsed


async def analyze_job_posting(
    page_data: Dict[str, Any],
    custom_notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Stage 1: Role, SAP SuccessFactors / AI-ATS & Objection Strategy Analyzer.
    Extracts Company, Role, Language ('sv' or 'en'), dynamic Positioning Angle,
    One-Sentence Role-Fit Proposition, Key Requirements, up to 25 SAP/ATS Priority Skills,
    Recruiter Objections & Mitigation, Experience Expansion/Compression Plan, and Job Description.
    """
    fallback_info = _heuristic_analyze_job_posting(page_data)
    is_test = (
        settings.ENV.lower() in ("test", "testing")
        or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    )
    if is_test or settings.LLM_PROVIDER.lower() == "mock" or (not settings.GEMINI_API_KEY and not settings.OPENAI_API_KEY):
        return fallback_info

    prompt = f"""Act as an expert CV strategist, executive recruiter, and SAP SuccessFactors / AI-ATS recruitment-systems analyst.
Analyze the submitted job advertisement webpage for {settings.CANDIDATE_NAME}.

Webpage URL: {page_data.get('url')}
Webpage Title: {page_data.get('page_title')}
Additional Candidate Notes: {custom_notes or 'None'}

Webpage Content:
{page_data.get('raw_text', '')[:16000]}

Perform the following analysis before CV drafting:
1. ROLE INTERPRETATION & DYNAMIC POSITIONING:
   - Determine the role family, expected seniority, principal business purpose, and top outcomes the successful candidate must deliver.
   - Determine the most credible positioning category directly from the vacancy itself (e.g., POS-01: Enterprise CIO / Head of IT; POS-02: CTO / CITO — Regulated Platform & Product Technology; POS-03: Technology Security, Resilience & Governance Leader; POS-04: AI & Data Governance Executive / Advisor; POS-05: Interim Executive / Transformation Lead; or a tailored role-specific positioning if the vacancy is specialist, AI engineering, commercial, product, or operational). Do not force an unrelated persona onto the role.
   - Formulate a one-sentence role-fit proposition answering: "Why is {settings.CANDIDATE_NAME} especially relevant to this specific role?"
2. SAP SUCCESSFACTORS & AI-ATS SKILL EXTRACTION:
   - Extract explicit mandatory qualifications, primary skills, and secondary skills from the job advertisement.
   - Select up to 20 high-value, distinct (non-synonym) skills using the employer's exact terminology only where those skills are explicitly supported by the supplied canonical evidence.
3. RECRUITER OBJECTION DIAGNOSIS:
   - Identify 1 to 3 likely concerns a recruiter or hiring manager may have (for example employment type, seniority fit, industry transition, or title differences) and state how the CV should factually address each.
4. EXPERIENCE ALLOCATION PLAN:
   - Identify which career entries should be expanded with decisive evidence vs. compressed for chronology.

Return ONLY valid JSON with these exact keys:
{{
  "company": "Target company or recruiting agency name (concise, e.g. 'Example Security')",
  "role": "Target role title (concise, e.g. 'Chief Technology Officer (CTO)')",
  "language": "'sv' if the job ad is written primarily in Swedish, otherwise 'en'",
  "positioning_angle": "Selected positioning label (e.g. 'POS-02: CTO / CITO — Product & Platform Technology')",
  "role_fit_proposition": "One-sentence role-fit proposition in the job ad's language",
  "key_requirements": ["5 to 8 concise strings of the explicit core role requirements and expected outcomes"],
  "ats_priority_skills": ["Up to 20 distinct, high-value SAP SuccessFactors / ATS skills in the job ad's language"],
  "recruiter_objections_and_mitigation": ["1 to 3 strings describing a likely recruiter concern and its factual mitigation"],
  "experiences_to_expand": ["Career entries to expand with decisive evidence"],
  "experiences_to_compress": ["Career entries to keep concise for chronology"],
  "application_gaps": ["Any explicit requirement from the ad that requires candidate confirmation or must not be claimed as an exact match"],
  "clean_job_description": "Comprehensive, well-structured summary of the role responsibilities, requirements, and context (300-800 words) in the job ad's language"
}}
"""
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.1},
    }
    models = [settings.GEMINI_MODEL] + [
        m for m in DEFAULT_GEMINI_FALLBACK_MODELS if m != settings.GEMINI_MODEL
    ]
    timeout = httpx.Timeout(15.0, connect=4.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if settings.GEMINI_API_KEY:
            for model_name in models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={settings.GEMINI_API_KEY}"
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        parts = data["candidates"][0]["content"].get("parts", [])
                        non_thought = [p.get("text", "") for p in parts if not p.get("thought") and "text" in p]
                        text_out = "\n".join(non_thought) if non_thought else (parts[0].get("text", "") if parts else "")
                        text_out = re.sub(r"^```(?:json)?\s*\n?", "", text_out.strip(), flags=re.IGNORECASE)
                        text_out = re.sub(r"\n?```\s*$", "", text_out).strip()
                        parsed = json.loads(text_out)
                        if isinstance(parsed, dict) and parsed.get("company") and parsed.get("role"):
                            return _normalize_parsed_job_info(parsed, fallback_info)
                except Exception as exc:
                    print(f"Notice: analyze_job_posting on {model_name} failed: {exc}")
                    continue

        if settings.OPENAI_API_KEY:
            for om in [settings.OPENAI_MODEL or "gpt-4.1-mini", "gpt-4.1-mini", "gpt-4o-mini"]:
                try:
                    resp = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": om,
                            "messages": [{"role": "user", "content": prompt}],
                            "response_format": {"type": "json_object"},
                            "temperature": 0.1,
                        },
                    )
                    if resp.status_code == 200:
                        content = resp.json()["choices"][0]["message"]["content"]
                        parsed = json.loads(content)
                        if isinstance(parsed, dict) and parsed.get("company") and parsed.get("role"):
                            return _normalize_parsed_job_info(parsed, fallback_info)
                except Exception as exc:
                    print(f"Notice: analyze_job_posting on OpenAI {om} failed: {exc}")
                    continue

    return fallback_info


def render_match_analysis_markdown(job_info: Dict[str, Any], source_url: str) -> str:
    """Renders 02_Match_Analysis.md capturing Role Success Profile, SAP/ATS Skills, and CV Strategy."""
    company = job_info.get("company", "Target Company")
    role = job_info.get("role", "Target Role")
    lang = job_info.get("language", "en")
    positioning = job_info.get("positioning_angle", "")
    proposition = job_info.get("role_fit_proposition", "")
    reqs = "\n".join(f"- {r}" for r in (job_info.get("key_requirements") or []))
    skills = "\n".join(f"- {s}" for s in (job_info.get("ats_priority_skills") or []))
    objections = "\n".join(f"- {o}" for o in (job_info.get("recruiter_objections_and_mitigation") or []))
    expand = "\n".join(f"- {e}" for e in (job_info.get("experiences_to_expand") or []))
    compress = "\n".join(f"- {c}" for c in (job_info.get("experiences_to_compress") or []))
    gaps = "\n".join(f"- {g}" for g in (job_info.get("application_gaps") or [])) or "- None identified"

    return f"""# Role Success Profile & CV Strategy — {role} at {company}

- **Source URL:** {source_url}
- **Language:** {lang.upper()}
- **Selected Positioning:** {positioning}

## A. One-Sentence Role-Fit Proposition
> {proposition}

## B. Key Vacancy Requirements & Expected Outcomes
{reqs}

## C. Top SAP SuccessFactors & AI-ATS Priority Skills
{skills}

## D. Recruiter Objections & Factual Mitigation Strategy
{objections}

## E. Experience Space Allocation
### Expand (Decisive Evidence)
{expand}

### Compress (Chronological Continuity)
{compress}

## F. Identified Gaps / Confirmation Items (Not Claimed as Exact Match)
{gaps}
"""


def _build_tailoring_knowledge_context(documents: List[Document]) -> str:
    """Builds prioritized canonical evidence context for CV and Cover Letter generation."""
    if not documents:
        return ""
    # Prioritize Master Evidence Bank, Tailoring Rules, and Canonical CV
    def _sort_key(d: Document) -> int:
        t = (d.title + " " + d.filename).lower()
        if "evidence bank" in t:
            return 0
        if "tailoring rules" in t:
            return 1
        if "public cv" in t or "canonical" in t:
            return 2
        if "strategy" in t:
            return 3
        return 4

    ordered = sorted(documents, key=_sort_key)
    blocks = []
    total_chars = 0
    for doc in ordered:
        content = (doc.content_markdown or "").strip()
        if not content:
            continue
        if total_chars + len(content) > 95000:
            content = content[: max(4000, 95000 - total_chars)]
        blocks.append(f"=== CANONICAL DOCUMENT: {doc.title} ({doc.filename}) ===\n{content}\n")
        total_chars += len(content)
        if total_chars >= 95000:
            break
    return "\n".join(blocks)


def _generate_fallback_cv_markdown(job_info: Dict[str, Any]) -> str:
    """Evidence-grounded fallback CV markdown when running in offline/mock test mode."""
    company = job_info.get("company", "Target Company")
    role = job_info.get("role", "Chief Technology Officer")
    lang = job_info.get("language", "en")

    if lang == "sv":
        return f"""# {settings.CANDIDATE_NAME}
{settings.CANDIDATE_CONTACT_LINE}

## Senior Technology, Security & Transformation Executive — {role}

Senior teknologiledare med lång erfarenhet av att etablera, styra och modernisera IT-, arkitektur- och säkerhetsorganisationer i komplexa, reglerade och multinationella verksamheter i Norden och Europa. Jag har verkat som CIO, CTO och CITO med direkt ansvar för teknisk strategi, plattformsmodernisering, informationssäkerhet, molntransformation och budgetoptimering.

Min bakgrund kombinerar arkitekturell och teknisk förankring (inklusive Python, PyTorch, RAG, LangSmith och multi-agent-system) med affärsorienterat ledarskap. Under de senaste åren har mitt arbete fokuserat på ansvarsfull AI-implementering, datastyrning och regulatorisk efterlevnad (relevant supervisory authorities, GDPR, SOX, ISO), med fokus på att koppla tekniska beslut till mätbara affärsresultat för {company}.

## Kärnkompetenser

- **Exekutivt teknologiledarskap:** Lång erfarenhet som CIO, CTO och CITO i bank-, försäkrings- och teknikintensiva verksamheter
- **Organisations- & Leveransledning:** Ledning av distribuerade teknik-, arkitektur- och säkerhetsorganisationer i Norden och Europa
- **Plattformsmodernisering & Moln:** Molntransformation (Microsoft Azure), konsolidering av datacenter och mer än 30 % kostnadsreduktion
- **Informationssäkerhet & GRC:** Uppbyggnad av säkerhetsfunktioner, CSIRT, ISO-standarder, SOX, ISAE 3402 samt tillsyn under relevanta tillsynsmyndigheter
- **AI, Data & Modern utveckling:** Praktisk AI-strategi, generativ AI (PyTorch, OpenAI, Mistral, LangSmith, RAG) och Multi-Agent DevOps
- **Arkitekturstyrning & Agila arbetssätt:** Införande och anpassning av SAFe och TOGAF-baserad arkitekturstyrning

## Yrkeserfarenhet

### Example Consulting | 2020–Nuvarande
**Grundare & Exekutiv Konsult (Interim CTO / CIO / Rådgivare)**
- **Transit Agency (2025) – Rådgivare inom AI, Data & Analys:** Fiktivt exempeluppdrag för att demonstrera evidensbaserad CV-generering.
- **Regional Insurer (2024) – Teknisk Rådgivare:** Utvecklade styrningsramverk och implementeringsplan för centraliserad arkitekturstyrning inom en SAFe-baserad leveransmodell i linje med TOGAF.
- **Intern produktutveckling (2023) – Cyber Security Triage Using AI:** Leder design, utveckling och drift av en AI-agent för management- och transformationsrådgivning.
- **Example Security Venture (2020–2021) – VD & CTO:** Medledde ett joint venture inom cybersäkerhet och styrde utvecklingen och lanseringen av en digital säkerhetsstrategiplattform för SME-segmentet.
- **Regional Insurer (2019–2020) – Teknisk Projektledare:** Ledde upphandling, integration och utrullning av en molnbaserad IoT-lösning för vattenläckagedetektering med ROI under sex månader.
- **Konfidentiell kund (2017–2018) – Head of Architecture and Security:** Linjeansvar för en organisation om cirka 50 personer inom arkitektur och cybersäkerhet; etablerade CSIRT och stärkt säkerhetsstyrning.

### Example Financial Services | 2022–2023
**Chief Information and Technology Officer (CITO)**
- Medlem i koncernledningen med fullt IT-budgetansvar och ledning av chefer och team inom utveckling, drift och dataanalys i fyra nordiska länder.
- Ledde ett omfattande transformationsprogram med moln-först-strategi i Microsoft Azure och konsolidering av datacenter som sänkte IT-budgeten med över 30 %.
- Ansvarade för regelefterlevnad under relevanta finans- och dataskyddsmyndigheter.

### Example Insurance Group | 2015–2017
**Nordic CTO – Strategy, Architecture & Information Security**
- Drev den nordiska digitala transformationsagendan med fokus på agil leverans, innovation och etablerad IT-styrning som balanserade stabilitet och kostnadseffektivitet med innovationskraft.

### Example Bank Group | 2007–2015
**Senior Manager | Interim CIO | Head of IT Controllership**
- Innehade flera seniora IT-ledarroller i Norden och Europa; byggde upp en ny IT-kontrollfunktion (SOX, ISO, ISAE 3402) och deltog i etableringen av en gemensam moln- och infrastrukturplattform över 12 reglerade europeiska enheter.

## Tidigare karriär
- **Example Technology Services:** Business Developer med ansvar för pre-sales, key accounts och regional affärsutveckling.
- **Example Software Studio:** Senior Project Manager & Architect för säkra digitala tjänster.

## Utbildning & Certifieringar
- **M.Sc. i Informatik**, Example University (1990–1995)
- **AI-studier**, Example University (2023–2025)
- **Retorik – muntlig och skriftlig kommunikation**, Example School & Example University
- **Certifieringar:** Strategy Tools Global Coaches Certification (2020); tidigare certifierad CGEIT (ISACA)
"""

    return f"""# {settings.CANDIDATE_NAME}
{settings.CANDIDATE_CONTACT_LINE}

## Senior Technology, Security & Transformation Executive — {role}

Accomplished senior technology executive with extensive experience establishing, governing, and modernizing engineering, architecture, and information security functions across complex, multi-market, and highly regulated organizations. Having served as CIO, CTO, and CITO, I combine a strong technical and architectural foundation with decisive executive leadership.

My track record spans regulated banking and credit services, insurance, and technology-intensive organizations—balancing delivery speed and product innovation with platform scalability, cost efficiency, and regulatory resilience. In recent years, my work has increasingly focused on practical AI strategy, hands-on generative AI and multi-agent engineering (Python, PyTorch, OpenAI, Mistral, LangSmith, RAG), and architecture governance tailored to {company}.

## Core Competencies

- **Executive Technology Leadership:** Extensive C-level and senior leadership experience as CITO, CTO, and CIO across Nordic and European regulated organizations
- **Cloud & Platform Modernization:** Cloud-first transformation (Microsoft Azure), data-center consolidation, and >30% IT budget reduction
- **Security & Regulatory Governance:** Establishment of security functions and CSIRT operations; regulatory compliance under relevant supervisory authorities, GDPR, SOX, ISO, and ISAE 3402
- **AI & Modern Engineering:** Enterprise AI & data strategy, custom models in PyTorch, RAG ecosystems (LangSmith, ZEP), and secure Multi-Agent DevOps
- **Architecture & Delivery Models:** SAFe delivery tailoring, TOGAF-aligned centralized architecture governance, and technical debt reduction
- **Commercial & Stakeholder Alignment:** Executive management team participation, board dialogue, vendor/offshore governance, and connecting technology to measurable ROI

## Professional Experience

### Example Consulting | 2017–Present
**Founder & Executive Consultant (Interim CTO / CIO / Strategic Advisor)**
- **SL (2025) – Advisor on AI, Data & Analytics:** Prepared the organization for implementing a comprehensive AI and data management strategy; handed over to the newly formed section six months ahead of schedule.
- **Regional Insurer (2024) – Technical Advisor:** Developed the governance framework and implementation plan for centralized architecture management within a SAFe-based delivery model aligned with TOGAF principles.
- **Internal Product Development (2023) – Cyber Security Triage Using AI:** Leading the design, development, and operations of an AI agent for management and transformation consulting.
- **Example Security Venture (2020–2021) – CEO & CTO:** Co-led a cybersecurity joint venture and directed the development and launch of a self-service digital security strategy platform for SMEs.
- **Regional Insurer (2019–2020) – Technical Project Lead:** Managed procurement, integration, and deployment of a cloud-based IoT water leakage detection solution achieving ROI in under six months.
- **Confidential Client (2017–2018) – Head of Architecture and Security:** Line management for a 50-person architecture and cybersecurity organization; established a Central Security Incident Response Team (CSIRT) and strengthened IT security governance.

### Example Financial Services | 2022–2023
**Chief Information and Technology Officer (CITO)**
- Member of the executive management team with full IT budget accountability, leading six direct-report managers across an approximately 40-person development, operations, and data analytics organization.
- Led a major cloud-first transformation programme in Microsoft Azure that consolidated data centers and reduced the overall IT budget by over 30%.
- Directed regulatory compliance under the relevant financial and data-protection authorities.

### Example Insurance Group | 2015–2017
**Nordic CTO – Strategy, Architecture & Information Security**
- Drove the Nordic digital transformation agenda across agile delivery, architecture, and information security, establishing structured IT governance that balanced operational stability with digital innovation.

### Example Bank Group | 2007–2015
**Senior Manager | Interim CIO | Head of IT Controllership**
- Held progressive Nordic and European IT leadership roles, building a new IT control function (SOX, ISO, ISAE 3402), transitioning web/integration delivery to an offshore model, and participating in establishing a shared cloud platform across 12 regulated European entities.

## Earlier Career
- **Example Technology Services:** Business Developer across pre-sales, key account management, and regional technology solutions.
- **Example Software Studio:** Senior Project Manager & Architect designing secure digital services.

## Education & Certifications
- **M.Sc. in Informatics**, Example University (1990–1995)
- **AI Studies**, Example University (2023–2025)
- **Rhetoric – Oral and Written Communication**, Example School & Example University
- **Certifications:** Strategy Tools Global Coaches Certification (2020); former certification: CGEIT (ISACA)
"""


def _generate_fallback_cover_letter_markdown(
    job_info: Dict[str, Any], custom_notes: Optional[str] = None
) -> str:
    """Evidence-grounded fallback cover letter when running in offline/mock test mode."""
    company = job_info.get("company", "Target Company")
    role = job_info.get("role", "Chief Technology Officer")
    lang = job_info.get("language", "en")
    notes_low = (custom_notes or "").lower()
    has_norge = "norgehistoria" in notes_low or "norwegian joke" in notes_low

    if lang == "sv":
        opening_hook = ""
        if has_norge:
            opening_hook = (
                "Det sägs att en norsk bankdirektör tillfrågades om banken nu använde AI för sina kreditbeslut. "
                "\"Ja visst,\" svarade han stolt, \"vi har döpt vår mest erfarna revisor till Anders Ingebretsen – "
                "så nu granskas varje lån av AI!\" På {company} handlar modern AI- och teknikutveckling förstås om "
                "verklig ingenjörskonst snarare än förkortningar, och det är precis därför jag skriver för att anmäla "
                f"mitt intresse för rollen som {role}.\n\n"
            ).format(company=company, role=role)
        return f"""# Personligt brev — {role} på {company}

Till rekryteringsteamet på {company},

{opening_hook}Jag skriver för att anmäla mitt intresse för rollen som {role} på {company}. Med en gedigen bakgrund som CITO, CTO och CIO i reglerade, teknikintensiva verksamheter kombinerar jag exekutivt teknologiledarskap med praktisk erfarenhet av AI-utveckling, arkitekturstyrning och cybersäkerhet.

I min roll som CITO på Example Financial Services ingick jag i koncernledningen med fullt ansvar för IT-budgeten och ledde utvecklings-, drifts- och dataanalysteam i Norden. Där drev jag ett transformationsprogram med moln-först-strategi i Microsoft Azure och konsolidering av datacenter som sänkte IT-budgeten med över 30 %, under dubbel tillsyn av relevanta tillsynsmyndigheter. Genom Example Consulting har jag under de senaste åren kombinerat strategisk rådgivning (bland annat AI- och datastrategi på Transit Agency 2025 som överlämnades sex månader före tidplan samt SAFe/TOGAF-baserad arkitekturstyrning på Regional Insurer 2024) med praktisk utveckling av AI-agenter i Python, PyTorch, OpenAI/Mistral, RAG och LangSmith.

Det som särskilt tilltalar mig med {company} är möjligheten att omsätta modern AI- och plattformsteknologi i pålitliga, affärskritiska lösningar. Jag är en pragmatisk och resultatfokuserad ledare och ingenjör med lågt ego som skapar tydlighet, engagemang och mätbar effekt.

Jag ser fram emot möjligheten att diskutera hur min erfarenhet kan bidra till {company}s fortsatta utveckling.

Med vänliga hälsningar,

**{settings.CANDIDATE_NAME}**
{settings.CANDIDATE_CONTACT_LINE}
"""

    opening_hook_en = ""
    if has_norge:
        opening_hook_en = (
            "There is a classic Nordic story (a Swedish \"Norgehistoria\") about a Norwegian bank manager who was asked "
            "whether his bank had finally adopted AI for its core banking systems. \"Absolutely,\" he replied proudly, "
            "\"we hired a fellow from Bergen named Anders Ingebretsen—so now every transaction is approved by AI!\" "
            f"Since {company} is building real, production-grade AI and mission-critical banking technology rather than relying on acronyms, "
            f"I am delighted to apply for the {role} role.\n\n"
        )

    return f"""# Personal Letter — {role} at {company}

Dear Hiring Team at {company},

{opening_hook_en}I am writing to express my strong interest in the {role} position at {company}. Throughout my career across financial technology, banking, and software engineering—serving both in C-level technology roles (CITO, CTO, CIO) and as a hands-on AI practitioner and architect—I have focused on building resilient, compliant platforms and translating emerging technology into measurable business outcomes.

As CITO at Example Financial Services, I served on the executive management team with full IT budget responsibility, leading development, operations, and data analytics across the Nordics. I spearheaded a cloud-first transformation in Microsoft Azure and data-center consolidation that reduced the IT budget by over 30% while maintaining strict compliance under relevant supervisory authorities supervision. Previously, at Example Insurance Group (Nordic CTO) and Example Bank Group, I built IT governance and control functions (SOX, ISO, ISAE 3402) and helped establish a shared cloud platform across 12 regulated European banking entities.

Alongside my executive leadership, I maintain an active, hands-on engineering practice in generative AI and software development—completing recent university coursework in Modern Generative AI at Example University (2023–2025), building custom models in PyTorch, developing RAG and multi-agent systems with Python, OpenAI, Mistral, LangSmith, and ZEP, and leading the development of an AI agent for cybersecurity triage. In 2025, I also prepared Transit Agency's comprehensive AI and data management strategy, handing it over six months ahead of schedule.

I would welcome the opportunity to discuss how my combination of deep banking/regulated-industry experience, cloud architecture leadership, and hands-on AI engineering can contribute to {company}.

Sincerely,

**{settings.CANDIDATE_NAME}**
{settings.CANDIDATE_CONTACT_LINE}
"""


async def _stream_gemini_markdown(
    system_instruction: str,
    user_prompt: str,
    temperature: float = 0.25,
) -> AsyncGenerator[str, None]:
    """
    Streams markdown text chunks from Google Gemini using streamGenerateContent?alt=sse,
    with fast failover across Gemini models and automatic OpenAI fallback if Gemini quota is exhausted.
    """
    payload = {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    models = [settings.GEMINI_MODEL] + [
        m for m in DEFAULT_GEMINI_FALLBACK_MODELS if m != settings.GEMINI_MODEL
    ]
    timeout = httpx.Timeout(35.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if settings.GEMINI_API_KEY:
            for model_name in models:
                sse_url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model_name}:streamGenerateContent?alt=sse&key={settings.GEMINI_API_KEY}"
                )
                emitted_any = False
                skip_sync_on_model = False
                try:
                    async with client.stream("POST", sse_url, json=payload) as resp:
                        if resp.status_code == 200:
                            async for line in resp.aiter_lines():
                                if not line or not line.startswith("data:"):
                                    continue
                                data_str = line[5:].strip()
                                if not data_str or data_str == "[DONE]":
                                    continue
                                try:
                                    chunk_obj = json.loads(data_str)
                                    candidates = chunk_obj.get("candidates") or []
                                    if not candidates:
                                        continue
                                    parts = candidates[0].get("content", {}).get("parts") or []
                                    for part in parts:
                                        if part.get("thought"):
                                            continue
                                        txt = part.get("text", "")
                                        if txt:
                                            emitted_any = True
                                            yield txt
                                except Exception:
                                    continue
                            if emitted_any:
                                return
                        elif resp.status_code in (429, 404, 400, 403):
                            skip_sync_on_model = True
                except Exception as exc:
                    print(f"Notice: Gemini SSE stream on {model_name} interrupted: {exc}")
                    if emitted_any:
                        return
                    continue

                if skip_sync_on_model:
                    continue

                # Fallback to non-streaming generateContent on the same model if SSE was empty
                sync_url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model_name}:generateContent?key={settings.GEMINI_API_KEY}"
                )
                try:
                    resp = await client.post(sync_url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        parts = data["candidates"][0]["content"].get("parts", [])
                        non_thought = [p.get("text", "") for p in parts if not p.get("thought") and "text" in p]
                        full_text = "\n".join(non_thought) if non_thought else (parts[0].get("text", "") if parts else "")
                        if full_text:
                            for i in range(0, len(full_text), 180):
                                yield full_text[i : i + 180]
                                await asyncio.sleep(0.01)
                            return
                except Exception:
                    continue

        # Automatic OpenAI fallback if Gemini models are quota-exhausted or unavailable
        if settings.OPENAI_API_KEY:
            openai_models = [settings.OPENAI_MODEL or "gpt-4.1-mini"] + [
                m for m in ["gpt-4.1-mini", "gpt-4o-mini", "gpt-4o"] if m != (settings.OPENAI_MODEL or "gpt-4.1-mini")
            ]
            for om in openai_models:
                try:
                    resp = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": om,
                            "messages": [
                                {"role": "system", "content": system_instruction},
                                {"role": "user", "content": user_prompt},
                            ],
                            "temperature": temperature,
                        },
                    )
                    if resp.status_code == 200:
                        full_text = resp.json()["choices"][0]["message"]["content"].strip()
                        if full_text:
                            for i in range(0, len(full_text), 180):
                                yield full_text[i : i + 180]
                                await asyncio.sleep(0.01)
                            return
                except Exception as exc:
                    print(f"Notice: OpenAI markdown fallback on {om} failed: {exc}")
                    continue


def _clean_fenced_markdown(raw_md: str) -> str:
    """Removes outer ```markdown ... ``` wrappers if the LLM included them."""
    text = (raw_md or "").strip()
    text = re.sub(r"^```(?:markdown|md)?\s*\n", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n```\s*$", "", text)
    return text.strip()


async def stream_tailored_cv(
    job_info: Dict[str, Any],
    documents: List[Document],
    custom_notes: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Streams the creation of an optimal, role-tailored CV grounded strictly in the
    candidate's canonical documents and CV Tailoring Rules.
    """
    is_test = (
        settings.ENV.lower() in ("test", "testing")
        or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    )
    if is_test or settings.LLM_PROVIDER.lower() == "mock" or (not settings.GEMINI_API_KEY and not settings.OPENAI_API_KEY):
        fallback_md = _generate_fallback_cv_markdown(job_info)
        lines = fallback_md.splitlines(keepends=True)
        accumulated = ""
        for idx, line in enumerate(lines):
            accumulated += line
            if idx % 4 == 0 or idx == len(lines) - 1:
                section_match = re.findall(r"^##\s+(.+)$", accumulated, flags=re.MULTILINE)
                current_section = section_match[-1] if section_match else "Executive Summary"
                yield {
                    "type": "cv_chunk",
                    "delta": line,
                    "section": current_section,
                    "chars": len(accumulated),
                }
                await asyncio.sleep(0.01)
        yield {"type": "cv_done", "markdown": fallback_md}
        return

    knowledge_context = _build_tailoring_knowledge_context(documents)
    lang_label = "Swedish (Svenska)" if job_info.get("language") == "sv" else "English"
    company = job_info.get("company", "Target Company")
    role = job_info.get("role", "Target Role")
    positioning = job_info.get("positioning_angle", "POS-02")
    role_fit_proposition = job_info.get(
        "role_fit_proposition",
        f"{settings.CANDIDATE_NAME} brings proven C-level technology, architecture, and security leadership directly relevant to {role} at {company}.",
    )
    reqs = "\n".join(f"- {r}" for r in (job_info.get("key_requirements") or []))
    ats_skills = ", ".join(job_info.get("ats_priority_skills") or [])
    objections = "\n".join(f"- {o}" for o in (job_info.get("recruiter_objections_and_mitigation") or []))
    expand_roles = ", ".join(job_info.get("experiences_to_expand") or [])
    compress_roles = ", ".join(job_info.get("experiences_to_compress") or [])
    gaps = "\n".join(f"- {g}" for g in (job_info.get("application_gaps") or [])) or "None"

    system_instruction = f"""Act as an elite CV strategist, executive recruiter, and SAP SuccessFactors / AI-ATS optimization specialist.
Draft a submission-ready, tailored CV for {settings.CANDIDATE_NAME} targeting the {role} vacancy at {company}, using the supplied Canonical Documents as the sole factual source of truth.

=== 1. EVIDENCE & TRUTHFULNESS RULES (NON-NEGOTIABLE) ===
- Treat the Master Evidence Bank and Canonical CV as the strict factual source of truth.
- Distinguish verified facts from positioning language.
- Never invent titles, dates, responsibilities, team sizes, budgets, technologies, clients, suppliers, certifications, or achievements.
- Never convert transferable, adjacent, or uncertain experience into an exact claim.
- Do not infer ownership merely from participation or exposure.
- Do not convert advisory/consulting work into permanent line-management ownership, or acting/interim mandates into permanent formal titles.
- Preserve exact distinctions between direct reports, dotted-line relationships, consultants, suppliers, and wider organizational scope.
- Preserve distinctions between personally delivered results and team or organizational results.
- Never describe expired or former certifications as current (e.g., list CGEIT explicitly as a former certification).
- Respect every confidentiality, anonymization, and public-disclosure restriction.
- If a requirement has no supporting evidence ({gaps}), do not fabricate or imply it.

=== 2. DYNAMIC POSITIONING & RECRUITER OBJECTION MITIGATION ===
- Target Positioning: {positioning}
- Guiding Role-Fit Proposition: {role_fit_proposition}
- Do not force an unrelated career identity onto the application; align depth, tone, and emphasis with the submitted vacancy.
- Proactively address these likely recruiter concerns through factual evidence selection and framing (without defensive explanations):
{objections}

=== 3. SAP SUCCESSFACTORS & AI-ATS OPTIMIZATION ===
- Naturally integrate these evidence-backed priority skills across the Profile, Core Competencies, and Experience bullets, using the employer's terminology where it accurately describes {settings.CANDIDATE_NAME}'s evidence:
  {ats_skills}
- Demonstrate critical skills through concrete experience and outcomes—do not merely list keywords.
- Spell out important abbreviations on first use where helpful for ATS parsing.

=== 4. EXPERIENCE SELECTION, CHRONOLOGY & ACHIEVEMENT-BULLET METHOD ===
- Do not give equal space to every role:
  - Expand roles providing decisive evidence: {expand_roles}
  - Keep older or less central roles concise for chronology: {compress_roles}
- Chronology clarity: Clearly distinguish consulting, interim, and permanent employment using only the dates and relationships in the canonical evidence, so ATS parsers and human reviewers can understand the timeline.
- Where a formal title does not clearly communicate relevant responsibilities, retain the accurate formal title and add a concise functional explanation in parentheses. Never replace the formal title with an invented one.
- Achievement-Bullet Method (for every important bullet):
  1. Begin with an accurate action verb (past tense for completed work, present tense only for active work; no first-person pronouns in bullets).
  2. Establish the problem, mandate, or scope.
  3. State {settings.CANDIDATE_NAME}'s personal responsibility vs. organizational scope.
  4. Demonstrate a relevant skill/competency and include the verified result, scale, or business outcome.
  5. Keep most bullets to 1–2 lines.

=== 5. REQUIRED CV STRUCTURE & MARKDOWN FORMAT ===
Write the entire CV in {lang_label}. Output ONLY the final submission-ready CV in clean Markdown (no ```markdown code fences, no evidence IDs, no drafting notes, no match-status labels, no tables) following this exact structure:

# {settings.CANDIDATE_NAME}
{settings.CANDIDATE_CONTACT_LINE}

## [Target-Role Headline Tailored to {role} — concise, max 10 words, no trailing hyphen]

[Tailored opening profile of 80–120 words communicating professional identity for this vacancy, relevant breadth/level of experience, 2–4 differentiating strengths, relevant industry/domain experience, and concrete business value. Avoid generic clichés.]

## Core Competencies (or ## Kärnkompetenser in Swedish)
- **[Capability Area]:** [Concise, evidence-backed capabilities aligned with the vacancy and SAP/ATS priority skills] (6–8 bullets)

## Professional Experience (or ## Yrkeserfarenhet in Swedish)
Use ### [Employer] | [Dates] and **[Accurate Formal Role Title]** followed by a 1-line scope statement and 3–5 high-impact achievement bullets for expanded roles (and concise 1-line entries under ## Earlier Career / ## Tidigare karriär for compressed roles).

## Education & Certifications (or ## Utbildning & Certifieringar in Swedish)
- M.Sc. in Informatics, Example University (1990–1995)
- AI Studies / Modern Generative AI, Example University (2022–2025)
- Rhetoric – oral and written communication, Example School and Example University
- Former certification: CGEIT – Certified in the Governance of Enterprise IT (ISACA)
- Strategy Tools Global Coaches Certification (2020)

## Languages & Technologies (or ## Språk & Teknologier in Swedish)
- **Languages:** Use only language proficiency explicitly present in the canonical evidence.
- **Technologies:** Python, Java, C#, JavaScript, PyTorch, OpenAI, Mistral, LangSmith, ZEP (RAG), Azure DevOps, GitHub Automation"""

    user_prompt = f"""TARGET APPLICATION:
Company: {company}
Role: {role}
Target Language: {lang_label}
Positioning Angle: {positioning}
One-Sentence Role-Fit Proposition: {role_fit_proposition}
Candidate Notes: {custom_notes or 'None'}

Key Role Requirements & Expected Outcomes:
{reqs}

Priority SAP SuccessFactors / ATS Skills to Demonstrate:
{ats_skills}

Full Job Description:
{job_info.get('clean_job_description', '')}

CANONICAL KNOWLEDGE BASE:
{knowledge_context}
"""

    accumulated = ""
    async for delta in _stream_gemini_markdown(system_instruction, user_prompt, temperature=0.2):
        accumulated += delta
        section_matches = re.findall(r"^##\s+(.+)$", accumulated, flags=re.MULTILINE)
        current_section = section_matches[-1].strip() if section_matches else "Executive Profile"
        yield {
            "type": "cv_chunk",
            "delta": delta,
            "section": current_section,
            "chars": len(accumulated),
        }

    cleaned = _clean_fenced_markdown(accumulated)
    if len(cleaned) < 400:
        cleaned = _generate_fallback_cv_markdown(job_info)
    yield {"type": "cv_done", "markdown": cleaned}


async def stream_tailored_cover_letter(
    job_info: Dict[str, Any],
    cv_markdown: str,
    documents: List[Document],
    custom_notes: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Streams the creation of a tailored, 1-page Personal Letter / Cover Letter
    matching the language and requirements of the target job ad, while honoring custom_notes.
    """
    is_test = (
        settings.ENV.lower() in ("test", "testing")
        or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    )
    if is_test or settings.LLM_PROVIDER.lower() == "mock" or (not settings.GEMINI_API_KEY and not settings.OPENAI_API_KEY):
        fallback_cl = _generate_fallback_cover_letter_markdown(job_info, custom_notes=custom_notes)
        lines = fallback_cl.splitlines(keepends=True)
        accumulated = ""
        for idx, line in enumerate(lines):
            accumulated += line
            if idx % 2 == 0 or idx == len(lines) - 1:
                yield {
                    "type": "cl_chunk",
                    "delta": line,
                    "chars": len(accumulated),
                }
                await asyncio.sleep(0.01)
        yield {"type": "cl_done", "markdown": fallback_cl}
        return

    lang_label = "Swedish (Svenska)" if job_info.get("language") == "sv" else "English"
    company = job_info.get("company", "Target Company")
    role = job_info.get("role", "Target Role")
    role_fit_proposition = job_info.get("role_fit_proposition", "")
    reqs = "\n".join(f"- {r}" for r in (job_info.get("key_requirements") or []))
    objections = "\n".join(f"- {o}" for o in (job_info.get("recruiter_objections_and_mitigation") or []))

    custom_instruction_block = ""
    if custom_notes and custom_notes.strip():
        custom_instruction_block = f"""
=== MANDATORY CANDIDATE CUSTOM INSTRUCTIONS / OPTIONAL FOCUS ===
The candidate explicitly requested the following focus or creative element for this application:
"{custom_notes.strip()}"
You MUST fulfill this instruction directly in the Personal Letter (for example, if the candidate asks to start the letter with a funny Norwegian joke / Swedish "Norgehistoria" relevant to the role, open Paragraph 1 right after the salutation with a short, witty, warm, role-relevant "Norgehistoria" before bridging naturally into the role at {company}) while keeping all factual career claims 100% grounded in the canonical CV.
"""

    system_instruction = f"""You are an executive career strategist drafting a tailored Personal Letter (Cover Letter) for {settings.CANDIDATE_NAME} targeting the {role} role at {company}.
{custom_instruction_block}
Rules:
1. Write in {lang_label} to match the job advertisement (unless custom instructions specify otherwise).
2. Strictly ground every professional experience claim in the provided Tailored CV and Canonical Documents. Never invent employers, dates, metrics, responsibilities, or experiences. Preserve the evidence's distinctions between permanent, interim, and consulting work.
3. Guiding Role-Fit Proposition: {role_fit_proposition}
4. Proactively and naturally address any likely recruiter questions ({objections}) through positive, concrete evidence.
5. Keep it concise, personal, confident, and low-ego (300–450 words, 4 paragraphs):
   - Heading: `# Personal Letter — {role} at {company}` (or `# Personligt brev — {role} på {company}` in Swedish)
   - Salutation: `Dear Hiring Team at {company},` (or `Till rekryteringsteamet på {company},` in Swedish)
   - Paragraph 1: Honor any requested opening hook/anecdote (such as a "Norgehistoria" if requested in Candidate Notes), followed by clear motivation for {role} at {company} and the central value proposition {settings.CANDIDATE_NAME} brings.
   - Paragraph 2: Concrete leadership, engineering, and transformation proof points from the supplied evidence that directly match the core requirements.
   - Paragraph 3: Practical AI & hands-on engineering depth (AI studies at Example University 2023–2025, building custom models in PyTorch, RAG/LangSmith/ZEP, Multi-Agent DevOps, SL AI & data strategy handed over 6 months ahead of schedule, Regional Insurer SAFe/TOGAF architecture governance) and collaborative leadership style.
   - Paragraph 4: Forward-looking closing and sign-off using the configured candidate contact details.
6. Do NOT wrap the output in ```markdown code fences."""

    user_prompt = f"""TARGET ROLE: {role} at {company}
Language: {lang_label}
Mandatory Candidate Notes / Custom Focus: {custom_notes or 'None'}

Key Requirements:
{reqs}

Job Description:
{job_info.get('clean_job_description', '')}

TAILORED CV FOR THIS APPLICATION:
{cv_markdown}
"""

    accumulated = ""
    async for delta in _stream_gemini_markdown(system_instruction, user_prompt, temperature=0.3):
        accumulated += delta
        yield {
            "type": "cl_chunk",
            "delta": delta,
            "chars": len(accumulated),
        }

    cleaned = _clean_fenced_markdown(accumulated)
    if len(cleaned) < 200:
        cleaned = _generate_fallback_cover_letter_markdown(job_info, custom_notes=custom_notes)
        yield {
            "type": "cl_chunk",
            "delta": cleaned,
            "chars": len(cleaned),
        }
    yield {"type": "cl_done", "markdown": cleaned}


def _format_inline_reportlab(text: str) -> str:
    """Converts basic Markdown bold/italic/links into ReportLab XML paragraph tags."""
    escaped = html.escape(text.strip())
    # Convert markdown links [label](url) -> label
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", escaped)
    # Bold **text**
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    # Italic *text*
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", escaped)
    return escaped


def render_markdown_cv_to_pdf_bytes(md_text: str) -> bytes:
    """
    Renders a structured Markdown CV into an executive A4 PDF byte buffer using ReportLab.
    Modeled after the repository's executive typography layout.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=f"{settings.CANDIDATE_NAME} - Executive CV",
        author=settings.CANDIDATE_NAME,
    )

    navy = colors.HexColor("#0F172A")
    accent = colors.HexColor("#1E3A8A")
    slate = colors.HexColor("#334155")
    muted = colors.HexColor("#475569")
    rule_color = colors.HexColor("#CBD5E1")

    base = getSampleStyleSheet()

    name_style = ParagraphStyle(
        "CVName",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=navy,
        spaceAfter=2,
    )
    contact_style = ParagraphStyle(
        "CVContact",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=8.8,
        leading=12,
        textColor=muted,
        spaceAfter=6,
    )
    headline_style = ParagraphStyle(
        "CVHeadline",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=15,
        textColor=accent,
        spaceBefore=2,
        spaceAfter=5,
    )
    section_style = ParagraphStyle(
        "CVSection",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10.2,
        leading=13,
        textColor=accent,
        spaceBefore=8,
        spaceAfter=3,
    )
    company_style = ParagraphStyle(
        "CVCompany",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.8,
        leading=12.5,
        textColor=navy,
        spaceBefore=5,
        spaceAfter=1,
    )
    role_style = ParagraphStyle(
        "CVRole",
        parent=base["Normal"],
        fontName="Helvetica-BoldOblique",
        fontSize=9.0,
        leading=11.5,
        textColor=slate,
        spaceAfter=2,
    )
    body_style = ParagraphStyle(
        "CVBody",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=9.0,
        leading=12.4,
        textColor=navy,
        alignment=TA_LEFT,
        spaceAfter=3.5,
    )
    bullet_style = ParagraphStyle(
        "CVBullet",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=8.8,
        leading=11.8,
        textColor=navy,
        leftIndent=11,
        firstLineIndent=-7,
        spaceAfter=2.0,
    )

    story = []
    lines = (md_text or "").splitlines()
    seen_first_h2 = False
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if not line or line == "---":
            i += 1
            continue

        if line.startswith("# "):
            story.append(Paragraph(_format_inline_reportlab(line[2:]), name_style))
            if i + 1 < len(lines) and not lines[i + 1].strip().startswith("#") and "|" in lines[i + 1]:
                i += 1
                story.append(Paragraph(_format_inline_reportlab(lines[i].strip()), contact_style))
            story.append(HRFlowable(width="100%", thickness=0.8, color=accent, spaceBefore=1, spaceAfter=5))
            i += 1
            continue

        if line.startswith("## "):
            h2_text = line[3:].strip()
            if not seen_first_h2:
                seen_first_h2 = True
                story.append(Paragraph(_format_inline_reportlab(h2_text), headline_style))
            else:
                story.append(Paragraph(_format_inline_reportlab(h2_text.upper()), section_style))
                story.append(HRFlowable(width="100%", thickness=0.5, color=rule_color, spaceBefore=0, spaceAfter=3))
            i += 1
            continue

        if line.startswith("### "):
            comp_text = line[4:].strip()
            block = [Paragraph(_format_inline_reportlab(comp_text), company_style)]
            if i + 1 < len(lines) and lines[i + 1].strip().startswith("**") and lines[i + 1].strip().endswith("**"):
                i += 1
                role_txt = lines[i].strip().strip("*").strip()
                block.append(Paragraph(_format_inline_reportlab(role_txt), role_style))
            story.append(KeepTogether(block))
            i += 1
            continue

        if line.startswith("- ") or line.startswith("* "):
            bullet_txt = _format_inline_reportlab(line[2:])
            story.append(Paragraph(f"&bull; {bullet_txt}", bullet_style))
            i += 1
            continue

        if line.startswith("**") and line.endswith("**") and len(line) < 95:
            role_txt = line.strip("*").strip()
            story.append(Paragraph(_format_inline_reportlab(role_txt), role_style))
            i += 1
            continue

        story.append(Paragraph(_format_inline_reportlab(line), body_style))
        i += 1

    if not story:
        story.append(Paragraph(settings.CANDIDATE_NAME, name_style))

    doc.build(story)
    return buf.getvalue()


def render_markdown_cover_letter_to_pdf_bytes(md_text: str, company: str, role: str) -> bytes:
    """Renders a Markdown Cover Letter / Personal Letter into a clean executive A4 PDF."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"{settings.CANDIDATE_NAME} - Cover Letter ({company})",
        author=settings.CANDIDATE_NAME,
    )

    navy = colors.HexColor("#0F172A")
    accent = colors.HexColor("#1E3A8A")
    muted = colors.HexColor("#475569")

    base = getSampleStyleSheet()
    header_style = ParagraphStyle(
        "CLHeader",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=navy,
        spaceAfter=2,
    )
    sub_style = ParagraphStyle(
        "CLSub",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=muted,
        spaceAfter=8,
    )
    title_style = ParagraphStyle(
        "CLTitle",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=accent,
        spaceBefore=4,
        spaceAfter=10,
    )
    body_style = ParagraphStyle(
        "CLBody",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14.5,
        textColor=navy,
        spaceAfter=8,
    )

    story = [
        Paragraph(html.escape(settings.CANDIDATE_NAME), header_style),
        Paragraph(
            html.escape(settings.CANDIDATE_CONTACT_LINE),
            sub_style,
        ),
        HRFlowable(width="100%", thickness=0.8, color=accent, spaceBefore=2, spaceAfter=10),
    ]

    for raw_line in (md_text or "").splitlines():
        line = raw_line.strip()
        if not line or line == "---":
            continue
        if line.startswith("#"):
            heading_txt = line.lstrip("#").strip()
            story.append(Paragraph(_format_inline_reportlab(heading_txt), title_style))
        elif line.startswith("- ") or line.startswith("* "):
            story.append(Paragraph(f"&bull; {_format_inline_reportlab(line[2:])}", body_style))
        else:
            story.append(Paragraph(_format_inline_reportlab(line), body_style))

    doc.build(story)
    return buf.getvalue()
