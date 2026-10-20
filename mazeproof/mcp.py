"""Read-only stdio MCP; local approved roots, no network or approval tool."""

import argparse
import base64
import json
import os
import stat
import sys
from collections import OrderedDict
from pathlib import Path

from . import core
from .worker import run
from .workspace import Workspace

MAX_LINE = 40 * 1024 * 1024


class RootReader:
    """Open each path component under pre-opened roots, refusing all symlinks.

    dir_fd + O_NOFOLLOW eliminates check/open races on parent components. Roots
    are explicitly selected at startup. This adapter targets POSIX Mac/Linux.
    """

    def __init__(self, roots):
        self.roots = []
        if not roots:
            raise ValueError("at least one allowed root required")
        try:
            for root in roots:
                path = Path(root).resolve(strict=True)
                fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                self.roots.append((path, fd))
                spelling = Path(os.path.abspath(root))
                if spelling != path:
                    self.roots.append((spelling, os.dup(fd)))
        except Exception:
            self.close()
            raise

    def close(self):
        for _, fd in self.roots:
            os.close(fd)
        self.roots = []

    def read(self, value):
        if type(value) is not str or "://" in value or value.startswith(("//", "\\\\")):
            raise core.Rejected("INVALID_INPUT", "LOCAL_FILE_REQUIRED")
        path = Path(value)
        if not path.is_absolute() or ".." in path.parts:
            raise core.Rejected("INVALID_INPUT", "ABSOLUTE_ALLOWED_PATH_REQUIRED")
        for root, root_fd in self.roots:
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            parts = relative.parts
            if not parts:
                break
            fd = os.dup(root_fd)
            try:
                for index, part in enumerate(parts):
                    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                    if index != len(parts) - 1:
                        flags |= os.O_DIRECTORY
                    next_fd = os.open(part, flags, dir_fd=fd)
                    os.close(fd)
                    fd = next_fd
                metadata = os.fstat(fd)
                if not stat.S_ISREG(metadata.st_mode):
                    raise core.Rejected("INVALID_INPUT", "REGULAR_FILE_REQUIRED")
                if metadata.st_size > core.MAX_BYTES:
                    raise core.Rejected("RESOURCE_LIMIT", "BYTE_LIMIT")
                with os.fdopen(fd, "rb") as stream:
                    fd = None
                    data = stream.read(core.MAX_BYTES + 1)
                if len(data) > core.MAX_BYTES:
                    raise core.Rejected("RESOURCE_LIMIT", "BYTE_LIMIT")
                return data
            except OSError:
                raise core.Rejected("INVALID_INPUT", "FILE_ACCESS_REJECTED") from None
            finally:
                if fd is not None:
                    os.close(fd)
        raise core.Rejected("INVALID_INPUT", "OUTSIDE_ALLOWED_ROOT")


def object_schema(properties, required):
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


TOOLS = [
    {
        "name": "validate_structure",
        "description": "Validate exact maze JSON strings. No files are read and no images are proved.",
        "inputSchema": object_schema(
            {
                "problem": {"type": "string"},
                "solution": {"type": "string"},
                "unique_required": {"type": "boolean"},
            },
            ["problem"],
        ),
    },
    {
        "name": "inspect_file",
        "description": "Inspect a PNG/JPEG or explicitly selected PDF page under an allowed root. Returns observations and an unconfirmed result. Cannot approve an image.",
        "inputSchema": object_schema(
            {
                "path": {"type": "string"},
                "page": {"type": "integer", "minimum": 1},
                "geometry": {"type": "object"},
                "rotation": {"enum": [0, 90, 180, 270]},
            },
            ["path"],
        ),
    },
    {
        "name": "validate_pair",
        "description": "Inspect problem/solution image paths independently. Every image result remains NEEDS_REVIEW. PDF page numbers must be explicit.",
        "inputSchema": object_schema(
            {
                "problem": {"type": "string"},
                "solution": {"type": "string"},
                "problem_page": {"type": "integer"},
                "solution_page": {"type": "integer"},
                "unique_required": {"type": "boolean"},
            },
            ["problem", "solution"],
        ),
    },
    {
        "name": "get_result",
        "description": "Read one of the last eight results in this process by request ID.",
        "inputSchema": object_schema({"requestId": {"type": "string"}}, ["requestId"]),
    },
]
for _tool in TOOLS:
    _tool["annotations"] = {
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    }


class MCP:
    def __init__(self, reader):
        self.reader = reader
        self.results = OrderedDict()
        self.initialized = False

    def call(self, name, arguments):
        definition = next((t for t in TOOLS if t["name"] == name), None)
        if definition is None:
            raise core.Rejected("INVALID_INPUT", "UNKNOWN_TOOL")
        schema = definition["inputSchema"]
        core._keys(
            arguments,
            schema["required"],
            tuple(set(schema["properties"]) - set(schema["required"])),
        )
        if (
            "unique_required" in arguments
            and type(arguments["unique_required"]) is not bool
        ):
            raise core.Rejected("INVALID_INPUT", "POLICY_TYPE")
        observations = None
        if name == "get_result":
            if (
                type(arguments["requestId"]) is not str
                or arguments["requestId"] not in self.results
            ):
                raise core.Rejected("INVALID_INPUT", "RESULT_NOT_FOUND")
            return self.results[arguments["requestId"]]
        if name == "validate_structure":
            result = run("structure", arguments)
        else:
            sources = {}
            roles = ("problem",) if name == "inspect_file" else ("problem", "solution")
            for role in roles:
                path = arguments["path" if name == "inspect_file" else role]
                raw = self.reader.read(path)
                item = {"name": Path(path).name, "data": base64.b64encode(raw).decode()}
                page = arguments.get(
                    "page" if name == "inspect_file" else role + "_page"
                )
                if page is not None:
                    item["page"] = page
                if name == "inspect_file":
                    item.update(
                        {
                            k: arguments[k]
                            for k in ("geometry", "rotation")
                            if k in arguments
                        }
                    )
                sources[role] = item
            workspace = Workspace(sources)
            workspace.unique_required = arguments.get("unique_required", True)
            result = workspace.evaluate()
            observations = {
                role: {
                    key: value
                    for key, value in obs.items()
                    if key not in ("image", "name")
                }
                for role, obs in workspace.observations.items()
            }
        response = {"result": result}
        if observations is not None:
            response["observations"] = observations
        self.results[result["requestId"]] = response
        while len(self.results) > 8:
            self.results.popitem(last=False)
        return response

    def handle(self, message):
        if (
            type(message) is not dict
            or message.get("jsonrpc") != "2.0"
            or type(message.get("method")) is not str
        ):
            return {
                "jsonrpc": "2.0",
                "id": message.get("id") if type(message) is dict else None,
                "error": {"code": -32600, "message": "Invalid request"},
            }
        if "id" not in message:
            return None
        request_id = message["id"]
        method, params = message["method"], message.get("params", {})
        envelope = {"jsonrpc": "2.0", "id": request_id}
        try:
            if method == "initialize":
                version = params.get("protocolVersion", "2025-06-18")
                self.initialized = True
                result = {
                    "protocolVersion": version
                    if version in ("2025-06-18", "2024-11-05")
                    else "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "mazeproof", "version": "0.2.0"},
                }
            elif method == "ping":
                result = {}
            elif not self.initialized:
                return {
                    **envelope,
                    "error": {"code": -32002, "message": "Initialize first"},
                }
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                try:
                    response = self.call(params["name"], params.get("arguments", {}))
                    result = {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(response, allow_nan=False),
                            }
                        ],
                        "isError": response["result"]["overallStatus"]
                        in ("ERROR", "INVALID_INPUT", "UNSUPPORTED", "RESOURCE_LIMIT"),
                    }
                except core.Rejected as error:
                    response = {"result": core.error_result(error.status, error.code)}
                    result = {
                        "content": [{"type": "text", "text": json.dumps(response)}],
                        "isError": True,
                    }
            else:
                return {
                    **envelope,
                    "error": {"code": -32601, "message": "Method not found"},
                }
            return {**envelope, "result": result}
        except Exception:
            return {
                **envelope,
                "error": {"code": -32602, "message": "Invalid parameters"},
            }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read-only stdio MCP for explicitly allowed local directories."
    )
    parser.add_argument("--allow-root", action="append", required=True)
    args = parser.parse_args(argv)
    try:
        reader = RootReader(args.allow_root)
    except (OSError, ValueError):
        parser.exit(3, "Allowed roots must be existing local directories.\n")
    server = MCP(reader)
    try:
        while True:
            line = sys.stdin.buffer.readline(MAX_LINE + 1)
            if not line:
                break
            if len(line) > MAX_LINE:
                # Do not continue parsing fragments of an oversized request.
                print(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": None,
                            "error": {"code": -32600, "message": "Request size limit"},
                        }
                    ),
                    flush=True,
                )
                return 3
            try:
                request, _ = core._decode(line)
                reply = server.handle(request)
            except core.Rejected:
                reply = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
            if reply is not None:
                print(json.dumps(reply, allow_nan=False), flush=True)
    finally:
        reader.close()
    return 0
