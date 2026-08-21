from __future__ import annotations

import argparse
import json
from .core import dispatch_tool

def main() -> None:
    parser = argparse.ArgumentParser(description="Sovereign Universal Toolchain CLI")
    parser.add_argument("tool", help="Tool name, e.g. toolchain_briefing or plan_sandbox_commands")
    parser.add_argument("--args", default="{}", help="JSON object with tool arguments")
    parsed = parser.parse_args()
    args = json.loads(parsed.args)
    result = dispatch_tool(parsed.tool, args)
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
