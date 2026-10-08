"""Optional QA-only dependency: jsonschema==4.23.0; not imported by product."""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jsonschema import Draft202012Validator
from mazeproof import validate_structure
from test_core import maze

root = Path(__file__).resolve().parents[1]
validators = {}
for name in ("maze", "result"):
    schema = json.loads((root / "schemas" / (name + ".schema.json")).read_text())
    Draft202012Validator.check_schema(schema)
    validators[name] = Draft202012Validator(schema)

obj = maze(2, 2, {(0, 1), (1, 3)}, route=[0, 1, 3])
validators["maze"].validate(obj)
invalid = copy.deepcopy(obj)
invalid["verticalWalls"][0][1] = 0
assert list(validators["maze"].iter_errors(invalid)), "non-boolean wall passed schema"
invalid = copy.deepcopy(obj)
invalid["extra"] = True
assert list(validators["maze"].iter_errors(invalid)), "unknown field passed schema"
for text in (json.dumps(obj), json.dumps(maze(2, 2, set())),
             json.dumps(maze(2, 2, {(0, 1), (1, 3), (0, 2), (2, 3)})),
             '{"x":1,"x":2}', '{"x":1e999}', '{}', '[' * 1100):
    validators["result"].validate(validate_structure(text))
for payload in (b'%PDF-1.7', b'\xff\xd8'):
    validators["result"].validate(validate_structure(payload))
large = copy.deepcopy(obj)
large["width"] = 251
validators["result"].validate(validate_structure(json.dumps(large)))
problem = copy.deepcopy(obj)
del problem["route"]
validators["result"].validate(validate_structure(json.dumps(problem), json.dumps(obj)))
validators["result"].validate(validate_structure(json.dumps(problem), json.dumps(maze(3, 1, {(0, 1), (1, 2)}, route=[0, 1, 2]))))
# Exercise the otherwise unreachable ERROR result through fault injection.
from unittest.mock import patch
from mazeproof import core
with patch.object(core, "_bridges", side_effect=RuntimeError("fault")):
    validators["result"].validate(validate_structure(json.dumps(obj)))
print("Draft 2020-12 schemas and 13 result scenarios: OK")
