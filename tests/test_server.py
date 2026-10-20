"""Loopback API integration: request origins, authentication and stale approvals."""

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from mazeproof.server import LocalServer
from mazeproof.samples import demo_sources


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = LocalServer(("127.0.0.1", 0))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, body=None, headers=None, raw=None):
        defaults = {
            "Origin": self.server.origin,
            "Authorization": "Bearer " + self.server.token,
            "Content-Type": "application/json",
        }
        defaults.update(headers or {})
        data = (
            raw
            if raw is not None
            else (json.dumps(body).encode() if body is not None else None)
        )
        request = Request(self.server.origin + path, data=data, headers=defaults)
        try:
            response = urlopen(request, timeout=35)
        except HTTPError as error:
            response = error
        with response:
            payload = response.read()
            return response.status, response.headers, payload

    def test_static_headers_host_and_paths(self):
        status, headers, data = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("MazeProof", data.decode())
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(self.request("/../../pyproject.toml")[0], 404)
        self.assertEqual(
            self.request("/", headers={"Host": "attacker.example"})[0], 403
        )
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_auth_origin_and_json_rejected(self):
        for headers in (
            {"Authorization": "Bearer wrong"},
            {"Origin": "http://evil.example"},
            {"Origin": "null"},
            {"Content-Type": "text/plain"},
        ):
            self.assertIn(self.request("/api/demo", {}, headers)[0], (403, 415))
        self.assertEqual(self.request("/api/demo", raw=b'{"x":1,"x":2}')[0], 400)
        self.assertEqual(self.request("/api/demo", raw=b'{"x":NaN}')[0], 400)
        with patch("mazeproof.server.MAX_BODY", 1):
            self.assertEqual(self.request("/api/demo", {})[0], 413)

    def test_full_api_flow_revision_and_model_approval(self):
        status, _, raw = self.request("/api/import", {"sources": demo_sources()})
        self.assertEqual(status, 200, raw)
        doc = json.loads(raw)
        self.assertEqual(doc["result"]["overallStatus"], "NEEDS_REVIEW")
        body = {
            "id": doc["id"],
            "revision": doc["revision"],
            "edits": doc["edits"],
            "uniqueRequired": True,
        }
        status, _, raw = self.request("/api/approve", body)
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(raw)["error"], "UNRESOLVED_OBSERVATIONS")
        for role, obs in doc["observations"].items():
            body["edits"][role]["resolved"] = [u["id"] for u in obs["unknowns"]]
        status, _, raw = self.request("/api/approve", body)
        self.assertEqual(status, 200, raw)
        confirmed = json.loads(raw)
        self.assertEqual(confirmed["result"]["overallStatus"], "PASS")
        stale = self.request("/api/evaluate", body)
        self.assertEqual(stale[0], 400)
        self.assertEqual(json.loads(stale[2])["error"], "STALE_REVISION")
        body["revision"] = confirmed["revision"]
        body["edits"]["problem"]["model"]["verticalWalls"][0][1] = True
        status, _, raw = self.request("/api/evaluate", body)
        edited = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(edited["result"]["overallStatus"], "NEEDS_REVIEW")
        self.assertFalse(edited["approved"])
        body["revision"] = edited["revision"]
        _, _, raw = self.request("/api/export", body)
        project = json.loads(raw)["project"]
        self.assertEqual(project["result"]["overallStatus"], "NEEDS_REVIEW")
        self.assertEqual(project["sources"], demo_sources())
        self.assertEqual(
            self.request(
                "/api/close", {"id": doc["id"], "revision": edited["revision"]}
            )[0],
            200,
        )
        self.assertEqual(self.request("/api/state", {"id": doc["id"]})[0], 400)

    def test_busy_and_internal_failure_do_not_return_previous_pass(self):
        self.server.operation_lock.acquire()
        try:
            self.assertEqual(self.request("/api/demo", {})[0], 409)
        finally:
            self.server.operation_lock.release()
        with patch(
            "mazeproof.server.Workspace", side_effect=RuntimeError("private details")
        ):
            status, _, raw = self.request("/api/import", {"sources": demo_sources()})
        self.assertEqual(status, 500)
        self.assertNotIn("private details", raw.decode())
        self.assertEqual(json.loads(raw)["result"]["overallStatus"], "ERROR")
        self.assertEqual(self.request("/api/demo", {})[0], 200)
