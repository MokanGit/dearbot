#!/usr/bin/env python3
"""Synchronize reviewed local Markdown or an optional advanced source into DearBot."""
import sys
import os
import asyncio

# Ensure project root is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from backend.app.database import AsyncSessionLocal, init_db
from backend.app.services.google_drive import GoogleDriveService


async def run_sync():
    print("============================================================")
    print("📂 Synchronizing DearBot Evidence Documents")
    print("============================================================")

    await init_db()
    g = GoogleDriveService()

    client = g._get_drive_client()
    if client:
        print("✓ Advanced Google Drive source is configured")
    else:
        print("✓ Using local Markdown from backend/data/synced_docs")

    async with AsyncSessionLocal() as session:
        result = await g.sync_documents(session)

    print("\n📊 Sync Summary:")
    print(f"  • Total Active Documents: {result.get('total_documents')}")
    print(f"  • Newly Added:           {result.get('added')}")
    print(f"  • Updated (Modified):    {result.get('updated')}")
    print(f"  • Unchanged (Cached):    {result.get('unchanged')}")

    print("\n📑 Current Knowledge Base Documents:")
    for idx, doc in enumerate(result.get("documents", []), start=1):
        print(f"  {idx:2d}. {doc['title']:<45} (file: {doc['filename']}, hash: {doc['content_hash']})")

    print("============================================================")
    print("✅ Local knowledge base successfully synchronized!")
    print("============================================================")


if __name__ == "__main__":
    asyncio.run(run_sync())
