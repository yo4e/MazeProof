"""Saved documents fit the bounded restore path and never carry approval."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mazeproof import core
from mazeproof.commands import inspect_main
from mazeproof.samples import demo_model, demo_route, demo_sources
from mazeproof.workspace import (
    MAX_PROJECT_BYTES, MAX_PROJECT_REQUEST_BYTES, Workspace, canonical, project_json,
)


class ProjectFileTests(unittest.TestCase):
    def test_compact_document_has_room_for_restore_envelope(self):
        value = {"name": "原画像.png", "route": [{"row": 1, "col": 2}]}
        text = project_json(value)
        self.assertEqual(json.loads(text), value)
        with patch("mazeproof.workspace.MAX_PROJECT_BYTES", len(text.encode())):
            self.assertEqual(project_json(value), text)
        with patch("mazeproof.workspace.MAX_PROJECT_BYTES", len(text.encode()) - 1):
            with self.assertRaises(core.Rejected) as rejected:
                project_json(value)
            self.assertEqual(rejected.exception.code, "PROJECT_SIZE_LIMIT")
        self.assertLess(len(canonical({"project": value}).encode()) - len(text), MAX_PROJECT_REQUEST_BYTES - MAX_PROJECT_BYTES)

    def test_legacy_project_roundtrip_preserves_edits_but_not_approval(self):
        workspace = Workspace(demo_sources())
        edits = copy.deepcopy(workspace.edits)
        for role, edit in edits.items():
            edit["model"] = demo_model()
            if role == "solution":
                edit["model"]["route"] = demo_route()
            edit["resolved"] = [u["id"] for u in workspace.observations[role]["unknowns"]]
            edit["routeReviewed"] = True
        workspace.set_edits(edits, False)
        workspace.evaluate(approve=True)
        saved = workspace.export()
        self.assertEqual(saved["schemaVersion"], "mazeproof.project/1")
        self.assertEqual(saved["result"]["overallStatus"], "PASS")
        # Old indented files and new compact files restore through the same path.
        for text in (json.dumps(saved, indent=2), project_json(saved)):
            restored = Workspace.restore(json.loads(text))
            self.assertEqual(restored.edits, workspace.edits)
            self.assertFalse(restored.unique_required)
            self.assertFalse(restored.snapshot()["approved"])
            self.assertEqual(restored.evaluate()["overallStatus"], "NEEDS_REVIEW")

    def test_oversized_export_and_restore_leave_workspace_unchanged(self):
        workspace = Workspace(demo_sources())
        saved = workspace.export()
        before = copy.deepcopy(workspace.snapshot())
        with patch("mazeproof.workspace.MAX_PROJECT_BYTES", 1):
            for operation in (workspace.export, lambda: Workspace.restore(saved)):
                with self.assertRaises(core.Rejected) as rejected:
                    operation()
                self.assertEqual(rejected.exception.code, "PROJECT_SIZE_LIMIT")
        self.assertEqual(workspace.snapshot(), before)

    def test_oversized_cli_save_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "new.mazeproof"
            output = io.StringIO()
            with (
                patch("mazeproof.commands.read_file", return_value=b"fixture"),
                patch("mazeproof.commands.Workspace") as workspace,
                patch("mazeproof.workspace.MAX_PROJECT_BYTES", 1),
                contextlib.redirect_stdout(output),
            ):
                workspace.return_value.export.return_value = {"fixture": "large"}
                code = inspect_main(["problem.png", "--allow-multiple", "--save-project", str(target)])
            self.assertEqual(code, 3)
            result = json.loads(output.getvalue())
            self.assertEqual(result["issues"][0]["reasonCode"], "PROJECT_SIZE_LIMIT")
            self.assertFalse(result["policy"]["unique_required"])
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
