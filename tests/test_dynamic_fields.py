import json

import pytest

from document_manager.editor.bridge import EditorSession
from document_manager.editor.fields import FieldDefinition
from document_manager.editor.visual_schema import FieldDocument, PageSettings

IDENTIFIER = "a1" * 16
FIELD = {
    "id": IDENTIFIER, "key": "tenant_name", "type": "text", "label": "承租人 · Tenant",
    "required": True, "default": None, "validation": {}, "formatting": {},
}


def document():
    return {
        "schema_version": 3,
        "page_settings": PageSettings().model_dump(),
        "fields": [FIELD],
        "document": {"type": "doc", "content": [{"type": "paragraph", "content": [
            {"type": "field", "attrs": {"fieldId": IDENTIFIER}},
            {"type": "text", "text": " / "},
            {"type": "field", "attrs": {"fieldId": IDENTIFIER}},
        ]}]},
    }


@pytest.mark.parametrize(("kind", "value", "rules", "formatting"), [
    ("text", "名称", {"min_length": 1}, {"style": "upper"}),
    ("multiline", "one\ntwo", {"max_length": 30}, {}),
    ("number", "-123.123456", {"min": "-124"}, {"decimals": 4}),
    ("currency", "123.45", {"max": "123.45"}, {"style": "symbol"}),
    ("date", "2028-02-29", {}, {"style": "dmy"}),
    ("date_range", {"start": "2026-11-01", "end": "2026-11-02"}, {}, {}),
    ("dropdown", "A", {"options": ["A", "B"]}, {}),
    ("checkbox", False, {}, {}),
    ("boolean", True, {}, {"style": "yes_no"}),
    ("phone", "+60 (12) 300-0000", {}, {}),
    ("email", "tenant@example.com", {}, {}),
    ("address", "Lot 4\nKuala Lumpur", {}, {}),
])
def test_all_field_types_validate_and_serialize(kind, value, rules, formatting):
    data = FIELD | {"type": kind, "default": value, "validation": rules, "formatting": formatting}
    assert FieldDefinition.model_validate(data).model_dump(exclude_unset=True) == data


@pytest.mark.parametrize("change", [
    {"type": "invented"},
    {"type": "currency", "default": "0.001"},
    {"type": "currency", "default": 0.01},
    {"type": "date", "default": "2026-2-03"},
    {"type": "date", "default": "2026-02-30"},
    {"type": "date_range", "default": {"start": "2026-11-02", "end": "2026-11-01"}},
    {"type": "email", "default": "tenant@"},
    {"type": "phone", "default": "oops"},
    {"type": "boolean", "default": "true"},
    {"type": "dropdown", "validation": {"options": ["yes", "no"]}, "default": "other"},
    {"validation": {"min": "0"}},
    {"validation": {"unknown_rule": "literal"}},
    {"formatting": {"style": "unknown"}},
])
def test_bridge_rejects_invalid_field_configuration(change):
    session = EditorSession(1)
    opened = session.handle('{"protocol_version":1,"method":"open","schema_version":3}')
    payload = document() | {"fields": [FIELD | change]}
    assert verify(session, opened, payload).error == "invalid_request"


def verify(session, binding, payload):
    return session.handle(json.dumps({
        "protocol_version": 1, "method": "verify_document", "company_id": binding.company_id,
        "session_id": binding.session_id, "document": payload,
    }))


def test_references_rename_compatibility_and_company_session():
    first = EditorSession(1)
    second = EditorSession(2)
    request = '{"protocol_version":1,"method":"open","schema_version":3}'
    binding = first.handle(request)
    assert second.handle(request).document.fields == []
    assert verify(second, binding, document()).error == "session_mismatch"
    data = document() | {"fields": [FIELD | {"key": "new_key", "label": "姓名"}]}
    response = verify(first, binding, data)
    assert isinstance(response.document, FieldDocument)
    assert json.loads(response.model_dump_json(exclude_unset=True))["document"] == data
    assert verify(first, binding, data | {"fields": []}).error == "invalid_request"
    assert verify(first, binding, data | {"fields": [FIELD, FIELD | {"id": "a2" * 16}]}).error == "invalid_request"
    assert verify(first, binding, data | {"schema_version": "3"}).error == "invalid_request"
    assert verify(first, binding, data | {"schema_version": 4}).error == "invalid_request"
    version_two = EditorSession(1)
    older_binding = version_two.handle('{"protocol_version":1,"method":"open","schema_version":2}')
    legacy = data | {"schema_version": 2}
    del legacy["fields"]
    assert verify(version_two, older_binding, legacy).error == "invalid_request"
    assert verify(version_two, older_binding, older_binding.document.model_dump(exclude_unset=True)).ok
