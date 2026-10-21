"""Loopback-only workbench. No file paths, external requests, or disk writes."""

import argparse
import hmac
import json
import math
import re
import secrets
import threading
import time
import webbrowser
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import core
from .workspace import MAX_PROJECT_REQUEST_BYTES, Workspace, canonical

MAX_BODY = 72 * 1024 * 1024
MAX_WORKSPACES = 128
MAX_STORED_BYTES = 192 * 1024 * 1024
IMPORT_LEASE_SECONDS = 60
IMPORT_RECORD_SECONDS = 120
MAX_IMPORT_RECORDS = 512
IMPORT_PATHS = {"/api/import", "/api/demo", "/api/restore", "/api/batch-item"}
IMPORT_CONTROLS = {"/api/import-claim", "/api/import-cancel"}
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/batch": ("index.html", "text/html; charset=utf-8"),
    "/help": ("help.html", "text/html; charset=utf-8"),
    "/help.css": ("help.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/batch.js": ("batch.js", "text/javascript; charset=utf-8"),
    "/files.js": ("files.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address):
        super().__init__(address, Handler)
        self.token = secrets.token_urlsafe(32)
        self.workspaces = OrderedDict()
        self.storage_costs = {}
        self.operation_lock = threading.Lock()
        self.import_lock = threading.Lock()
        self.imports = {}

    @property
    def origin(self):
        return "http://127.0.0.1:" + str(self.server_address[1])

    def _prune_imports(self):
        now = time.monotonic()
        for request_id, record in list(self.imports.items()):
            if record["expires"] <= now:
                # Only unclaimed results expire. Claimed work remains intact.
                del self.imports[request_id]

    def service_actions(self):
        with self.import_lock:
            self._prune_imports()

    @staticmethod
    def check_request_id(request_id):
        if not isinstance(request_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{16,80}", request_id
        ):
            raise core.Rejected("INVALID_INPUT", "IMPORT_REQUEST_ID")

    def begin_import(self, request_id):
        self.check_request_id(request_id)
        with self.import_lock:
            self._prune_imports()
            existing = self.imports.get(request_id)
            if existing:
                raise core.Rejected(
                    "INVALID_INPUT",
                    "IMPORT_CANCELLED"
                    if existing["state"] == "cancelled"
                    else "DUPLICATE_IMPORT",
                )
            if len(self.imports) >= MAX_IMPORT_RECORDS:
                raise core.Rejected("RESOURCE_LIMIT", "IMPORT_REQUEST_LIMIT")
            self.imports[request_id] = {"state": "reading", "expires": math.inf}

    def finish_import(self, request_id):
        with self.import_lock:
            record = self.imports.get(request_id)
            if record and record["state"] == "reading":
                self.imports[request_id] = {
                    "state": "cancelled",
                    "expires": time.monotonic() + IMPORT_RECORD_SECONDS,
                }

    def cancel_import(self, request_id):
        self.check_request_id(request_id)
        with self.import_lock:
            self._prune_imports()
            record = self.imports.get(request_id)
            if record and record["state"] == "claimed":
                self.workspaces.pop(record["id"], None)
                self.storage_costs.pop(record["id"], None)
            if record is None and len(self.imports) >= MAX_IMPORT_RECORDS:
                raise core.Rejected("RESOURCE_LIMIT", "IMPORT_REQUEST_LIMIT")
            # A tombstone also handles cancellation arriving before the import.
            self.imports[request_id] = {
                "state": "cancelled",
                "expires": time.monotonic() + IMPORT_RECORD_SECONDS,
            }
        return {"cancelled": True}

    def claim_import(self, request_id, key):
        self.check_request_id(request_id)
        with self.import_lock:
            self._prune_imports()
            record = self.imports.get(request_id)
            if (
                not record
                or record["state"] not in ("pending", "claimed")
                or record["id"] != key
            ):
                raise core.Rejected("INVALID_INPUT", "IMPORT_EXPIRED")
            if record["state"] == "pending":
                self.workspaces[key] = record["workspace"]
                self.storage_costs[key] = record["cost"]
                self.imports[request_id] = {
                    "state": "claimed",
                    "id": key,
                    # Keep cancellation possible if the claim response itself
                    # is lost. Closing the owned workspace releases this record.
                    "expires": math.inf,
                }
        return {"claimed": True}

    def close_workspace(self, key):
        with self.import_lock:
            self.workspaces.pop(key, None)
            self.storage_costs.pop(key, None)
            for request_id, record in list(self.imports.items()):
                if record["state"] == "claimed" and record["id"] == key:
                    del self.imports[request_id]

    def put(self, workspace, request_id=None):
        # Never evict another maze's edits/approval to make room for a batch.
        # Reserve for growth of routes and resolved-boundary lists as well as
        # the serialized sources/observations. This is a storage budget, not an
        # OS-enforced process RSS limit.
        cost = len(
            canonical({"sources": workspace.sources, **workspace.snapshot()}).encode()
        ) + 128 * sum(
            obs["model"]["width"] * obs["model"]["height"]
            for obs in workspace.observations.values()
        )
        key = secrets.token_urlsafe(18)
        result = {
            "id": key,
            "sources": workspace.sources,
            **workspace.snapshot(),
            "result": workspace.evaluate(),
        }
        with self.import_lock:
            self._prune_imports()
            record = self.imports.get(request_id)
            if request_id is not None and (not record or record["state"] != "reading"):
                raise core.Rejected("INVALID_INPUT", "IMPORT_CANCELLED")
            pending = [r for r in self.imports.values() if r["state"] == "pending"]
            if (
                len(self.workspaces) + len(pending) >= MAX_WORKSPACES
                or sum(self.storage_costs.values())
                + sum(r["cost"] for r in pending)
                + cost
                > MAX_STORED_BYTES
            ):
                raise core.Rejected("RESOURCE_LIMIT", "WORKSPACE_LIMIT")
            if request_id is None:
                self.workspaces[key] = workspace
                self.storage_costs[key] = cost
            else:
                self.imports[request_id] = {
                    "state": "pending",
                    "id": key,
                    "workspace": workspace,
                    "cost": cost,
                    "expires": time.monotonic() + IMPORT_LEASE_SECONDS,
                }
        return result


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
        try:
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
            self.wfile.write(data)
        except (OSError, TimeoutError):
            return False
        return True

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
        control = self.path in IMPORT_CONTROLS
        limit = MAX_BODY
        if control:
            limit = 1024
        elif self.path in ("/api/restore", "/api/batch-item"):
            limit = MAX_PROJECT_REQUEST_BYTES
        if not 0 <= length <= limit:
            self.send(413, {"error": "REQUEST_SIZE_LIMIT"})
            return
        # Cancellation/receipt are bounded metadata operations. They must remain
        # available while the image worker owns the expensive-operation lock.
        if not control and not self.server.operation_lock.acquire(blocking=False):
            self.send(409, {"error": "BUSY"})
            return
        self.import_request_id = None
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
            if self.path in IMPORT_PATHS:
                request_id = self.headers.get("X-MazeProof-Import")
                self.server.begin_import(request_id)
                self.import_request_id = request_id
            result = self.dispatch(body)
            if not self.send(200, result) and self.import_request_id:
                self.server.cancel_import(self.import_request_id)
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
            if self.import_request_id:
                self.server.finish_import(self.import_request_id)
            if not control:
                self.server.operation_lock.release()

    def dispatch(self, body):
        if self.path == "/api/import-cancel":
            core._keys(body, ("requestId",))
            return self.server.cancel_import(body["requestId"])
        if self.path == "/api/import-claim":
            core._keys(body, ("requestId", "id"))
            return self.server.claim_import(body["requestId"], body["id"])
        if self.path == "/api/batch-item":
            from .batch import inspect_item

            return self.server.put(inspect_item(body), self.import_request_id)
        if self.path == "/api/import":
            core._keys(body, ("sources",), ("reference",))
            return self.server.put(
                Workspace(body["sources"], body.get("reference")),
                self.import_request_id,
            )
        if self.path == "/api/demo":
            core._keys(body, ())
            from .samples import demo_sources

            return self.server.put(Workspace(demo_sources()), self.import_request_id)
        if self.path == "/api/restore":
            core._keys(body, ("project",))
            return self.server.put(
                Workspace.restore(body["project"]), self.import_request_id
            )
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
        core._keys(
            body, ("id", "revision"), ("edits", "uniqueRequired", "revokeApproval")
        )
        workspace = self.server.workspaces.get(body["id"])
        if workspace is None:
            raise core.Rejected("INVALID_INPUT", "SESSION_EXPIRED")
        if type(body["revision"]) is not int or body["revision"] != workspace.revision:
            raise core.Rejected("INVALID_INPUT", "STALE_REVISION")
        if self.path == "/api/close":
            self.server.close_workspace(body["id"])
            return {"closed": True}
        if self.path == "/api/revoke":
            workspace.approved_digest = None
            return {"revoked": True}
        if self.path not in ("/api/evaluate", "/api/approve", "/api/export"):
            raise core.Rejected("INVALID_INPUT", "UNKNOWN_OPERATION")
        if "edits" in body:
            workspace.set_edits(
                body["edits"],
                body["uniqueRequired"],
                revoke_approval=body.get("revokeApproval", False),
            )
        elif "revokeApproval" in body:
            raise core.Rejected("INVALID_INPUT", "EDITS_REQUIRED")
        if self.path == "/api/export":
            return {"project": workspace.export(), "revision": workspace.revision}
        result = workspace.evaluate(approve=self.path == "/api/approve")
        return {"id": body["id"], **workspace.snapshot(), "result": result}


def _open_browser(url):
    """Best-effort launch; never delay serving or expose a failed command/token."""
    try:
        opened = webbrowser.open(url, new=2)
    except Exception:
        opened = False
    if not opened:
        print("ブラウザを開けませんでした。上に表示されたURLを手動で開いてください。", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run MazeProof on localhost; open the printed private URL."
    )
    parser.add_argument(
        "--port", type=int, default=0, help="Loopback port (0 chooses a free port)"
    )
    parser.add_argument("--batch", action="store_true", help="Start at the batch input screen")
    parser.add_argument("--open-browser", action="store_true", help="Open a new browser tab (otherwise print the URL only)")
    args = parser.parse_args(argv)
    try:
        server = LocalServer(("127.0.0.1", args.port))
    except OSError:
        parser.exit(3, "Unable to bind the local port. Choose another --port.\n")
    url = server.origin + ("/batch#" if args.batch else "/#") + server.token
    print("MazeProof: " + url, flush=True)
    print(
        "このURLはこの起動中だけ有効です。共有せずに使ってください。\n"
        "終了前に画面で作業を保存し、このターミナルで Ctrl+C を押してください。",
        flush=True,
    )
    try:
        if args.open_browser:
            threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.workspaces.clear()
        server.storage_costs.clear()
        server.imports.clear()
        server.server_close()
    return 0
