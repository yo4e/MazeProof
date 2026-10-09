"""End-to-end subprocess checks for the practical module CLI."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mazeproof import cli, core

ROOT = Path(__file__).resolve().parents[1]


def command(*arguments):
    return subprocess.run([sys.executable, "-m", "mazeproof", *arguments], cwd=ROOT,
                          capture_output=True, text=True, timeout=10)


class CliTests(unittest.TestCase):
    def test_four_public_examples(self):
        for args, status, code, reason in (
            (("examples/problem.json", "--solution", "examples/solution.json"), "PASS", 0, None),
            (("examples/multiple.json",), "FAIL", 1, "MULTIPLE"),
            (("examples/wall-crossing.json",), "FAIL", 1, "ROUTE_WALL_CROSSING"),
            (("examples/invalid.json",), "INVALID_INPUT", 3, "OBJECT_FIELDS"),
        ):
            with self.subTest(args=args):
                process = command(*args)
                self.assertEqual(process.returncode, code, process.stderr)
                self.assertEqual(process.stderr, "")
                result = json.loads(process.stdout)
                self.assertEqual(result["overallStatus"], status)
                if reason:
                    self.assertIn(reason, [issue["reasonCode"] for issue in result["issues"]])
                self.assertEqual(result["checks"]["renderedAgreement"]["status"], "NOT_RUN")

    def test_allow_multiple_and_text_scope(self):
        process = command("examples/multiple.json", "--allow-multiple")
        result = json.loads(process.stdout)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(result["evidence"]["uniqueness"], "multiple")
        self.assertFalse(result["policy"]["unique_required"])
        process = command("examples/problem.json", "--format", "text")
        self.assertEqual(process.returncode, 0)
        self.assertIn("exact_structure", process.stdout)
        self.assertIn("routeValidity: NOT_RUN", process.stdout)
        self.assertIn("renderedAgreement: NOT_RUN", process.stdout)
        process = command("examples/wall-crossing.json", "--format", "text")
        self.assertEqual(process.returncode, 1)
        self.assertIn('"index": 1', process.stdout)

    def test_cli_and_core_result_match_and_inputs_unchanged(self):
        problem = (ROOT / "examples/problem.json").read_bytes()
        solution = (ROOT / "examples/solution.json").read_bytes()
        expected = core.validate_structure(problem, solution)
        actual = json.loads(command("examples/problem.json", "--solution", "examples/solution.json").stdout)
        expected.pop("requestId")
        actual.pop("requestId")
        self.assertEqual(actual, expected)
        self.assertEqual(problem, (ROOT / "examples/problem.json").read_bytes())
        self.assertEqual(solution, (ROOT / "examples/solution.json").read_bytes())

    def test_argument_errors_and_help(self):
        for arguments in ((), ("--unknown",), ("examples/problem.json", "--format", "other"),
                          ("examples/problem.json", "--solution")):
            process = command(*arguments)
            self.assertEqual(process.returncode, 3)
            self.assertEqual(json.loads(process.stdout)["issues"][0]["reasonCode"], "CLI_ARGUMENTS")
            self.assertNotIn("Traceback", process.stderr)
        process = command("--help")
        self.assertEqual(process.returncode, 0)
        self.assertIn("--solution", process.stdout)

    def test_files_and_no_private_path_in_errors(self):
        for path in ("missing-private-name.json", "examples", "https://example.com/maze.json", "//host/share/file"):
            process = command(path)
            self.assertEqual(process.returncode, 3)
            self.assertEqual(json.loads(process.stdout)["overallStatus"], "INVALID_INPUT")
            self.assertNotIn(path, process.stdout + process.stderr)
        process = command("examples/problem.json", "--solution", "missing-private-solution.json")
        self.assertEqual(process.returncode, 3)
        self.assertEqual(json.loads(process.stdout)["scope"]["checked"], [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            for raw, status in ((b'\xff', "INVALID_INPUT"), (b'{"x":1,"x":2}', "INVALID_INPUT"),
                                (b'%PDF-1.7', "UNSUPPORTED"), (b'\x89PNG', "UNSUPPORTED"),
                                (b'\xff\xd8', "UNSUPPORTED")):
                path.write_bytes(raw)
                process = command(str(path))
                self.assertEqual(process.returncode, 3)
                self.assertEqual(json.loads(process.stdout)["overallStatus"], status)
            if hasattr(os, "mkfifo"):
                fifo = Path(directory) / "fifo"
                os.mkfifo(fifo)
                process = command(str(fifo))
                self.assertEqual(process.returncode, 3)
                self.assertEqual(json.loads(process.stdout)["issues"][0]["reasonCode"], "REGULAR_FILE_REQUIRED")

    def test_byte_limit_before_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "huge.json"
            with path.open("wb") as stream:
                stream.truncate(core.MAX_BYTES + 1)
            process = command(str(path))
            self.assertEqual(process.returncode, 3)
            self.assertEqual(json.loads(process.stdout)["overallStatus"], "RESOURCE_LIMIT")

    def test_adapter_faults_and_reserved_exit_codes(self):
        self.assertEqual(cli.EXIT_CODES["NEEDS_REVIEW"], 2)
        output = io.StringIO()
        with patch.object(cli, "read_file", side_effect=RuntimeError("private path")), contextlib.redirect_stdout(output):
            self.assertEqual(cli.main(["examples/problem.json", "--allow-multiple"]), 3)
        result = json.loads(output.getvalue())
        self.assertEqual(result["overallStatus"], "ERROR")
        self.assertFalse(result["policy"]["unique_required"])
        self.assertNotIn("private path", output.getvalue())
        with patch.object(cli.sys.stdout, "write", side_effect=BrokenPipeError):
            self.assertEqual(cli.main(["examples/problem.json"]), 3)
