"""Real worker and stdio integration plus filesystem capability tests."""

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mazeproof import core
from mazeproof.mcp import RootReader, MCP
from mazeproof.samples import demo_sources, demo_model
from mazeproof.worker import run

ROOT = Path(__file__).resolve().parents[1]


class LocalTests(unittest.TestCase):
    def test_worker_success_timeout_memory_and_bad_operation(self):
        result = run("structure", {"problem": json.dumps(demo_model())})
        self.assertEqual(result["overallStatus"], "PASS")
        for kwargs, code in [
            ({"seconds": 0}, "WORKER_TIMEOUT"),
            ({"memory": 1}, "MEMORY_LIMIT"),
        ]:
            with self.assertRaises(core.Rejected) as e:
                run("structure", {"problem": "{}"}, **kwargs)
            self.assertEqual(e.exception.code, code)
        with self.assertRaises(core.Rejected):
            run("bad", {})
        src = demo_sources()["problem"]
        observed = run(
            "inspect", {"data": base64.b64decode(src["data"]), "name": src["name"]}
        )
        self.assertEqual(observed["model"], demo_model())

    def test_root_path_escape_symlink_special_file_and_size(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "allowed"
            root.mkdir()
            (root / "file.json").write_text("{}")
            outside = Path(folder) / "outside"
            outside.write_text("private")
            (root / "link").symlink_to(outside)
            nested = root / "nested"
            nested.mkdir()
            (nested / "good").write_text("safe")
            (root / "dirlink").symlink_to(nested, target_is_directory=True)
            os.mkfifo(root / "fifo")
            reader = RootReader([root])
            try:
                self.assertEqual(reader.read(str(nested / "good")), b"safe")
                for path in (
                    str(outside),
                    str(root / "link"),
                    str(root / "dirlink" / "good"),
                    str(root / "fifo"),
                    str(root),
                    str(root / "../outside"),
                    "file:///x",
                    "https://x/a",
                    "relative",
                ):
                    with self.subTest(path=path):
                        with self.assertRaises(core.Rejected):
                            reader.read(path)
                with open(root / "huge", "wb") as f:
                    f.truncate(core.MAX_BYTES + 1)
                with self.assertRaises(core.Rejected) as e:
                    reader.read(str(root / "huge"))
                self.assertEqual(e.exception.status, "RESOURCE_LIMIT")
                # Swap a parent directory after the root was opened. No symlink traversal.
                nested.rename(root / "original")
                nested.symlink_to(Path(folder), target_is_directory=True)
                with self.assertRaises(core.Rejected):
                    reader.read(str(nested / "outside"))
            finally:
                reader.close()

    def test_mcp_stdio_handshake_and_core_equivalence(self):
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "synthetic-test", "version": "1"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "validate_structure",
                    "arguments": {"problem": json.dumps(demo_model())},
                },
            },
        ]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "mazeproof",
                "mcp",
                "--allow-root",
                str(ROOT / "examples"),
            ],
            input="\n".join(json.dumps(r) for r in requests) + "\n",
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(replies), 3)
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(len(replies[1]["result"]["tools"]), 5)
        parsed = json.loads(replies[2]["result"]["content"][0]["text"])["result"]
        exact = core.validate_structure(json.dumps(demo_model()))
        self.assertEqual(parsed["checks"], exact["checks"])
        self.assertEqual(parsed["evidence"], exact["evidence"])

    def test_mcp_image_pair_cannot_confirm_and_get_result(self):
        with tempfile.TemporaryDirectory() as folder:
            for role, src in demo_sources().items():
                (Path(folder) / src["name"]).write_bytes(base64.b64decode(src["data"]))
            reader = RootReader([folder])
            server = MCP(reader)
            try:
                response = server.call(
                    "validate_pair",
                    {
                        "problem": str(Path(folder) / "problem.png"),
                        "solution": str(Path(folder) / "solution.png"),
                    },
                )
                self.assertEqual(response["result"]["overallStatus"], "NEEDS_REVIEW")
                self.assertEqual(
                    server.call(
                        "get_result", {"requestId": response["result"]["requestId"]}
                    ),
                    response,
                )
                with self.assertRaises(core.Rejected):
                    server.call("approve", {})
                with self.assertRaises(core.Rejected):
                    server.call(
                        "inspect_file",
                        {"path": str(Path(folder) / "problem.png"), "confirmed": True},
                    )
                self.assertNotIn("image", response["observations"]["problem"])
                self.assertEqual(
                    (Path(folder) / "problem.png").read_bytes(),
                    base64.b64decode(demo_sources()["problem"]["data"]),
                )
            finally:
                reader.close()

    def test_image_cli_review_exit_and_project_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "problem.png"
            path.write_bytes(base64.b64decode(demo_sources()["problem"]["data"]))
            output = Path(folder) / "work.mazeproof"
            args = [
                sys.executable,
                "-m",
                "mazeproof",
                "inspect",
                str(path),
                "--save-project",
                str(output),
            ]
            result = subprocess.run(
                args, cwd=ROOT, capture_output=True, text=True, timeout=30
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(json.loads(result.stdout)["overallStatus"], "NEEDS_REVIEW")
            saved = output.read_bytes()
            result = subprocess.run(
                args, cwd=ROOT, capture_output=True, text=True, timeout=30
            )
            self.assertEqual(result.returncode, 3)
            self.assertEqual(output.read_bytes(), saved)
            self.assertEqual(
                json.loads(result.stdout)["issues"][0]["reasonCode"],
                "OUTPUT_ALREADY_EXISTS",
            )
