from types import MappingProxyType

from flask import Flask, jsonify

from agent_runtime.tools.base import ToolResult


def test_tool_result_thaws_nested_mappingproxy_for_json_response() -> None:
    result = ToolResult(
        metadata=MappingProxyType(
            {
                "mode": "scan",
                "findings": (
                    MappingProxyType(
                        {
                            "severity": "warning",
                            "details": MappingProxyType({"path": "worker.py"}),
                        }
                    ),
                ),
            }
        )
    )

    app = Flask(__name__)
    with app.app_context():
        response = jsonify({"metadata": result.metadata})

    assert response.status_code == 200
    assert response.get_json() == {
        "metadata": {
            "mode": "scan",
            "findings": [
                {
                    "severity": "warning",
                    "details": {"path": "worker.py"},
                }
            ],
        }
    }
