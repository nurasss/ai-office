import asyncio
from pathlib import Path

from memory.long_term_memory import LongTermMemoryStore
from rag.vector_store import LocalJsonVectorStore


def test_local_json_store_disables_writes_on_read_only_filesystem(monkeypatch, tmp_path):
    def raise_read_only(self, *args, **kwargs):
        raise OSError("read-only filesystem")

    monkeypatch.setattr(Path, "mkdir", raise_read_only)

    store = LocalJsonVectorStore(tmp_path / "data" / "documents.jsonl")

    assert store._writable is False
    assert asyncio.run(store.search("anything")) == []


def test_long_term_memory_disables_itself_on_read_only_filesystem(monkeypatch, tmp_path):
    def raise_read_only(self, *args, **kwargs):
        raise OSError("read-only filesystem")

    monkeypatch.setattr(Path, "mkdir", raise_read_only)

    store = LongTermMemoryStore(tmp_path / "memory")

    assert store.enabled is False
    assert store.search(agent_id="data_analyst", query="sales") == []
