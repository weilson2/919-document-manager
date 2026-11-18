import json

import pytest
from PySide6.QtCore import QObject, QUrl
from PySide6.QtWebEngineCore import QWebEnginePage

from document_manager.editor.bridge import (
    MAX_REQUEST_BYTES,
    EditorBridge,
    EditorSession,
)
from document_manager.editor.web import ENTRY_URL, EditorWebPage, allowed_asset

OPEN = {"method": "open", "protocol_version": 1}
DOCUMENT = {
    "schema_version": 1,
    "document": {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Perjanjian sewa — 麻坡 🌿"}]},
            {"type": "paragraph"},
            {"type": "paragraph", "content": [{"type": "text", "text": "  Lot 12 & 13  "}]},
        ],
    },
}


def verify_request(binding, **changes):
    return {
        "method": "verify_document", "protocol_version": 1,
        "company_id": binding["company_id"], "session_id": binding["session_id"], "document": DOCUMENT,
    } | changes


def test_bridge_exposes_one_slot_and_preserves_document_json():
    parent = QObject()
    bridge = EditorBridge(EditorSession(1), parent)
    meta = bridge.metaObject()
    assert [bytes(meta.method(i).methodSignature()) for i in range(meta.methodOffset(), meta.methodCount())] == [
        b"request(QString)",
    ]
    opened = json.loads(bridge.request(json.dumps(OPEN)))
    assert opened["company_id"] == 1
    assert opened["document"]["document"]["content"] == [{"type": "paragraph"}]
    result = json.loads(bridge.request(json.dumps(verify_request(opened), ensure_ascii=False)))
    assert result == opened | {"document": DOCUMENT}


@pytest.mark.parametrize("payload", [
    "not JSON",
    "[]",
    json.dumps({"method": "shell", "protocol_version": 1}),
    json.dumps(OPEN | {"protocol_version": 2}),
    json.dumps(OPEN | {"protocol_version": True}),
    json.dumps(OPEN | {"company_id": 2}),
    json.dumps(OPEN | {"path": "C:/example.txt"}),
    " " * (MAX_REQUEST_BYTES + 1),
])
def test_bridge_rejects_invalid_requests(payload):
    parent = QObject()
    bridge = EditorBridge(EditorSession(1), parent)
    assert json.loads(bridge.request(payload)) == {"ok": False, "protocol_version": 1, "error": "invalid_request"}


@pytest.mark.parametrize("doc", [
    {"schema_version": 2, "document": DOCUMENT["document"]},
    {"schema_version": True, "document": DOCUMENT["document"]},
    {"schema_version": 1, "document": {"type": "doc", "content": []}},
    {"schema_version": 1, "document": {"type": "doc", "content": [{"type": "paragraph", "content": None}]}},
    {"schema_version": 1, "document": {"type": "doc", "content": [{"type": "image", "attrs": {"src": "file:///C:/private"}}]}},
    {"schema_version": 1, "document": {"type": "doc", "content": [{"type": "paragraph", "attrs": {"onclick": "x"}}]}},
])
def test_invalid_document_schema_is_rejected(doc):
    session = EditorSession(1)
    opened = session.handle(json.dumps(OPEN)).model_dump()
    assert session.handle(json.dumps(verify_request(opened, document=doc))).error == "invalid_request"


def test_bridge_binds_verification_to_open_session_and_company():
    first = EditorSession(1)
    second = EditorSession(2)
    binding = first.handle(json.dumps(OPEN)).model_dump()
    assert second.handle(json.dumps(verify_request(binding))).error == "session_mismatch"
    second_binding = second.handle(json.dumps(OPEN)).model_dump()
    assert binding["session_id"] != second_binding["session_id"]
    assert second.handle(json.dumps(verify_request(second_binding, company_id=1))).error == "session_mismatch"
    assert second.handle(json.dumps(verify_request(second_binding, session_id=binding["session_id"]))).error == "session_mismatch"
    first.close()
    assert first.handle(json.dumps(verify_request(binding))).error == "session_closed"


@pytest.mark.parametrize(("url", "method", "asset"), [
    (ENTRY_URL, b"GET", "index.html"),
    (b"document-manager-editor://app/app.js", b"GET", "app.js"),
    (b"document-manager-editor://app/app.js", b"POST", None),
    (b"document-manager-editor://app/app.js?x=1", b"GET", None),
    (b"document-manager-editor://app/unlisted.js", b"GET", None),
    (b"document-manager-editor://elsewhere/app.js", b"GET", None),
    (b"file:///C:/local.txt", b"GET", None),
    (b"https://outside.invalid/editor", b"GET", None),
])
def test_editor_resource_allowlist(url, method, asset):
    assert allowed_asset(QUrl.fromEncoded(url), method) == asset


def test_navigation_accepts_only_the_main_editor_page():
    mode = QWebEnginePage.NavigationType.NavigationTypeOther
    assert EditorWebPage.acceptNavigationRequest(None, QUrl.fromEncoded(ENTRY_URL), mode, True)
    assert not EditorWebPage.acceptNavigationRequest(None, QUrl.fromEncoded(ENTRY_URL), mode, False)
    assert not EditorWebPage.acceptNavigationRequest(None, QUrl("https://outside.invalid/"), mode, True)
