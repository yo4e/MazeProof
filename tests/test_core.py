"""Independent synthetic graphs; no MazeMa data or third-party solver code."""
import copy
import itertools
import json
import unittest
from unittest.mock import patch

from mazeproof import validate_structure
from mazeproof import core


def maze(width, height, edges, start=0, end=None, route=None):
    end = width * height - 1 if end is None else end
    obj = {"schemaVersion": "mazeproof.maze/1", "width": width, "height": height,
           "horizontalWalls": [[True] * width for _ in range(height + 1)],
           "verticalWalls": [[True] * (width + 1) for _ in range(height)]}
    for a, b in edges:
        a, b = sorted((a, b))
        if b - a == 1 and a // width == b // width:
            obj["verticalWalls"][a // width][a % width + 1] = False
        elif b - a == width:
            obj["horizontalWalls"][b // width][a % width] = False
        else:
            raise ValueError("non-grid edge")
    for name, node in (("entrance", start), ("exit", end)):
        row, col = divmod(node, width)
        if row == 0:
            side, field, r, c = "N", "horizontalWalls", 0, col
        elif row == height - 1:
            side, field, r, c = "S", "horizontalWalls", height, col
        elif col == 0:
            side, field, r, c = "W", "verticalWalls", row, 0
        elif col == width - 1:
            side, field, r, c = "E", "verticalWalls", row, width
        else:
            raise ValueError("endpoint must be boundary")
        obj[name] = {"row": row, "col": col, "side": side}
        obj[field][r][c] = False
    if route is not None:
        obj["route"] = [{"row": n // width, "col": n % width} for n in route]
    return obj


def run(obj, answer=None, **policy):
    return validate_structure(json.dumps(obj), json.dumps(answer) if answer is not None else None, **policy)


def oracle_paths(edges, start, end):
    """Tiny independent DFS, operating on edge sets, without production helpers."""
    paths = []

    def walk(node, path):
        if node == end:
            paths.append(path)
            return
        for a, b in edges:
            neighbor = b if a == node else a if b == node else None
            if neighbor is not None and neighbor not in path:
                walk(neighbor, path + [neighbor])
    walk(start, [start])
    return paths


def witness_is_valid(witness, width, edges, start, end):
    nodes = [p["row"] * width + p["col"] for p in witness]
    return (nodes[0] == start and nodes[-1] == end and len(nodes) == len(set(nodes))
            and all(tuple(sorted((a, b))) in edges for a, b in zip(nodes, nodes[1:])))


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.edges = {(0, 1), (1, 3)}
        self.good = maze(2, 2, self.edges, route=[0, 1, 3])

    def test_golden_fixture(self):
        from pathlib import Path
        obj = json.loads(Path("tests/fixtures/unique-2x2.json").read_text())
        result = validate_structure(Path("tests/fixtures/unique-2x2.json").read_bytes())
        normalized = {k: v for k, v in result.items() if k != "requestId"}
        expected = json.loads(Path("tests/fixtures/unique-2x2.result.json").read_text())
        self.assertEqual(normalized, expected)
        self.assertEqual(result["overallStatus"], "PASS")
        self.assertEqual(result["evidence"]["uniqueness"], "unique")
        self.assertFalse(result["evidence"]["wholeGraphTree"])
        self.assertEqual(result["checks"]["routeValidity"]["reasonCode"], "ROUTE_VALID")
        self.assertEqual(result["scope"]["notChecked"], ["mazeIdentity", "renderedAgreement"])

    def test_fault_wall_added_breaks_reachability(self):
        obj = copy.deepcopy(self.good)
        obj["horizontalWalls"][1][1] = True
        result = run(obj)
        self.assertEqual(result["overallStatus"], "FAIL")
        self.assertEqual(result["evidence"]["uniqueness"], "none")
        self.assertEqual(result["checks"]["routeValidity"]["reasonCode"], "ROUTE_WALL_CROSSING")

    def test_fault_wall_removed_adds_alternative(self):
        obj = maze(2, 2, self.edges | {(0, 2), (2, 3)}, route=[0, 1, 3])
        result = run(obj)
        self.assertEqual(result["overallStatus"], "FAIL")
        self.assertEqual(result["evidence"]["uniqueness"], "multiple")
        self.assertNotEqual(result["evidence"]["path"], result["evidence"]["alternativePath"])
        self.assertEqual(run(obj, unique_required=False)["overallStatus"], "PASS")

    def test_route_faults(self):
        for route, code in (([], "EMPTY_ROUTE"), ([0, 3], "ROUTE_DISCONTINUOUS"),
                            ([1, 3], "ROUTE_ENDPOINTS"), ([0, 1], "ROUTE_ENDPOINTS"),
                            ([0, 2, 3], "ROUTE_WALL_CROSSING"),
                            ([0, 1, 0, 1, 3], "ROUTE_REVISIT")):
            with self.subTest(route=route):
                obj = copy.deepcopy(self.good)
                obj["route"] = [{"row": n // 2, "col": n % 2} for n in route]
                check = run(obj)["checks"]["routeValidity"]
                self.assertEqual(check["status"], "FAIL")
                self.assertEqual(check["reasonCode"], code)
                self.assertIn("index", check["coordinates"])

    def test_pair_identity_and_route_against_problem(self):
        problem = copy.deepcopy(self.good)
        del problem["route"]
        self.assertEqual(run(problem, self.good)["overallStatus"], "PASS")
        answer = maze(2, 2, self.edges | {(0, 2), (2, 3)}, route=[0, 2, 3])
        result = run(problem, answer)
        self.assertEqual(result["checks"]["mazeIdentity"]["status"], "FAIL")
        self.assertEqual(result["checks"]["routeValidity"]["reasonCode"], "ROUTE_WALL_CROSSING")
        self.assertEqual(result["evidence"]["mazeDifferences"],
                         [{"field": "horizontalWalls", "row": 1, "col": 0},
                          {"field": "verticalWalls", "row": 1, "col": 1}])
        self.assertEqual(run(self.good, answer)["overallStatus"], "INVALID_INPUT")

    def test_pair_dimension_and_endpoint_mismatch(self):
        problem = copy.deepcopy(self.good)
        del problem["route"]
        answer = maze(3, 1, {(0, 1), (1, 2)}, route=[0, 1, 2])
        result = run(problem, answer)
        self.assertEqual(result["overallStatus"], "FAIL")
        self.assertEqual(result["checks"]["mazeIdentity"]["status"], "FAIL")
        self.assertEqual(result["checks"]["routeValidity"]["reasonCode"], "INCOMPATIBLE_DIMENSIONS")
        answer = copy.deepcopy(self.good)
        answer["horizontalWalls"][0][0] = True
        answer["verticalWalls"][0][0] = False
        answer["entrance"]["side"] = "W"
        result = run(problem, answer)
        self.assertEqual(result["checks"]["mazeIdentity"]["status"], "FAIL")
        self.assertEqual(result["checks"]["routeValidity"]["status"], "PASS")

    def test_rotated_structure_and_wall_addition_properties(self):
        # Coordinate/wall rotation is constructed independently from edge sets.
        edges = {(0, 1), (1, 2), (2, 5), (0, 3), (3, 4)}
        width, height, start, end = 3, 2, 0, 5
        result = run(maze(width, height, edges, start, end))
        rotate = lambda n: (n % width) * height + (height - 1 - n // width)
        rotated_edges = {tuple(sorted((rotate(a), rotate(b)))) for a, b in edges}
        rotated = run(maze(height, width, rotated_edges, rotate(start), rotate(end)))
        self.assertEqual(result["overallStatus"], rotated["overallStatus"])
        self.assertEqual(result["evidence"]["uniqueness"], rotated["evidence"]["uniqueness"])
        disconnected = {(0, 1), (3, 4)}
        for edge in disconnected:
            reduced = run(maze(width, height, disconnected - {edge}, start, end))
            self.assertEqual(reduced["checks"]["reachability"]["status"], "FAIL")

    def test_cycle_off_path_is_unique_not_tree(self):
        edges = {(0, 1), (1, 2), (2, 5), (0, 3), (3, 4), (4, 7), (6, 7), (3, 6)}
        result = run(maze(3, 3, edges, start=0, end=5, route=[0, 1, 2, 5]))
        self.assertEqual(result["overallStatus"], "PASS")
        self.assertFalse(result["evidence"]["wholeGraphTree"])
        self.assertEqual(result["evidence"]["uniqueness"], "unique")

    def test_not_run_and_no_mutation(self):
        obj = copy.deepcopy(self.good)
        del obj["route"]
        original = copy.deepcopy(obj)
        result = run(obj)
        self.assertEqual(result["checks"]["routeValidity"]["status"], "NOT_RUN")
        self.assertEqual(obj, original)
        self.assertEqual(run(obj)["inputDigests"], result["inputDigests"])

    def test_strict_input(self):
        invalid = []
        for field, value in (("width", True), ("width", 0), ("height", 1.0),
                             ("schemaVersion", "other"), ("route", None)):
            obj = copy.deepcopy(self.good)
            obj[field] = value
            invalid.append(obj)
        for change in (lambda o: o.update(unknown=1),
                       lambda o: o["horizontalWalls"][0].append(True),
                       lambda o: o["verticalWalls"][0].__setitem__(1, 0),
                       lambda o: o["horizontalWalls"][2].__setitem__(0, False),
                       lambda o: o["entrance"].__setitem__("side", "S"),
                       lambda o: o["entrance"].__setitem__("side", []),
                       lambda o: o["exit"].update(o["entrance"]),
                       lambda o: o["route"][0].__setitem__("col", -1),
                       lambda o: o["entrance"].__setitem__("row", True)):
            obj = copy.deepcopy(self.good)
            change(obj)
            invalid.append(obj)
        for obj in invalid:
            with self.subTest(obj=obj):
                result = run(obj)
                self.assertEqual(result["overallStatus"], "INVALID_INPUT")
                self.assertTrue(all(c["status"] == "NOT_RUN" for c in result["checks"].values()))
        for payload in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', b'\xff', '[]', '{', '{"x":{"a":1,"a":2}}', '[' * 1100):
            self.assertEqual(validate_structure(payload)["overallStatus"], "INVALID_INPUT")
        self.assertEqual(run(self.good, unique_required=1)["overallStatus"], "INVALID_INPUT")

    def test_limits_and_internal_error_fail_closed(self):
        obj = copy.deepcopy(self.good)
        obj["width"] = 251
        self.assertEqual(run(obj)["overallStatus"], "RESOURCE_LIMIT")
        with patch.object(core, "MAX_BYTES", 10):
            self.assertEqual(run(self.good)["overallStatus"], "RESOURCE_LIMIT")
        with patch.object(core, "MAX_SECONDS", -1):
            result = run(self.good)
            self.assertEqual(result["overallStatus"], "RESOURCE_LIMIT")
            self.assertEqual(result["evidence"], {})
        with patch.object(core, "_bridges", side_effect=RuntimeError("private input")):
            result = run(self.good)
            self.assertEqual(result["overallStatus"], "ERROR")
            self.assertNotIn("private input", json.dumps(result))
            self.assertEqual(result["evidence"], {})
        for payload in (b'%PDF-1.7', b'\x89PNG', b'\xff\xd8'):
            self.assertEqual(validate_structure(payload)["overallStatus"], "UNSUPPORTED")

    def test_large_grid_without_recursion(self):
        width = height = 250
        # Hamiltonian snake across every row: 62,500 vertices.
        path = [r * width + c for r in range(height) for c in (range(width) if r % 2 == 0 else range(width - 1, -1, -1))]
        obj = maze(width, height, set(zip(path, path[1:])), start=path[0], end=path[-1])
        result = run(obj)
        self.assertEqual(result["overallStatus"], "PASS")
        self.assertTrue(result["evidence"]["wholeGraphTree"])

    def test_exhaustive_independent_oracle(self):
        width, height = 3, 2
        possible = [(r * width + c, r * width + c + 1) for r in range(height) for c in range(width - 1)]
        possible += [(c, c + width) for c in range(width)]
        count = 0
        for bits in itertools.product((False, True), repeat=len(possible)):
            edges = {edge for edge, present in zip(possible, bits) if present}
            for start, end in itertools.permutations(range(width * height), 2):
                paths = oracle_paths(edges, start, end)
                expected = "none" if not paths else "unique" if len(paths) == 1 else "multiple"
                result = run(maze(width, height, edges, start, end))
                self.assertEqual(result["evidence"]["uniqueness"], expected, (edges, start, end))
                self.assertEqual(result["overallStatus"], "PASS" if expected == "unique" else "FAIL")
                for key in ("path", "alternativePath"):
                    if key in result["evidence"]:
                        self.assertTrue(witness_is_valid(result["evidence"][key], width, edges, start, end))
                if expected == "multiple":
                    self.assertNotEqual(result["evidence"]["path"], result["evidence"]["alternativePath"])
                count += 1
        self.assertEqual(count, 3840)


if __name__ == "__main__":
    unittest.main()
