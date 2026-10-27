# Master CV format

Use the master evidence bank as a factual ledger, not as a polished application. DearBot can tailor presentation later; it cannot safely reconstruct facts that were never recorded.

## Evidence rules

- One employment entry represents one contractual relationship or engagement.
- Distinguish permanent, interim, and consulting work explicitly.
- Preserve the source's precision. Do not turn a year into a month, an approximate number into an exact metric, or participation into ownership.
- Attach a source locator to each engagement and project. A filename plus page or section is sufficient.
- Record disagreements between sources under `Unresolved or Conflicting Information` rather than silently choosing one.
- Treat absent facts as unknown. Plausibility is not evidence.

## Internal and public documents

`00_master_evidence_bank.md` must start with `# Classification: internal`. It may contain verified career detail needed for generation but must not contain passwords, identity documents, salary strategy, recruiter notes, health data, or unrelated private material.

Public evidence is a separate, deliberately smaller set of files. Each public file must start with `# Classification: public` and contain only facts the user has approved for recruiter-facing profiles. Suggested files are:

- `01_executive_overview.md`
- `02_selected_experience.md`
- `03_capabilities.md`

The document classifier is fail-closed: unmarked documents remain internal. Never change the master evidence bank to public as a shortcut.

Start public files from `assets/public-evidence-template.md`. Retaining its master-reference and employment fields lets the deterministic validator compare employer, relationship, title, dates, and numeric claims with the internal source of truth.

## Review priorities

Resolve these before generating an application:

1. Employer and client naming.
2. Employment relationship and overlapping dates.
3. Exact titles and whether they were formal, interim, or advisory.
4. Metrics, team sizes, budgets, markets, and regulatory claims.
5. Certifications, degrees, and language proficiency.

The validator checks structure and high-risk factual tokens. It does not prove that prose is true; final publication still requires human approval.
