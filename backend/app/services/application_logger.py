import os
import re
from datetime import datetime, timezone
from typing import Optional
from backend.app.config import settings


def sanitize_filename(name: str) -> str:
    """Replaces spaces and non-alphanumeric chars with underscores."""
    s = re.sub(r'[^\w\s-]', '', name).strip()
    return re.sub(r'[-\s]+', '_', s)


class ApplicationLoggerService:
    """
    Logs every created job application in the designated applications folder
    following the `_application template`.
    """

    def __init__(self):
        self.output_dir = "backend/data/applications"
        os.makedirs(self.output_dir, exist_ok=True)
        self.template_path = "backend/data/_application_template.md"

    def _get_template_content(self) -> str:
        # 1. Check local synced_docs for any _application_template.md or similar
        synced_dir = settings.LOCAL_SYNC_DIR
        if os.path.exists(synced_dir):
            for f in os.listdir(synced_dir):
                if "_application" in f.lower() and "template" in f.lower() and f.endswith(".md"):
                    with open(os.path.join(synced_dir, f), "r", encoding="utf-8") as tf:
                        return tf.read()

        # 2. Check default template
        if os.path.exists(self.template_path):
            with open(self.template_path, "r", encoding="utf-8") as tf:
                return tf.read()

        # 3. Fallback
        return (
            "# Ansökan: {{COMPANY}} — {{ROLE}}\n\n"
            "- **Datum:** {{DATE}}\n"
            "- **Profil-URL:** {{PROFILE_URL}}\n"
            "- **Token:** `{{TOKEN}}`\n\n"
            "## Kravprofil\n{{JOB_DESCRIPTION}}\n\n"
            "## Anteckningar\n{{NOTES}}\n"
        )

    def log_application(
        self,
        token: str,
        company: str,
        role: str,
        job_description: str,
        notes: Optional[str] = None,
        attached_filename: Optional[str] = None
    ) -> str:
        """
        Creates a markdown record of the application in the application folder.
        Returns the created filepath.
        """
        template = self._get_template_content()
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        profile_url = f"{settings.BASE_URL}/a/{token}"
        cv_source = attached_filename or "Standardiserat genererat CV"

        rendered = template
        rendered = rendered.replace("{{COMPANY}}", company)
        rendered = rendered.replace("{{ROLE}}", role)
        rendered = rendered.replace("{{DATE}}", date_str)
        rendered = rendered.replace("{{PROFILE_URL}}", profile_url)
        rendered = rendered.replace("{{TOKEN}}", token)
        rendered = rendered.replace("{{CV_SOURCE}}", cv_source)
        rendered = rendered.replace("{{JOB_DESCRIPTION}}", job_description.strip())
        rendered = rendered.replace("{{NOTES}}", (notes or "Inga särskilda anteckningar angivna.").strip())

        safe_comp = sanitize_filename(company)
        safe_role = sanitize_filename(role)
        filename = f"{date_str}_{safe_comp}_{safe_role}.md"
        filepath = os.path.join(self.output_dir, filename)

        # Prepend explicit internal and confidential classification header
        header = "# CLASSIFICATION: INTERNAL\n# CONFIDENTIAL - ADMIN ONLY\n\n"
        final_content = header + rendered if not rendered.startswith("# CLASSIFICATION: INTERNAL") else rendered

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(final_content)

        return filepath
