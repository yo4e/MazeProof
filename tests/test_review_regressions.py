"""PR #5 regressions: approval, pixel connectivity, and import ownership."""

import base64
import copy
import io
import json
import socket
import threading
import time
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image, ImageDraw

from mazeproof.imaging import _one_component, inspect
from mazeproof.samples import demo_sources
from mazeproof.server import LocalServer
from mazeproof.workspace import Workspace, inspect_sources


def fast_workspace():
    with patch(
        "mazeproof.workspace.run", side_effect=lambda _op, args, **_kw: inspect(**args)
    ):
        return Workspace({"problem": demo_sources()["problem"]})


class RecognitionRegressions(unittest.TestCase):
    def test_unsynced_undo_revokes_unchanged_digest_and_requires_reapproval(self):
        workspace = fast_workspace()
        workspace.evaluate(approve=True)
        digest, revision = workspace.digest(), workspace.revision
        edits = copy.deepcopy(workspace.edits)
        workspace.set_edits(edits, True, revoke_approval=True)
        self.assertEqual((workspace.digest(), workspace.revision), (digest, revision))
        self.assertEqual(workspace.export()["result"]["overallStatus"], "NEEDS_REVIEW")
        self.assertEqual(workspace.evaluate(approve=True)["overallStatus"], "PASS")

    def test_pixel_connectivity_matches_independent_exhaustive_3x3_floodfill(self):
        for bits in range(512):
            points = {
                (r, c) for r in range(3) for c in range(3) if bits & (1 << (r * 3 + c))
            }
            mask = np.array([[(r, c) in points for c in range(3)] for r in range(3)])
            remaining = set(points)
            if remaining:
                stack = [remaining.pop()]
                while stack:
                    r, c = stack.pop()
                    for dr in (-1, 0, 1):
                        for dc in (-1, 0, 1):
                            neighbor = (r + dr, c + dc)
                            if neighbor in remaining:
                                remaining.remove(neighbor)
                                stack.append(neighbor)
            self.assertEqual(_one_component(mask), bool(points) and not remaining, bits)

    def test_disconnected_complete_projection_requires_route_review_in_real_worker(
        self,
    ):
        problem = Image.new("RGB", (193, 121), "white")
        draw = ImageDraw.Draw(problem)
        draw.line((24, 24, 168, 24), fill="black", width=3)
        draw.line((24, 96, 168, 96), fill="black", width=3)
        solution = problem.copy()
        draw = ImageDraw.Draw(solution)
        draw.line((60, 60, 95, 60), fill=(225, 35, 55), width=1)
        draw.line([(96, 64), (132, 64), (132, 60)], fill=(225, 35, 55), width=1)
        for transpose in (False, True):
            sources = {}
            geometry = {
                "x0": 24,
                "y0": 24,
                "x1": 96 if transpose else 168,
                "y1": 168 if transpose else 96,
                "cols": 1 if transpose else 2,
                "rows": 2 if transpose else 1,
            }
            for role, image in (("problem", problem), ("solution", solution)):
                if transpose:
                    image = image.transpose(Image.Transpose.TRANSPOSE)
                stream = io.BytesIO()
                image.save(stream, "PNG")
                sources[role] = {
                    "name": role + ".png",
                    "data": base64.b64encode(stream.getvalue()).decode(),
                    "geometry": geometry,
                }
            workspace = Workspace(sources)
            self.assertTrue(workspace.observations["solution"]["routeUncertain"])
            self.assertFalse(workspace.edits["solution"]["routeReviewed"])
            self.assertIn(
                "RED_ROUTE_UNCERTAIN", [p["reason"] for p in workspace.pending()]
            )
            self.assertEqual(workspace.evaluate()["overallStatus"], "NEEDS_REVIEW")


class ImportRegressions(unittest.TestCase):
    def setUp(self):
        self.server = LocalServer(("127.0.0.1", 0))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.original = fast_workspace()
        self.original.evaluate(approve=True)
        self.old_id = self.server.put(self.original)["id"]
        self.sources = {"problem": demo_sources()["problem"]}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, path, body, request_id=None, **extra_headers):
        headers = {
            "Content-Type": "application/json",
            "Origin": self.server.origin,
            "Authorization": "Bearer " + self.server.token,
            **extra_headers,
        }
        if request_id:
            headers["X-MazeProof-Import"] = request_id
        req = Request(
            self.server.origin + "/api/" + path, json.dumps(body).encode(), headers
        )
        try:
            response = urlopen(req, timeout=35)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def create(self, claim=True):
        request_id = str(uuid.uuid4())
        status, result = self.request("import", {"sources": self.sources}, request_id)
        if status == 200 and claim:
            self.assertEqual(
                self.request(
                    "import-claim", {"requestId": request_id, "id": result["id"]}
                )[0],
                200,
            )
        return request_id, status, result

    def assert_old_preserved(self):
        self.assertIs(self.server.workspaces[self.old_id], self.original)
        self.assertEqual(self.original.evaluate()["overallStatus"], "PASS")

    def test_http_undo_revocation_is_atomic_with_evaluate_and_export(self):
        for path in ("evaluate", "export"):
            self.original.evaluate(approve=True)
            status, result = self.request(
                path,
                {
                    "id": self.old_id,
                    "revision": self.original.revision,
                    "edits": copy.deepcopy(self.original.edits),
                    "uniqueRequired": True,
                    "revokeApproval": True,
                },
            )
            self.assertEqual(status, 200, result)
            result = (
                result["project"]["result"] if path == "export" else result["result"]
            )
            self.assertEqual(result["overallStatus"], "NEEDS_REVIEW")
        status, _ = self.request(
            "evaluate",
            {
                "id": self.old_id,
                "revision": self.original.revision,
                "edits": self.original.edits,
                "uniqueRequired": True,
                "revokeApproval": "yes",
            },
        )
        self.assertEqual(status, 400)

    def test_cancel_before_acceptance_and_control_auth_and_limits(self):
        request_id = str(uuid.uuid4())
        self.assertEqual(
            self.request("import-cancel", {"requestId": request_id})[0], 200
        )
        with patch("mazeproof.server.Workspace") as work:
            status, result = self.request(
                "import", {"sources": self.sources}, request_id
            )
            self.assertEqual((status, result["error"]), (400, "IMPORT_CANCELLED"))
            work.assert_not_called()
        for path in ("import-cancel", "import-claim"):
            self.assertEqual(
                self.request(path, {}, Authorization="Bearer invalid")[0], 403
            )
            self.assertEqual(self.request(path, {"requestId": "x" * 1100})[0], 413)
            self.assertEqual(self.request(path, {"requestId": "invalid"})[0], 400)
        self.assert_old_preserved()

    def test_cancel_while_real_worker_request_is_running_then_retry(self):
        entered, release = threading.Event(), threading.Event()
        result = []
        request_id = str(uuid.uuid4())

        def gated(sources):
            entered.set()
            if not release.wait(10):
                raise AssertionError("Missing release")
            return inspect_sources(sources)

        with patch("mazeproof.workspace.inspect_sources", side_effect=gated):
            thread = threading.Thread(
                target=lambda: result.append(
                    self.request("import", {"sources": self.sources}, request_id)
                )
            )
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                self.assertTrue(self.server.operation_lock.locked())
                self.assertEqual(
                    self.request("import-cancel", {"requestId": request_id})[0], 200
                )
            finally:
                release.set()
                thread.join(timeout=35)
        self.assertFalse(thread.is_alive())
        self.assertEqual(
            (result[0][0], result[0][1]["error"]), (400, "IMPORT_CANCELLED")
        )
        self.assertEqual(list(self.server.workspaces), [self.old_id])
        self.assertFalse(
            any(r["state"] == "pending" for r in self.server.imports.values())
        )
        self.assertEqual(self.create()[1], 200)
        self.assert_old_preserved()

    def test_unreceived_result_expires_without_evicting_reviewed_work(self):
        now = [time.monotonic()]
        with (
            patch("mazeproof.server.time", SimpleNamespace(monotonic=lambda: now[0])),
            patch("mazeproof.server.MAX_WORKSPACES", 2),
        ):
            request_id, status, result = self.create(claim=False)
            self.assertEqual(status, 200)
            self.assertNotIn(result["id"], self.server.workspaces)
            self.assertEqual(self.create()[2]["error"], "WORKSPACE_LIMIT")
            now[0] += 61
            self.server.service_actions()
            self.assertEqual(
                self.request(
                    "import-claim", {"requestId": request_id, "id": result["id"]}
                )[0],
                400,
            )
            self.assertEqual(self.create()[1], 200)
            self.assert_old_preserved()

    def test_cancel_received_result_and_lost_claim_response_is_idempotent(self):
        for claim in (False, True):
            request_id, status, result = self.create(claim=claim)
            self.assertEqual(status, 200)
            for _ in range(2):
                self.assertEqual(
                    self.request("import-cancel", {"requestId": request_id})[0], 200
                )
            self.assertNotIn(result["id"], self.server.workspaces)
            self.assertNotIn(result["id"], self.server.storage_costs)
            self.assertEqual(
                self.request(
                    "import-claim", {"requestId": request_id, "id": result["id"]}
                )[0],
                400,
            )
        self.assertEqual(self.create()[1], 200)
        self.assert_old_preserved()

    def test_disconnected_accepted_http_request_releases_quota(self):
        entered, release = threading.Event(), threading.Event()
        now = [time.monotonic()]

        def gated(sources):
            entered.set()
            if not release.wait(10):
                raise AssertionError("Missing release")
            return inspect_sources(sources)

        with (
            patch("mazeproof.workspace.inspect_sources", side_effect=gated),
            patch("mazeproof.server.time", SimpleNamespace(monotonic=lambda: now[0])),
            patch("mazeproof.server.MAX_WORKSPACES", 2),
        ):
            client = socket.create_connection(self.server.server_address, timeout=5)
            payload = json.dumps({"sources": self.sources}).encode()
            headers = (
                "POST /api/import HTTP/1.0\r\n"
                f"Host: 127.0.0.1:{self.server.server_address[1]}\r\n"
                f"Origin: {self.server.origin}\r\n"
                f"Authorization: Bearer {self.server.token}\r\n"
                f"X-MazeProof-Import: {uuid.uuid4()}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(payload)}\r\n\r\n"
            ).encode()
            client.sendall(headers + payload)
            try:
                self.assertTrue(entered.wait(5))
                client.shutdown(socket.SHUT_RDWR)
            finally:
                client.close()
                release.set()
            self.assertTrue(self.server.operation_lock.acquire(timeout=35))
            self.server.operation_lock.release()
            now[0] += 61
            self.server.service_actions()
            self.assertEqual(list(self.server.workspaces), [self.old_id])
            self.assertFalse(
                any(r["state"] == "pending" for r in self.server.imports.values())
            )
            self.assertEqual(self.create()[1], 200)
            self.assert_old_preserved()
