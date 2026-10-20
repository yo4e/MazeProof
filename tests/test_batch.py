"""Batch isolation, restore trust, resource budgets, and UI/MCP equivalence."""

import base64
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mazeproof import core
from mazeproof.batch import inspect_item, inspect_many
from mazeproof.imaging import inspect as inspect_direct
from mazeproof.mcp import MCP, RootReader
from mazeproof.samples import demo_sources
from mazeproof.server import LocalServer
from mazeproof.workspace import Workspace


def direct(_op, arguments, **_kwargs):
    return inspect_direct(**arguments)


class BatchTests(unittest.TestCase):
    def test_100_mixed_items_continue_and_never_approve(self):
        sources = demo_sources()
        items = [{"id": f"item-{i}"} for i in range(100)]

        def load(item):
            i = int(item["id"].split("-")[1])
            if i % 10 == 0:
                raise core.Rejected("INVALID_INPUT", "TEST_BROKEN_IMAGE")
            return {"sources": sources if i % 2 else {"problem": sources["problem"]}}

        with patch("mazeproof.workspace.run", side_effect=direct):
            result = inspect_many(items, load)
        self.assertEqual(
            result["counts"], {"NEEDS_REVIEW": 90, "ERROR": 10, "QUEUED": 0}
        )
        self.assertEqual([x["id"] for x in result["items"]], [x["id"] for x in items])
        self.assertEqual(result["overallStatus"], "NEEDS_REVIEW")
        self.assertNotIn(
            "PASS", [x["result"]["overallStatus"] for x in result["items"]]
        )
        self.assertEqual(
            result["items"][-1]["result"]["recognition"]["assurance"],
            "recognized_unconfirmed",
        )

    def test_restore_recomputes_and_never_trusts_saved_pass(self):
        with patch("mazeproof.workspace.run", side_effect=direct):
            original = Workspace({"problem": demo_sources()["problem"]})
            original.evaluate(approve=True)
            project = original.export()
            project["result"]["recognition"]["assurance"] = "human_confirmed"
            project["result"]["overallStatus"] = "PASS"
            restored = inspect_item({"project": project})
        self.assertEqual(restored.evaluate()["overallStatus"], "NEEDS_REVIEW")
        self.assertEqual(restored.edits, original.edits)
        with self.assertRaises(core.Rejected):
            inspect_item({"sources": demo_sources(), "approved": True})

    def test_batch_limits_and_duplicate_ids_do_not_load_files(self):
        def forbidden(_):
            self.fail("Invalid batch must not load any files")

        for items in (
            [],
            [{"id": "x"}] * 2,
            [{"id": str(i)} for i in range(101)],
            [{"id": 1}],
        ):
            with self.assertRaises(core.Rejected):
                inspect_many(items, forbidden)
        with patch("mazeproof.batch.MAX_BATCH_SECONDS", -1):
            result = inspect_many([{"id": "a"}, {"id": "b"}], forbidden)
        self.assertEqual(result["counts"]["QUEUED"], 2)
        self.assertEqual(result["overallStatus"], "NEEDS_REVIEW")
        self.assertEqual(result["items"][0]["reason"], "BATCH_TIME_LIMIT")
        with (
            patch("mazeproof.workspace.run", side_effect=direct),
            patch("mazeproof.batch.MAX_RESULT_BYTES", 3000),
        ):
            result = inspect_many(
                [{"id": "a"}, {"id": "b"}], lambda _: {"sources": demo_sources()}
            )
        self.assertTrue(
            any(
                row.get("reason") == "BATCH_RESULT_LIMIT"
                or row.get("result", {}).get("overallStatus") == "RESOURCE_LIMIT"
                for row in result["items"]
            )
        )
        self.assertNotEqual(result["overallStatus"], "PASS")

    def test_retention_never_silently_evicts_edits_or_approvals(self):
        server = LocalServer(("127.0.0.1", 0))
        try:
            with patch("mazeproof.workspace.run", side_effect=direct):
                first = Workspace({"problem": demo_sources()["problem"]})
                first.evaluate(approve=True)
                first_id = server.put(first)["id"]
                for _ in range(5):
                    server.put(Workspace({"problem": demo_sources()["problem"]}))
            self.assertIs(server.workspaces[first_id], first)
            self.assertEqual(first.evaluate()["overallStatus"], "PASS")
            with (
                patch("mazeproof.server.MAX_WORKSPACES", 6),
                self.assertRaises(core.Rejected),
            ):
                server.put(first)
            with (
                patch("mazeproof.server.MAX_STORED_BYTES", 1),
                self.assertRaises(core.Rejected),
            ):
                server.put(first)
            self.assertEqual(len(server.workspaces), 6)
            self.assertEqual(first.evaluate()["overallStatus"], "PASS")
        finally:
            server.server_close()

    def test_mcp_batch_matches_ui_engine_and_rejects_outside_root(self):
        with tempfile.TemporaryDirectory() as folder:
            sources = demo_sources()
            for src in sources.values():
                (Path(folder) / src["name"]).write_bytes(base64.b64decode(src["data"]))
            reader = RootReader([folder])
            mcp = MCP(reader)
            try:
                with patch("mazeproof.workspace.run", side_effect=direct):
                    ui = inspect_item({"sources": sources}).evaluate()
                    result = mcp.call(
                        "inspect_batch",
                        {
                            "items": [
                                {
                                    "id": "valid",
                                    "problem": str(Path(folder) / "problem.png"),
                                    "solution": str(Path(folder) / "solution.png"),
                                },
                                {"id": "outside", "problem": "/outside/private.png"},
                                {
                                    "id": "injection",
                                    "problem": str(Path(folder) / "problem.png"),
                                    "confirmed": True,
                                },
                            ]
                        },
                    )["result"]
                valid = result["items"][0]["result"]
                self.assertEqual(valid["checks"], ui["checks"])
                self.assertEqual(valid["inputDigests"], ui["inputDigests"])
                self.assertEqual(valid["evidence"], ui["evidence"])
                self.assertEqual(
                    result["counts"], {"NEEDS_REVIEW": 1, "ERROR": 2, "QUEUED": 0}
                )
                self.assertEqual(
                    mcp.call("get_result", {"requestId": result["requestId"]})[
                        "result"
                    ],
                    result,
                )
                self.assertNotIn("private.png", str(result))
                self.assertEqual(
                    (Path(folder) / "problem.png").read_bytes(),
                    base64.b64decode(sources["problem"]["data"]),
                )
            finally:
                reader.close()

    def test_unknowns_and_policy_change_still_require_review(self):
        with patch("mazeproof.workspace.run", side_effect=direct):
            workspace = inspect_item(
                {"sources": demo_sources(), "uniqueRequired": False}
            )
        self.assertFalse(workspace.unique_required)
        self.assertTrue(workspace.pending())
        with self.assertRaises(core.Rejected):
            workspace.evaluate(approve=True)
        edits = copy.deepcopy(workspace.edits)
        for role, obs in workspace.observations.items():
            edits[role]["resolved"] = [u["id"] for u in obs["unknowns"]]
        workspace.set_edits(edits, False)
        self.assertEqual(workspace.evaluate(approve=True)["overallStatus"], "PASS")
        workspace.set_edits(edits, True)
        self.assertEqual(workspace.evaluate()["overallStatus"], "NEEDS_REVIEW")
