from types import SimpleNamespace

import asyncio

import pytest

from socials import telegram as tg


@pytest.fixture(autouse=True)
def _force_admin(monkeypatch):
    monkeypatch.setattr(tg, "is_admin", lambda user_id: True)


def _build_message(reply_texts, documents):
    async def fake_reply_text(text):
        reply_texts.append(text)

    async def fake_reply_document(document, filename=None, caption=None):
        documents.append(
            {
                "document": document,
                "filename": filename,
                "caption": caption,
            }
        )

    return SimpleNamespace(
        from_user=SimpleNamespace(id=1),
        reply_text=fake_reply_text,
        reply_document=fake_reply_document,
    )


def test_config_list_filters_section_and_chunks_text(monkeypatch):
    sample_config = {
        "logging": {"log_level": "DEBUG"},
        "social_networks": {f"platform_{i}": bool(i % 2) for i in range(20)},
    }
    monkeypatch.setattr(tg.cfg, "load_config", lambda: sample_config)
    monkeypatch.setattr(tg, "CONFIG_LIST_CHUNK_SIZE", 50)
    monkeypatch.setattr(tg, "CONFIG_LIST_MAX_TEXT_CHUNKS", 50)

    replies: list[str] = []
    documents: list[dict[str, object]] = []
    message = _build_message(replies, documents)
    update = SimpleNamespace(message=message)
    context = SimpleNamespace(args=["social_networks"])

    asyncio.run(tg.config_list(update, context))

    assert not documents
    assert len(replies) >= 2  # small chunk size should split output
    combined = "\n".join(replies)
    assert "social_networks" in combined
    assert "logging" not in combined


def test_config_list_falls_back_to_document_when_too_large(monkeypatch):
    sample_config = {"social_networks": {"telegram": True}}
    monkeypatch.setattr(tg.cfg, "load_config", lambda: sample_config)
    monkeypatch.setattr(tg, "CONFIG_LIST_CHUNK_SIZE", 10)
    monkeypatch.setattr(tg, "CONFIG_LIST_MAX_TEXT_CHUNKS", 1)

    replies: list[str] = []
    documents: list[dict[str, object]] = []
    message = _build_message(replies, documents)
    update = SimpleNamespace(message=message)
    context = SimpleNamespace(args=["social_networks"])

    asyncio.run(tg.config_list(update, context))

    assert not replies
    assert len(documents) == 1
    payload = documents[0]["document"].getvalue()
    assert b"telegram" in payload
    assert documents[0]["filename"] == "social_networks.yaml"
    assert "social_networks" in documents[0]["caption"]


def test_config_list_reports_invalid_path(monkeypatch):
    monkeypatch.setattr(tg.cfg, "load_config", lambda: {"logging": {}})

    replies: list[str] = []
    documents: list[dict[str, object]] = []
    message = _build_message(replies, documents)
    update = SimpleNamespace(message=message)
    context = SimpleNamespace(args=["missing.path"])

    asyncio.run(tg.config_list(update, context))

    assert documents == []
    assert replies == ["Clave invalida: missing.path"]
