"""Bounded UTF-8 JSON input, immutable validation, and graph evidence."""
import hashlib
import json
import math
import time
import uuid
from collections import deque

MAX_BYTES = 25 * 1024 * 1024
MAX_DIMENSION = 250
MAX_SECONDS = 30
CHECK_NAMES = ("reachability", "uniqueness", "routeValidity", "mazeIdentity", "renderedAgreement")


class Rejected(Exception):
    def __init__(self, status, code, location=None):
        self.status, self.code, self.location = status, code, location


def _reject(code, location=None):
    raise Rejected("INVALID_INPUT", code, location)


def _tick(deadline):
    if time.monotonic() > deadline:
        raise Rejected("RESOURCE_LIMIT", "TIME_LIMIT")


def _keys(value, required, optional=()):
    if type(value) is not dict or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        _reject("OBJECT_FIELDS")


def _integer(value):
    return type(value) is int


def _decode(payload):
    if type(payload) not in (bytes, str):
        _reject("JSON_PAYLOAD_REQUIRED")
    if len(payload) > MAX_BYTES:
        raise Rejected("RESOURCE_LIMIT", "BYTE_LIMIT")
    try:
        raw = payload.encode("utf-8") if type(payload) is str else payload
        if len(raw) > MAX_BYTES:
            raise Rejected("RESOURCE_LIMIT", "BYTE_LIMIT")
        if raw.startswith((b"%PDF", b"\x89PNG", b"\xff\xd8")):
            raise Rejected("UNSUPPORTED", "STRUCTURE_JSON_ONLY")
        text = raw.decode("utf-8")

        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    _reject("DUPLICATE_KEY")
                result[key] = value
            return result

        def constant(_):
            _reject("NONFINITE_NUMBER")

        def number(value):
            decoded = float(value)
            if not math.isfinite(decoded):
                _reject("NONFINITE_NUMBER")
            return decoded

        obj = json.loads(text, object_pairs_hook=pairs, parse_constant=constant, parse_float=number)
    except (ValueError, UnicodeError, RecursionError):
        _reject("INVALID_JSON")
    return obj, hashlib.sha256(raw).hexdigest()


def _cell(value, width, height):
    _keys(value, ("row", "col"))
    row, col = value["row"], value["col"]
    if not _integer(row) or not _integer(col) or not (0 <= row < height and 0 <= col < width):
        _reject("CELL_RANGE", value)
    return row * width + col


def _parse(obj):
    _keys(obj, ("schemaVersion", "width", "height", "horizontalWalls", "verticalWalls", "entrance", "exit"), ("route",))
    if obj["schemaVersion"] != "mazeproof.maze/1":
        _reject("SCHEMA_VERSION")
    width, height = obj["width"], obj["height"]
    if not _integer(width) or not _integer(height) or min(width, height) < 1:
        _reject("DIMENSIONS")
    if max(width, height) > MAX_DIMENSION:
        raise Rejected("RESOURCE_LIMIT", "GRID_LIMIT")
    for name, rows, cols in (("horizontalWalls", height + 1, width), ("verticalWalls", height, width + 1)):
        matrix = obj[name]
        if type(matrix) is not list or len(matrix) != rows:
            _reject("WALL_SHAPE", name)
        for index, row in enumerate(matrix):
            if type(row) is not list or len(row) != cols or any(type(v) is not bool for v in row):
                _reject("WALL_SHAPE", {"field": name, "row": index})
    openings = []
    endpoints = []
    for name in ("entrance", "exit"):
        point = obj[name]
        _keys(point, ("row", "col", "side"))
        node = _cell({"row": point["row"], "col": point["col"]}, width, height)
        row, col, side = point["row"], point["col"], point["side"]
        if type(side) is not str or side not in ("N", "E", "S", "W"):
            _reject("ENDPOINT_SIDE", name)
        if side == "N" and row == 0:
            opening = ("horizontalWalls", 0, col)
        elif side == "S" and row == height - 1:
            opening = ("horizontalWalls", height, col)
        elif side == "W" and col == 0:
            opening = ("verticalWalls", row, 0)
        elif side == "E" and col == width - 1:
            opening = ("verticalWalls", row, width)
        else:
            _reject("ENDPOINT_NOT_BOUNDARY", name)
        if obj[opening[0]][opening[1]][opening[2]]:
            _reject("ENDPOINT_CLOSED", name)
        openings.append(opening)
        endpoints.append(node)
    if endpoints[0] == endpoints[1]:
        _reject("IDENTICAL_ENDPOINT_CELLS")
    perimeter = [("horizontalWalls", r, c) for r in (0, height) for c in range(width)]
    perimeter += [("verticalWalls", r, c) for r in range(height) for c in (0, width)]
    for name, row, col in perimeter:
        if not obj[name][row][col] and (name, row, col) not in openings:
            _reject("UNSPECIFIED_OPENING", {"field": name, "row": row, "col": col})
    route = None
    if "route" in obj:
        if type(obj["route"]) is not list:
            _reject("ROUTE_TYPE")
        if len(obj["route"]) > width * height:
            # A simple path cannot exceed the vertex count, but this is a
            # bounded semantic failure (revisits), not a parser limit.
            if len(obj["route"]) > MAX_DIMENSION * MAX_DIMENSION:
                raise Rejected("RESOURCE_LIMIT", "ROUTE_LIMIT")
        route = [_cell(cell, width, height) for cell in obj["route"]]
    return obj, endpoints, route


def _graph(obj, deadline):
    width, height = obj["width"], obj["height"]
    graph = [[] for _ in range(width * height)]
    for row in range(height):
        _tick(deadline)
        for col in range(width):
            node = row * width + col
            if col + 1 < width and not obj["verticalWalls"][row][col + 1]:
                graph[node].append(node + 1)
                graph[node + 1].append(node)
            if row + 1 < height and not obj["horizontalWalls"][row + 1][col]:
                graph[node].append(node + width)
                graph[node + width].append(node)
    return graph


def _path(graph, start, end, deadline, blocked=None):
    parent = {start: None}
    queue = deque([start])
    while queue:
        _tick(deadline)
        node = queue.popleft()
        if node == end:
            route = []
            while node is not None:
                route.append(node)
                node = parent[node]
            return route[::-1], len(parent)
        for neighbor in graph[node]:
            if blocked is not None and {node, neighbor} == set(blocked):
                continue
            if neighbor not in parent:
                parent[neighbor] = node
                queue.append(neighbor)
    return None, len(parent)


def _bridges(graph, deadline):
    """Iterative Tarjan low-link traversal, including disconnected components."""
    discovery, low, bridges = {}, {}, set()
    for root in range(len(graph)):
        if root in discovery:
            continue
        discovery[root] = low[root] = len(discovery)
        stack = [(root, None, iter(graph[root]))]
        while stack:
            _tick(deadline)
            node, parent, neighbors = stack[-1]
            neighbor = next(neighbors, None)
            if neighbor is None:
                stack.pop()
                if parent is not None:
                    low[parent] = min(low[parent], low[node])
                    if low[node] > discovery[parent]:
                        bridges.add(tuple(sorted((node, parent))))
            elif neighbor != parent:
                if neighbor in discovery:
                    low[node] = min(low[node], discovery[neighbor])
                else:
                    discovery[neighbor] = low[neighbor] = len(discovery)
                    stack.append((neighbor, node, iter(graph[neighbor])))
    return bridges


def _route_check(route, graph, endpoints, width):
    if not route:
        return "EMPTY_ROUTE", {"index": 0}
    if route[0] != endpoints[0] or route[-1] != endpoints[1]:
        return "ROUTE_ENDPOINTS", {"index": 0 if route[0] != endpoints[0] else len(route) - 1}
    seen = set()
    for index, node in enumerate(route):
        if node in seen:
            return "ROUTE_REVISIT", {"index": index}
        seen.add(node)
        if index:
            previous = route[index - 1]
            if abs(node // width - previous // width) + abs(node % width - previous % width) != 1:
                return "ROUTE_DISCONTINUOUS", {"index": index}
            if node not in graph[previous]:
                return "ROUTE_WALL_CROSSING", {"index": index}
    return "ROUTE_VALID", None


def _check(status, code, sources, coordinates=None, assurance="exact_structure"):
    return {"status": status, "reasonCode": code, "coordinates": coordinates,
            "sources": sources, "assurance": assurance}


def _base(unique_required):
    return {"schemaVersion": "mazeproof.result/1", "requestId": str(uuid.uuid4()),
            "engineVersion": "0.1.0-local", "inputDigests": {}, "pagePairs": [],
            "policy": {"unique_required": unique_required},
            "limits": {"maxBytes": MAX_BYTES, "maxDimension": MAX_DIMENSION, "maxSeconds": MAX_SECONDS},
            "transforms": [], "recognition": {"status": "NOT_APPLICABLE", "assurance": "exact_structure"},
            "checks": {name: _check("NOT_RUN", "NO_INPUT", []) for name in CHECK_NAMES},
            "overallStatus": "ERROR", "issues": [], "evidence": {},
            "scope": {"checked": [], "notChecked": list(CHECK_NAMES)}}


def validate_structure(problem, solution=None, *, unique_required=True):
    """Validate UTF-8 JSON bytes/text. Optional solution is a complete maze + route.

    No filesystem or network calls. PASS is scoped to supplied exact structure.
    An absent route or comparison is NOT_RUN, never implicitly proven.
    """
    result = _base(unique_required if type(unique_required) is bool else True)
    deadline = time.monotonic() + MAX_SECONDS
    try:
        if type(unique_required) is not bool:
            _reject("POLICY_TYPE")
        obj, digest = _decode(problem)
        result["inputDigests"]["problem"] = digest
        obj, endpoints, route = _parse(obj)
        answer = None
        if solution is not None:
            answer_obj, answer_digest = _decode(solution)
            result["inputDigests"]["solution"] = answer_digest
            answer, _, answer_route = _parse(answer_obj)
            if answer_route is None:
                _reject("SOLUTION_ROUTE_REQUIRED")
            if route is not None:
                _reject("AMBIGUOUS_ROUTE_SOURCE")
        _tick(deadline)
        graph = _graph(obj, deadline)
        start, end = endpoints
        path, _ = _path(graph, start, end, deadline)
        coords = lambda nodes: [{"row": n // obj["width"], "col": n % obj["width"]} for n in nodes]
        checks = result["checks"]
        checks["reachability"] = _check("PASS" if path else "FAIL", "REACHABLE" if path else "UNREACHABLE", ["problem"])
        if path:
            bridges = _bridges(graph, deadline)
            alternative_edge = next(((a, b) for a, b in zip(path, path[1:]) if tuple(sorted((a, b))) not in bridges), None)
            uniqueness = "multiple" if alternative_edge else "unique"
            result["evidence"]["path"] = coords(path)
            if alternative_edge:
                alternative, _ = _path(graph, start, end, deadline, alternative_edge)
                if alternative is None:
                    raise RuntimeError("bridge evidence invariant")
                result["evidence"]["alternativePath"] = coords(alternative)
        else:
            uniqueness = "none"
        result["evidence"]["uniqueness"] = uniqueness
        checks["uniqueness"] = _check("FAIL" if uniqueness != "unique" and unique_required else "PASS", uniqueness.upper(), ["problem"])
        # Full connectivity is a separate diagnostic; BFS must finish, not stop at exit.
        _, visited = _path(graph, start, -1, deadline)
        edge_count = sum(map(len, graph)) // 2
        result["evidence"]["wholeGraphTree"] = visited == len(graph) and edge_count == len(graph) - 1
        if answer is not None:
            differences = []
            for field in ("width", "height", "entrance", "exit"):
                if obj[field] != answer[field]:
                    differences.append({"field": field})
            for field in ("horizontalWalls", "verticalWalls"):
                if (obj["width"], obj["height"]) != (answer["width"], answer["height"]):
                    continue
                for row, (left, right) in enumerate(zip(obj[field], answer[field])):
                    _tick(deadline)
                    for col, (a, b) in enumerate(zip(left, right)):
                        if a != b:
                            differences.append({"field": field, "row": row, "col": col})
            checks["mazeIdentity"] = _check("FAIL" if differences else "PASS", "MAZE_MISMATCH" if differences else "MAZE_IDENTICAL", ["problem", "solution"], differences or None)
            result["evidence"]["mazeDifferences"] = differences
            # Check coordinates against the problem model, never the altered answer.
            if (obj["width"], obj["height"]) == (answer["width"], answer["height"]):
                route = [_cell(cell, obj["width"], obj["height"]) for cell in answer["route"]]
            else:
                route = None
                checks["routeValidity"] = _check("NOT_RUN", "INCOMPATIBLE_DIMENSIONS", ["problem", "solution"])
        else:
            checks["mazeIdentity"] = _check("NOT_RUN", "NO_COMPARISON", [])
        if route is not None:
            code, position = _route_check(route, graph, endpoints, obj["width"])
            if position is not None and route:
                position.update(coords([route[position["index"]]])[0])
            checks["routeValidity"] = _check("PASS" if code == "ROUTE_VALID" else "FAIL", code, ["problem", "solution"] if answer is not None else ["problem"], position)
        elif checks["routeValidity"]["reasonCode"] != "INCOMPATIBLE_DIMENSIONS":
            checks["routeValidity"] = _check("NOT_RUN", "NO_ROUTE", [])
        checks["renderedAgreement"] = _check("NOT_RUN", "NO_RENDERED_ADAPTER", [])
        _tick(deadline)
        result["overallStatus"] = "FAIL" if any(c["status"] == "FAIL" for c in checks.values()) else "PASS"
        for name, check in checks.items():
            if check["status"] == "FAIL":
                result["issues"].append({"check": name, "reasonCode": check["reasonCode"], "coordinates": check["coordinates"]})
    except Rejected as error:
        result["overallStatus"] = error.status
        result["checks"] = {name: _check("NOT_RUN", "INPUT_REJECTED", []) for name in CHECK_NAMES}
        result["evidence"] = {}
        result["issues"] = [{"check": None, "reasonCode": error.code, "coordinates": error.location}]
    except Exception:
        # Fail closed; do not expose input contents, paths, or partial PASS.
        result["overallStatus"] = "ERROR"
        result["checks"] = {name: _check("NOT_RUN", "INTERNAL_ERROR", []) for name in CHECK_NAMES}
        result["evidence"] = {}
        result["issues"] = [{"check": None, "reasonCode": "INTERNAL_ERROR", "coordinates": None}]
    result["scope"] = {"checked": [n for n, c in result["checks"].items() if c["status"] != "NOT_RUN"],
                       "notChecked": [n for n, c in result["checks"].items() if c["status"] == "NOT_RUN"]}
    return result
