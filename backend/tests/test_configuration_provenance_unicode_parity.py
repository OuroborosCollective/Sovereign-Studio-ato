from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.configuration.config_canonicalize import canonical_json, hash_value


def test_non_ascii_object_uses_raw_utf8_and_reference_hash() -> None:
    value = {
        "label": "café",
        "emoji": "🛡️",
        "greeting": "Grüße",
        "model": "llama-3",
        "nested": {"title": "Synchronisieren"},
        "arr": ["Wiederherstellung", 1, True, None],
    }
    expected = (
        '{"arr":["Wiederherstellung",1,true,null],"emoji":"🛡️",'
        '"greeting":"Grüße","label":"café","model":"llama-3",'
        '"nested":{"title":"Synchronisieren"}}'
    )
    assert canonical_json(value) == expected
    assert hash_value(value) == "6929ea6b770c93c1f9d34bc0ecac2d6aa6f8373906c2c69ebd4ad953cab1756c"


def test_non_ascii_string_and_key_are_not_ascii_escaped() -> None:
    assert canonical_json("café") == '"café"'
    assert hash_value("café") == "28380feb8724d669bc8d4cf5b5a5bb1adbdc61b81ebd06f3fabc567b4f3b0fc5"
    rendered = canonical_json({"Grüße": "café"})
    assert rendered == '{"Grüße":"café"}'
    assert "\\u" not in rendered
