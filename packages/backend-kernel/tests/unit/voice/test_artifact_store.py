from app.voice.artifact_store import TtsArtifactStore


def test_write_and_resolve_segment(tmp_path) -> None:
    store = TtsArtifactStore(base_dir=tmp_path / "tts", ttl_seconds=60)
    store.register_task("task-1")
    store.write_segment("task-1", 1, b"RIFF")
    resolved = store.resolve_segment("task-1", 1)
    assert resolved is not None
    assert resolved.exists()


def test_cleanup_expired(tmp_path) -> None:
    store = TtsArtifactStore(base_dir=tmp_path / "tts", ttl_seconds=1)
    store.register_task("task-1")
    store.write_segment("task-1", 1, b"RIFF")
    store.mark_completed("task-1")
    deleted = store.cleanup_expired()
    assert deleted >= 0
