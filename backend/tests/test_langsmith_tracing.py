import json
import pytest
from backend.app.models import Application, Document, utc_now
from backend.app.services.ai import (
    serialize_application_context,
    render_qa_messages,
    AnswerSynthesizer,
    MockLLMProvider,
    invoke_mock,
    invoke_gemini,
)


def test_serialize_application_context_is_pure_json():
    """Verify serialize_application_context returns pure JSON serializable dict with no object pointers."""
    app = Application(
        id=123,
        company="LangSmith Testing AB",
        role="Principal AI Architect",
        job_description="Architecting observable and robust LLM tracing systems.",
        notes="Internal private notes that must NOT be exposed."
    )
    doc1 = Document(
        id=1,
        title="AI Experience",
        filename="03_ai_and_data_governance.md",
        content_markdown="# AI Experience\nDesigned enterprise AI systems.",
        classification="public"
    )
    doc2 = Document(
        id=2,
        title="Cybersecurity Overview",
        filename="04_cybersecurity_and_grc.md",
        content_markdown="# Security\nISO 27001 readiness.",
        classification="public"
    )

    question = "What is the candidate's AI and governance experience?"
    
    serialized = serialize_application_context(app, question, [doc1, doc2])

    # 1. Must be directly serializable to JSON without custom encoders
    json_str = json.dumps(serialized)
    assert isinstance(json_str, str)
    
    # 2. Must not contain Python memory address representations
    assert "object at 0x" not in json_str
    assert "Application" not in json_str
    assert "Document" not in json_str

    # 3. Verify exact keys and structure
    assert serialized["company"] == "LangSmith Testing AB"
    assert serialized["role"] == "Principal AI Architect"
    assert serialized["job_description"] == "Architecting observable and robust LLM tracing systems."
    assert serialized["question"] == question
    assert len(serialized["documents"]) == 2
    assert serialized["documents"][0]["title"] == "AI Experience"
    assert serialized["documents"][0]["filename"] == "03_ai_and_data_governance.md"


def test_render_qa_messages_structure():
    """Verify render_qa_messages formats standard system and user messages correctly."""
    template_variables = {
        "company": "Nordic Bank",
        "role": "Chief Information Officer",
        "job_description": "Banking regulations and DORA compliance.",
        "question": "How do you handle regulatory resilience?",
        "documents": [
            {
                "id": "1",
                "title": "Example Financial Services — CITO",
                "filename": "02_selected_experience.md",
                "content_markdown": "Led DORA compliance and ISO 27001 readiness."
            }
        ]
    }

    messages = render_qa_messages(template_variables)
    
    assert isinstance(messages, list)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"

    # Verify JSON serializability of messages
    json_messages = json.dumps(messages)
    assert isinstance(json_messages, str)

    # Check content contains template variable inputs
    assert "Nordic Bank" in messages[0]["content"]
    assert "Chief Information Officer" in messages[0]["content"]
    assert "How do you handle regulatory resilience?" in messages[1]["content"]
    assert "Example Financial Services — CITO" in messages[1]["content"]


@pytest.mark.asyncio
async def test_invoke_mock_traced_model_call():
    """Verify invoke_mock executes successfully given serialized messages and template variables."""
    template_variables = {
        "company": "CloudCorp",
        "role": "Head of Engineering",
        "job_description": "Cloud security and resilience.",
        "question": "What cybersecurity experience do you have?",
        "documents": [
            {
                "id": "1",
                "title": "Cybersecurity & GRC",
                "filename": "04_cybersecurity.md",
                "content_markdown": "Formulated zero-trust cybersecurity posture and ISO 27001 readiness."
            }
        ]
    }
    messages = render_qa_messages(template_variables)

    result = await invoke_mock(
        messages=messages,
        template_variables=template_variables,
        model="Mock AI Engine (Offline / Test)"
    )

    assert isinstance(result, dict)
    assert "answer" in result
    assert "security" in result["answer"].lower()
    assert result.get("confidence") == "high"
    assert len(result.get("evidence", [])) > 0


@pytest.mark.asyncio
async def test_answer_synthesizer_streaming_with_serialization():
    """Verify AnswerSynthesizer.stream_answer processes serialized inputs cleanly."""
    synth = AnswerSynthesizer()
    app = Application(
        company="StreamCorp",
        role="CTO",
        job_description="AI strategy and cloud architecture.",
        notes="Private note"
    )
    doc = Document(
        title="AI Governance",
        filename="03_ai.md",
        content_markdown="Formulated AI governance frameworks compliant with EU AI Act.",
        classification="public"
    )

    tokens = []
    metadata = None
    async for chunk in synth.stream_answer("What AI experience do you have?", app, [doc]):
        if chunk["type"] == "token":
            tokens.append(chunk["content"])
        elif chunk["type"] == "metadata":
            metadata = chunk

    assert len(tokens) > 0
    full_answer = "".join(tokens)
    assert "evidence-linked assistant" in full_answer
    assert metadata is not None
    assert metadata["status"] == "ok"
    assert metadata["confidence"] == "high"


@pytest.mark.asyncio
async def test_invoke_gemini_fast_failover_on_timeout(monkeypatch):
    """Verify invoke_gemini does not retry a timed-out model and fails over immediately."""
    import httpx
    from backend.app.services import ai as ai_module

    called_models = []

    async def fake_invoke_gemini_model(client, model_name, attempt, url, payload):
        called_models.append((model_name, attempt))
        if model_name == "gemini-3.7-flash":
            raise httpx.ReadTimeout("Simulated model read timeout")
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"thought": True, "text": "internal reasoning"},
                                {"text": "Grounded answer from fallback model."},
                            ]
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(ai_module, "_invoke_gemini_model", fake_invoke_gemini_model)

    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}]
    result = await invoke_gemini(
        messages=messages,
        template_variables={"question": "test"},
        model="gemini-3.7-flash",
        api_key="test-key",
        fallback_models=["gemini-3.7-flash", "gemini-3.6-flash"],
        request_timeout=1.0,
    )

    # Must only call gemini-3.7-flash once (attempt 0) before failing over to gemini-3.6-flash
    assert called_models == [("gemini-3.7-flash", 0), ("gemini-3.6-flash", 0)]
    assert result["answer"] == "Grounded answer from fallback model."
    assert result["model_name"] == "Google Gemini 3.6 Flash"

