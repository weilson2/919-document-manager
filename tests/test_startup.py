from document_manager.app import main


def test_check_initializes_storage_and_creates_log(tmp_path, capsys):
    data_dir = tmp_path / "workspace % local"
    assert main(["--check", "--data-dir", str(data_dir)]) == 0
    assert (data_dir / "document-manager.sqlite3").is_file()
    assert "Local database ready" in (data_dir / "application.log").read_text(encoding="utf-8")
    assert "Local database ready" in capsys.readouterr().out


def test_check_reports_corrupt_database_and_preserves_file(tmp_path, capsys):
    database = tmp_path / "document-manager.sqlite3"
    original = b"not a database"
    database.write_bytes(original)
    assert main(["--check", "--data-dir", str(tmp_path)]) == 1
    assert "could not open its local workspace" in capsys.readouterr().err
    assert "Application startup failed" in (tmp_path / "application.log").read_text(encoding="utf-8")
    assert database.read_bytes() == original
