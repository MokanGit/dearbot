import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.models import Application, ApplicationDocument, Interaction, Document
from backend.app.services.application_logger import sanitize_filename


def _delete_file_safely(file_path: str):
    """Safely removes a file from disk if it exists."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Notice: Could not remove file {file_path}: {e}")


class DataCleanupService:
    """Handles data purging for revoked applications and immediate permanent deletion."""

    @staticmethod
    async def delete_application_files(app: Application, session: AsyncSession):
        """Removes all disk artifacts associated with an application."""
        # 1. Main generated CV PDF
        if app.pdf_path:
            _delete_file_safely(app.pdf_path)

        # 2. Uploaded cover letter
        if app.cover_letter_path:
            _delete_file_safely(app.cover_letter_path)

        # 3. Attached application documents
        stmt_docs = select(ApplicationDocument).where(ApplicationDocument.application_id == app.id)
        docs = (await session.execute(stmt_docs)).scalars().all()
        for doc in docs:
            if doc.file_path:
                _delete_file_safely(doc.file_path)

        # 4. Local application log markdown file
        try:
            app_dir = "backend/data/applications"
            if os.path.exists(app_dir):
                safe_comp = sanitize_filename(app.company)
                safe_role = sanitize_filename(app.role)
                for f in os.listdir(app_dir):
                    if safe_comp in f and safe_role in f and f.endswith(".md"):
                        _delete_file_safely(os.path.join(app_dir, f))
        except Exception as e:
            print(f"Notice: Error cleaning up log files for {app.company}: {e}")

    @classmethod
    async def delete_application_permanently(
        cls,
        app: Application,
        session: AsyncSession
    ) -> Dict[str, Any]:
        """
        Immediately and permanently deletes an application, its files, interactions,
        and supporting documents.
        """
        token = app.token
        company = app.company
        role = app.role

        # Delete physical files
        await cls.delete_application_files(app, session)

        # Delete from DB (cascades to Interaction and ApplicationDocument)
        await session.delete(app)
        await session.commit()

        return {
            "status": "deleted",
            "token": token,
            "company": company,
            "role": role,
            "message": "Application and all associated data permanently deleted."
        }

    @classmethod
    async def cleanup_expired_revoked_applications(
        cls,
        session: AsyncSession,
        retention_days: int = 30
    ) -> Dict[str, Any]:
        """
        Purges all application records and associated files where revoked_at is older
        than retention_days (default 30 days).
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        stmt = select(Application).where(
            Application.revoked_at.is_not(None),
            Application.revoked_at <= cutoff
        )
        expired = (await session.execute(stmt)).scalars().all()

        purged_count = 0
        purged_tokens = []

        for app in expired:
            purged_tokens.append(app.token)
            await cls.delete_application_files(app, session)
            await session.delete(app)
            purged_count += 1

        if purged_count > 0:
            await session.commit()

        return {
            "status": "success",
            "retention_days": retention_days,
            "cutoff": cutoff.isoformat(),
            "purged_count": purged_count,
            "purged_tokens": purged_tokens
        }
