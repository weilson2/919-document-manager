import json
from hashlib import sha256

import pytest
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QImage

from document_manager.editor.bridge import EditorSession, ImageResponse
from document_manager.editor.images import MAX_IMAGE_BYTES, ImportedImage, import_image
from document_manager.editor.web import ORIGIN, EditorImages


def test_managed_image_decodes_jpeg_and_stores_only_normalized_png(tmp_path):
    source = tmp_path / "photo.jpeg"
    raster = QImage(40, 60, QImage.Format.Format_RGB32)
    raster.fill(Qt.GlobalColor.blue)
    assert raster.save(str(source))
    image = import_image(tmp_path, 42, source)
    assert image.asset_id == sha256(image.content).hexdigest()
    assert image.content.startswith(b"\x89PNG\r\n\x1a\n")
    destination = tmp_path / "editor-assets" / "42" / f"{image.asset_id}.png"
    assert destination.read_bytes() == image.content
    assert source.read_bytes().startswith(b"\xff\xd8\xff")


@pytest.mark.parametrize("kind", ["svg", "broken_png", "oversized", "too_wide"])
def test_invalid_local_image_does_not_create_a_managed_file(kind, tmp_path):
    candidate = tmp_path / "bad.png"
    if kind == "too_wide":
        image = QImage(4097, 12, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        assert image.save(str(candidate))
    else:
        contents = {
            "svg": b"<svg/>", "broken_png": b"\x89PNG\r\n\x1a\ncorrupt",
            "oversized": b"\0" * (MAX_IMAGE_BYTES + 1),
        }
        candidate.write_bytes(contents[kind])
    with pytest.raises(ValueError):
        import_image(tmp_path, 1, candidate)
    assert not (tmp_path / "editor-assets").exists()


def test_only_native_picker_can_add_an_image_bound_to_its_session():
    registry = EditorImages()
    opened_picker = []
    image = ImportedImage("1" * 64, b"synthetic test asset")

    def choose_image():
        opened_picker.append(True)
        return image

    session = EditorSession(17, choose_image=choose_image, expose_image=registry.add)
    binding = session.handle('{"method":"open","protocol_version":1,"schema_version":2}')
    envelope = {
        "protocol_version": 1, "company_id": 17, "session_id": binding.session_id,
    }
    document = binding.document.model_dump()
    document["document"] = {"type": "doc", "content": [{"type": "image", "attrs": {"assetId": image.asset_id}}]}
    verify = envelope | {"method": "verify_document", "document": document}
    assert session.handle(json.dumps(verify)).error == "invalid_image"
    request = envelope | {"method": "import_image"}
    assert session.handle(json.dumps(request | {"path": "C:/outside.png"})).error == "invalid_request"
    assert session.handle(json.dumps(request | {"company_id": 99})).error == "session_mismatch"
    assert opened_picker == []

    result = session.handle(json.dumps(request))
    assert isinstance(result, ImageResponse) and result.asset_id == image.asset_id
    assert len(opened_picker) == 1
    assert session.handle(json.dumps(verify)).ok
    image_url = QUrl.fromEncoded(ORIGIN + f"image/{binding.session_id}/{image.asset_id}.png".encode())
    assert registry.get(image_url, b"GET") == image.content
    assert registry.get(image_url, b"POST") is None
    registry.clear()
    session.close()
    assert registry.get(image_url, b"GET") is None
    assert session.handle(json.dumps(verify)).error == "session_closed"


@pytest.mark.parametrize("body", [
    {"type": "paragraph", "attrs": {"lineSpacing": "url(https://outside.invalid)"}},
    {"type": "paragraph", "content": [{"type": "text", "text": "x", "marks": [{"type": "textStyle", "attrs": {"color": "url()"}}]}]},
    {"type": "image", "attrs": {"assetId": "1" * 64, "src": "https://outside.invalid/p.png"}},
    {"type": "table", "content": [{"type": "paragraph"}]},
])
def test_visual_schema_rejects_unsupported_attributes_and_structure(body):
    session = EditorSession(1)
    opened = session.handle('{"method":"open","protocol_version":1,"schema_version":2}')
    assert opened.document.page_settings.page_size == "A4"
    payload = {
        "method": "verify_document", "protocol_version": 1, "company_id": 1, "session_id": opened.session_id,
        "document": opened.document.model_dump() | {"document": {"type": "doc", "content": [body]}},
    }
    assert session.handle(json.dumps(payload)).error == "invalid_request"
