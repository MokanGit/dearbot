import pytest
import json
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.config import settings


@pytest.mark.asyncio
async def test_mcp_protocol():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create an application
        app_res = await client.post("/admin/applications", json={
            "company": "Nordic Fintech",
            "role": "CITO",
            "job_description": "Fintech and regulatory architecture"
        })
        token = app_res.json()["token"]

        # 1. MCP tools/list
        list_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }
        res = await client.post(f"/mcp/{token}", json=list_req)
        assert res.status_code == 200
        tools = res.json()["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        assert "get_profile" in tool_names
        assert "ask_about_candidate" in tool_names
        assert "get_evidence" in tool_names

        # 2. MCP tools/call get_profile
        call_profile = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_profile"}
        }
        res_prof = await client.post(f"/mcp/{token}", json=call_profile)
        assert res_prof.status_code == 200
        prof_data = json.loads(res_prof.json()["result"]["content"][0]["text"])
        assert prof_data["name"] == settings.CANDIDATE_NAME

        # 3. MCP tools/call ask_about_candidate
        call_ask = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "ask_about_candidate",
                "arguments": {"question": "What is his experience in banking and credit?"}
            }
        }
        res_ask = await client.post(f"/mcp/{token}", json=call_ask)
        assert res_ask.status_code == 200
        ask_data = json.loads(res_ask.json()["result"]["content"][0]["text"])
        assert ask_data["confidence"] == "high"
        assert len(ask_data["evidence"]) > 0

        # 4. MCP tools/call get_evidence
        call_ev = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "get_evidence",
                "arguments": {"source_title": "Selected Experience"}
            }
        }
        res_ev = await client.post(f"/mcp/{token}", json=call_ev)
        assert res_ev.status_code == 200
        ev_text = res_ev.json()["result"]["content"][0]["text"]
        assert "Example Systems" in ev_text
