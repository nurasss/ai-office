from memory import LongTermMemoryStore


def test_memory_limits_prompt_context_and_prunes_agent_file(tmp_path):
    store = LongTermMemoryStore(storage_path=tmp_path)
    store.max_events_per_context = 2
    store.max_events_per_agent = 3

    for index in range(5):
        store.record_incident(
            agent_id="pmo",
            task=f"route lesson task {index}",
            lesson="route lesson should be remembered",
            outcome=f"outcome {index}",
        )

    memory_file = tmp_path / "pmo.jsonl"
    assert len(memory_file.read_text(encoding="utf-8").splitlines()) == 3

    matches = store.search(agent_id="pmo", query="route lesson")
    assert len(matches) == 2
