from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP_SOURCES = (
    ROOT / "backend" / "app.py",
    ROOT / "scripts" / "sovereign-backend" / "app.py",
)


def _load_catalog_runtime(path: Path, rows: list[dict]):
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    selected = [
        node
        for node in module.body
        if (
            isinstance(node, ast.ClassDef)
            and node.name == "_PersistedProviderCatalog"
        )
        or (
            isinstance(node, ast.FunctionDef)
            and node.name == "test_provider_available"
        )
    ]
    assert {node.name for node in selected} == {
        "_PersistedProviderCatalog",
        "test_provider_available",
    }

    queries: list[str] = []
    probes: list[str] = []

    def query(sql: str):
        normalized = " ".join(sql.split())
        queries.append(normalized)
        return [dict(row) for row in rows]

    namespace = {"query": query}
    class_node = next(node for node in selected if isinstance(node, ast.ClassDef))
    exec(compile(ast.Module(body=[class_node], type_ignores=[]), str(path), "exec"), namespace)
    catalog = namespace["_PersistedProviderCatalog"]()
    namespace["PROVIDER_MODELS"] = catalog

    def test_provider_key(provider: str):
        probes.append(provider)
        return True, f"{provider} available", [f"{provider}/live-model"]

    namespace["test_provider_key"] = test_provider_key
    function_node = next(node for node in selected if isinstance(node, ast.FunctionDef))
    exec(compile(ast.Module(body=[function_node], type_ignores=[]), str(path), "exec"), namespace)
    return catalog, namespace["test_provider_available"], queries, probes, source


def _function_ast(path: Path, name: str) -> str:
    module = ast.parse(path.read_text(encoding="utf-8"))
    node = next(
        item for item in module.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.dump(node, include_attributes=False)


def _class_ast(path: Path, name: str) -> str:
    module = ast.parse(path.read_text(encoding="utf-8"))
    node = next(
        item for item in module.body
        if isinstance(item, ast.ClassDef) and item.name == name
    )
    return ast.dump(node, include_attributes=False)


def test_catalog_is_built_only_from_persisted_enabled_gateway_rows():
    rows = [
        {"provider": "OpenAI", "model_id": "openai/gpt-a"},
        {"provider": "openai", "model_id": "openai/gpt-a"},
        {"provider": "openai", "model_id": "openai/gpt-b"},
        {"provider": "anthropic", "model_id": "anthropic/claude-a"},
        {"provider": "", "model_id": "ignored"},
    ]
    for path in APP_SOURCES:
        catalog, _available, queries, _probes, _source = _load_catalog_runtime(path, rows)
        providers = dict(catalog.items())

        assert set(providers) == {"openai", "anthropic"}
        assert providers["openai"] == {
            "name": "openai",
            "models": ["openai/gpt-a", "openai/gpt-b"],
            "default": "openai/gpt-a",
            "format": "{model}",
        }
        assert "openai" in catalog
        assert "gemini" not in catalog
        assert all("lower(provider) <> 'cloudflare'" in sql for sql in queries)


def test_unknown_provider_is_blocked_without_external_probe():
    for path in APP_SOURCES:
        _catalog, available, _queries, probes, _source = _load_catalog_runtime(
            path,
            [{"provider": "openai", "model_id": "openai/gpt-a"}],
        )

        result = available("gemini")

        assert result == (False, "No enabled persisted routes for gemini", [])
        assert probes == []


def test_persisted_provider_uses_real_gateway_probe():
    for path in APP_SOURCES:
        _catalog, available, _queries, probes, _source = _load_catalog_runtime(
            path,
            [{"provider": "OpenAI", "model_id": "openai/gpt-a"}],
        )

        result = available(" OPENAI ")

        assert result == (True, "openai available", ["openai/live-model"])
        assert probes == ["openai"]


def test_gateway_probe_uses_single_provider_path_and_real_response_models():
    for path in APP_SOURCES:
        source = path.read_text(encoding="utf-8")
        assert 'fetch_ai_gateway("/v1/models", provider=provider)' in source
        assert 'fetch_ai_gateway(f"/{provider}/v1/models", provider=provider)' not in source
        assert 'model_info["models"]' not in source
        assert 'str(model.get("id") or model.get("name") or "").strip()' in source
        assert "PROVIDER_MODELS = _PersistedProviderCatalog()" in source


def test_live_and_deploy_gateway_contracts_are_semantically_identical():
    for name in ("test_provider_key", "test_provider_available"):
        assert _function_ast(APP_SOURCES[0], name) == _function_ast(APP_SOURCES[1], name)
    assert _class_ast(APP_SOURCES[0], "_PersistedProviderCatalog") == _class_ast(
        APP_SOURCES[1],
        "_PersistedProviderCatalog",
    )
