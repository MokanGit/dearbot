#!/usr/bin/env python3
"""Validate a DearBot master evidence bank and its approved public subsets."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIRED_HEADINGS = {
    "candidate identity",
    "employment chronology",
    "projects and transformations",
    "education and certifications",
    "skills with supporting engagements",
    "languages",
    "unresolved or conflicting information",
}
REQUIRED_ENGAGEMENT_FIELDS = {"employer", "relationship", "title", "start", "end", "evidence source"}
RELATIONSHIPS = {"permanent", "interim", "consulting"}
PUBLIC_FACT_FIELDS = {"employer", "relationship", "title", "start", "end"}
PLACEHOLDER_RE = re.compile(
    r"\[(?=[^\]\n]*(?:required|optional|explicitly|unknown|source|supported|eng|prj|yyyy|qualification|institution|issuer|language|skill|describe|teams?|budget|metrics?|context|contribution|outcome|name|location|period|year))[^\]\n]+\]",
    re.IGNORECASE,
)
PUBLIC_FILENAME_MARKERS = {
    "01_executive_overview",
    "02_selected_experience",
    "03_ai_and_data_governance",
    "04_cybersecurity_and_grc",
    "executive_overview",
    "public_cv",
}
HIGH_RISK_RE = re.compile(
    r"\b(?:19|20)\d{2}\b|\b\d+(?:[.,]\d+)?\s*(?:%|k|m|million|billion|employees?|people|countries|markets|regions)\b",
    re.IGNORECASE,
)


def issue(issues: list[dict[str, str]], severity: str, code: str, message: str, file: Path) -> None:
    issues.append({"severity": severity, "code": code, "message": message, "file": str(file)})


def headings(text: str) -> set[str]:
    return {
        match.group(1).strip().lower()
        for match in re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE)
    }


def engagement_blocks(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^###\s+(ENG-[A-Z0-9_-]+)\s*$", text, flags=re.MULTILINE | re.IGNORECASE))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((match.group(1).upper(), text[match.end():end]))
    return blocks


def fields(block: str) -> dict[str, str]:
    return {
        match.group(1).strip().lower(): match.group(2).strip()
        for match in re.finditer(r"^-\s+([^:]+):\s*(.*?)\s*$", block, flags=re.MULTILINE)
    }


def field_pairs(text: str) -> list[tuple[str, str]]:
    return [
        (match.group(1).strip().lower(), match.group(2).strip())
        for match in re.finditer(r"^-\s+([^:]+):\s*(.*?)\s*$", text, flags=re.MULTILINE)
    ]


def normalized_features(text: str) -> set[str]:
    return {re.sub(r"\s+", "", value.lower().replace(",", ".")) for value in HIGH_RISK_RE.findall(text)}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def validate_master(master: Path, text: str, issues: list[dict[str, str]]) -> None:
    if "# classification: internal" not in text[:500].lower():
        issue(issues, "error", "master-classification", "Master evidence bank must start with an internal classification.", master)

    missing_headings = sorted(REQUIRED_HEADINGS - headings(text))
    if missing_headings:
        issue(issues, "error", "missing-headings", f"Missing sections: {', '.join(missing_headings)}.", master)

    if PLACEHOLDER_RE.search(text):
        issue(issues, "error", "template-placeholders", "Replace all bracketed template prompts before synchronization.", master)

    blocks = engagement_blocks(text)
    if not blocks:
        issue(issues, "error", "missing-engagements", "Add at least one ENG-* employment entry.", master)

    seen: set[str] = set()
    for engagement_id, block in blocks:
        if engagement_id in seen:
            issue(issues, "error", "duplicate-engagement", f"Duplicate engagement identifier {engagement_id}.", master)
        seen.add(engagement_id)
        values = fields(block)
        missing_fields = sorted(field for field in REQUIRED_ENGAGEMENT_FIELDS if not values.get(field))
        if missing_fields:
            issue(issues, "error", "missing-engagement-fields", f"{engagement_id} is missing: {', '.join(missing_fields)}.", master)
        relationship = values.get("relationship", "").lower()
        if relationship and relationship not in RELATIONSHIPS:
            issue(issues, "error", "invalid-relationship", f"{engagement_id} relationship must be permanent, interim, or consulting.", master)


def validate_public(master_text: str, public_file: Path, issues: list[dict[str, str]]) -> None:
    text = public_file.read_text(encoding="utf-8")
    explicit_public = "# classification: public" in text[:500].lower()
    public_by_name = any(marker in public_file.name.lower() for marker in PUBLIC_FILENAME_MARKERS)
    if not explicit_public and not public_by_name:
        return

    if not explicit_public:
        issue(issues, "error", "implicit-public-classification", "A public filename must also contain an explicit public classification marker.", public_file)

    if PLACEHOLDER_RE.search(text):
        issue(issues, "error", "public-placeholders", "Public evidence contains template placeholders.", public_file)

    normalized_master = normalize_text(master_text)
    for field, value in field_pairs(text):
        if field in PUBLIC_FACT_FIELDS and value and normalize_text(value) not in normalized_master:
            issue(
                issues,
                "error",
                "unsupported-public-field",
                f"Public {field} value is absent from the master evidence bank.",
                public_file,
            )

        if field == "master reference" and value and not re.search(
            rf"^###\s+{re.escape(value)}\s*$",
            master_text,
            flags=re.MULTILINE | re.IGNORECASE,
        ):
            issue(issues, "error", "unknown-master-reference", "Public evidence references an unknown master entry.", public_file)

    unsupported = sorted(normalized_features(text) - normalized_features(master_text))
    if unsupported:
        issue(
            issues,
            "error",
            "unsupported-high-risk-facts",
            "Public evidence contains years or numeric claims absent from the master evidence bank.",
            public_file,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", required=True, type=Path)
    parser.add_argument("--public-dir", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    master = args.master.expanduser().resolve()
    issues: list[dict[str, str]] = []
    if not master.is_file():
        issue(issues, "error", "master-not-found", "Master evidence bank was not found.", master)
        master_text = ""
    else:
        master_text = master.read_text(encoding="utf-8")
        validate_master(master, master_text, issues)

    if args.public_dir:
        public_dir = args.public_dir.expanduser().resolve()
        if not public_dir.is_dir():
            issue(issues, "error", "public-dir-not-found", "Public evidence directory was not found.", public_dir)
        elif master_text:
            for public_file in sorted(public_dir.glob("*.md")):
                if public_file.resolve() != master:
                    validate_public(master_text, public_file, issues)

    result = {
        "valid": not any(item["severity"] == "error" for item in issues),
        "issues": issues,
    }
    if args.as_json:
        print(json.dumps(result, indent=2))
    elif issues:
        for item in issues:
            print(f"[{item['severity'].upper()}] {item['code']}: {item['message']} ({item['file']})")
    else:
        print("Evidence validation passed.")

    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
