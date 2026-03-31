from app.plugins.infrastructure.metadata_repository import PluginMetadataRepository


def test_metadata_repository_returns_empty_when_file_is_invalid_json(tmp_path) -> None:
    metadata_file = tmp_path / "plugin_metadata.json"
    metadata_file.write_text("{invalid-json", encoding="utf-8")

    repository = PluginMetadataRepository(metadata_file)

    assert repository.all() == {}


def test_metadata_repository_swallow_write_errors_and_keep_memory_state(tmp_path, monkeypatch) -> None:
    metadata_file = tmp_path / "plugin_metadata.json"
    repository = PluginMetadataRepository(metadata_file)

    def _raise_write_error(self, *args, **kwargs):
        del self, args, kwargs
        raise OSError("disk full")

    monkeypatch.setattr(type(repository._metadata_file), "write_text", _raise_write_error)

    repository.upsert("com.demo", {"source_type": "user_created"})
    repository.update_publish("com.demo", {"last_version": "1.0.0"})
    repository.update_mobile_publish("com.demo", {"last_version": "1.0.0"})

    assert repository.all()["com.demo"]["source_type"] == "user_created"
    assert repository.get_publish("com.demo")["last_version"] == "1.0.0"
    assert repository.get_mobile_publish("com.demo")["last_version"] == "1.0.0"
