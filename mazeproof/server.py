"""Loopback-only workbench. No file paths, external requests, or disk writes."""

import argparse
import hmac
import json
import math
import secrets
import threading
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import core
from .workspace import Workspace

MAX_BODY = 72 * 1024 * 1024
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/help": ("help.html", "text/html; charset=utf-8"),
    "/help.css": ("help.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address):
        super().__init__(address, Handler)
        self.token = secrets.token_urlsafe(32)
        self.workspaces = OrderedDict()
        self.operation_lock = threading.Lock()

    @property
    def origin(self):
        return "http://127.0.0.1:" + str(self.server_address[1])

    def put(self, workspace):
        key = secrets.token_urlsafe(18)
        self.workspaces[key] = workspace
        while len(self.workspaces) > 4:
            self.workspaces.popitem(last=False)
        return {
            "id": key,
            "sources": workspace.sources,
            **workspace.snapshot(),
            "result": workspace.evaluate(),
        }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *_):
        pass  # filenames, payloads and authentication tokens never enter logs

    def send(self, status, body, mime="application/json; charset=utf-8"):
        data = (
            body
            if isinstance(body, bytes)
            else json.dumps(body, allow_nan=False).encode()
        )
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
        )
        self.end_headers()
        try:
            self.wfile.write(data)
        except (OSError, TimeoutError):
            pass

    def host_ok(self):
        return self.headers.get("Host") == urlsplit(self.server.origin).netloc

    def do_GET(self):
        if not self.host_ok():
            self.send(403, {"error": "HOST_REJECTED"})
            return
        if self.path not in STATIC:
            self.send(404, {"error": "NOT_FOUND"})
            return
        filename, mime = STATIC[self.path]
        self.send(200, (Path(__file__).parent / "web" / filename).read_bytes(), mime)

    def do_POST(self):
        if (
            not self.host_ok()
            or self.headers.get("Origin") != self.server.origin
            or not hmac.compare_digest(
                self.headers.get("Authorization", ""), "Bearer " + self.server.token
            )
        ):
            self.send(403, {"error": "LOCAL_SESSION_REQUIRED"})
            return
        if self.headers.get("Content-Type") != "application/json" or self.headers.get(
            "Transfer-Encoding"
        ):
            self.send(415, {"error": "JSON_REQUIRED"})
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY:
            self.send(413, {"error": "REQUEST_SIZE_LIMIT"})
            return
        if not self.server.operation_lock.acquire(blocking=False):
            self.send(409, {"error": "BUSY"})
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise core.Rejected("INVALID_INPUT", "INCOMPLETE_REQUEST")

            # Larger than the core JSON budget because sources are base64 encoded.
            # Duplicate keys/nonfinite numbers are still rejected.
            def pairs(items):
                obj = {}
                for key, value in items:
                    if key in obj:
                        raise ValueError("duplicate")
                    obj[key] = value
                return obj

            def constant(_):
                raise ValueError("nonfinite")

            def number(value):
                decoded = float(value)
                if not math.isfinite(decoded):
                    raise ValueError("nonfinite")
                return decoded

            body = json.loads(
                raw,
                object_pairs_hook=pairs,
                parse_constant=constant,
                parse_float=number,
            )
            result = self.dispatch(body)
            self.send(200, result)
        except core.Rejected as error:
            self.send(
                400,
                {
                    "error": error.code,
                    "result": core.error_result(error.status, error.code),
                },
            )
        except (ValueError, TypeError, KeyError, RecursionError):
            self.send(
                400,
                {
                    "error": "INVALID_REQUEST",
                    "result": core.error_result("INVALID_INPUT", "INVALID_REQUEST"),
                },
            )
        except Exception:
            self.send(
                500,
                {
                    "error": "LOCAL_OPERATION_FAILED",
                    "result": core.error_result("ERROR", "LOCAL_OPERATION_FAILED"),
                },
            )
        finally:
            self.server.operation_lock.release()

    def dispatch(self, body):
        if self.path == "/api/import":
            core._keys(body, ("sources",), ("reference",))
            return self.server.put(Workspace(body["sources"], body.get("reference")))
        if self.path == "/api/demo":
            core._keys(body, ())
            from .samples import demo_sources

            return self.server.put(Workspace(demo_sources()))
        if self.path == "/api/restore":
            core._keys(body, ("project",))
            return self.server.put(Workspace.restore(body["project"]))
        if self.path == "/api/state":
            core._keys(body, ("id",))
            workspace = self.server.workspaces.get(body["id"])
            if workspace is None:
                raise core.Rejected("INVALID_INPUT", "SESSION_EXPIRED")
            return {
                "id": body["id"],
                **workspace.snapshot(),
                "result": workspace.evaluate(),
            }
        core._keys(body, ("id", "revision"), ("edits", "uniqueRequired"))
        workspace = self.server.workspaces.get(body["id"])
        if workspace is None:
            raise core.Rejected("INVALID_INPUT", "SESSION_EXPIRED")
        if type(body["revision"]) is not int or body["revision"] != workspace.revision:
            raise core.Rejected("INVALID_INPUT", "STALE_REVISION")
        if self.path == "/api/close":
            del self.server.workspaces[body["id"]]
            return {"closed": True}
        if self.path == "/api/revoke":
            workspace.approved_digest = None
            return {"revoked": True}
        if self.path not in ("/api/evaluate", "/api/approve", "/api/export"):
            raise core.Rejected("INVALID_INPUT", "UNKNOWN_OPERATION")
        if "edits" in body:
            workspace.set_edits(body["edits"], body["uniqueRequired"])
        if self.path == "/api/export":
            return {"project": workspace.export(), "revision": workspace.revision}
        result = workspace.evaluate(approve=self.path == "/api/approve")
        return {"id": body["id"], **workspace.snapshot(), "result": result}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run MazeProof on localhost; open the printed private URL."
    )
    parser.add_argument(
        "--port", type=int, default=0, help="Loopback port (0 chooses a free port)"
    )
    args = parser.parse_args(argv)
    try:
        server = LocalServer(("127.0.0.1", args.port))
    except OSError:
        parser.exit(3, "Unable to bind the local port. Choose another --port.\n")
    print("MazeProof: " + server.origin + "/#" + server.token, flush=True)
    print(
        "Local only. Keep this URL private. Ctrl+C to stop and clear the session.",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.workspaces.clear()
        server.server_close()
    return 0
