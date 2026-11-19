"""Static source-wiring contract; real broker readback is a separate release gate."""
from pathlib import Path
import ast
import unittest

ROOT=Path(__file__).resolve().parents[1]

class AshenWiring(unittest.TestCase):
    def test_readonly_tool_api_and_broker_actions_exist(self):
        server=ast.parse((ROOT/"server.py").read_text())
        broker=ast.parse((ROOT/"broker.py").read_text())
        tool_names={n.name for n in ast.walk(server) if isinstance(n,ast.FunctionDef)}
        for name in ("ashen_director_project_status","ashen_neural_advice", "ashen_neural_consult", "ashen_neural_sources"):
            self.assertIn(name,tool_names)
        bound={n.value for n in ast.walk(broker) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
        for action in ("ashen_director_project_status","ashen_neural_advice", "ashen_neural_consult", "ashen_neural_sources"):
            self.assertIn(action,bound)

if __name__=="__main__": unittest.main()
