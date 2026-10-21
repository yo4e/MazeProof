"""Image CLI errors obey the same exit/result/privacy contract as JSON CLI."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from mazeproof import core
from mazeproof.cli import InputError, main
from mazeproof.commands import inspect_main


class InspectCliErrorTests(unittest.TestCase):
    def invoke(self, args, entry=inspect_main):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = entry(args)
        return code, json.loads(output.getvalue()), errors.getvalue()

    def assert_error(self, response, reason, status="INVALID_INPUT", policy=True):
        code, result, errors = response
        self.assertEqual(code, 3)
        self.assertEqual(result["schemaVersion"], "mazeproof.result/1")
        self.assertEqual(result["overallStatus"], status)
        self.assertEqual(result["issues"][0]["reasonCode"], reason)
        self.assertEqual(result["policy"]["unique_required"], policy)
        self.assertTrue(
            all(c["status"] == "NOT_RUN" for c in result["checks"].values())
        )
        self.assertNotIn("Traceback", errors)

    def test_missing_problem_is_invalid_input_not_review(self):
        with patch("mazeproof.commands.read_file") as read:
            self.assert_error(self.invoke([]), "CLI_ARGUMENTS")
            read.assert_not_called()

    def test_bad_pages_do_not_echo_argument_values(self):
        for option in ("--problem-page", "--solution-page"):
            with self.subTest(option=option):
                response = self.invoke(["private.png", option, "PRIVATE_PAGE_VALUE"])
                self.assert_error(response, "CLI_ARGUMENTS")
                self.assertNotIn("PRIVATE_PAGE_VALUE", response[2])
                self.assertNotIn("private.png", response[2])

    def test_unknown_option_through_top_level_dispatch(self):
        response = self.invoke(
            ["inspect", "private.png", "--PRIVATE_UNKNOWN_OPTION"], entry=main
        )
        self.assert_error(response, "CLI_ARGUMENTS")
        self.assertNotIn("PRIVATE_UNKNOWN_OPTION", response[2])
        self.assertNotIn("private.png", response[2])

    def test_help_still_exits_zero_without_reading_files(self):
        output = io.StringIO()
        with patch("mazeproof.commands.read_file") as read:
            with (
                contextlib.redirect_stdout(output),
                self.assertRaises(SystemExit) as raised,
            ):
                inspect_main(["--help"])
            self.assertEqual(raised.exception.code, 0)
            self.assertIn("--save-project", output.getvalue())
            read.assert_not_called()

    def test_input_error_preserves_requested_policy(self):
        with patch(
            "mazeproof.commands.read_file",
            side_effect=InputError("INVALID_INPUT", "FILE_READ_ERROR"),
        ):
            self.assert_error(
                self.invoke(["missing.png", "--allow-multiple"]),
                "FILE_READ_ERROR",
                policy=False,
            )

    def test_decoder_rejection_preserves_requested_policy(self):
        with patch("mazeproof.commands.read_file", return_value=b"synthetic"):
            with patch(
                "mazeproof.commands.Workspace",
                side_effect=core.Rejected("RESOURCE_LIMIT", "MEMORY_LIMIT"),
            ):
                self.assert_error(
                    self.invoke(["problem.png", "--allow-multiple"]),
                    "MEMORY_LIMIT",
                    status="RESOURCE_LIMIT",
                    policy=False,
                )

    def test_existing_output_is_not_overwritten_and_preserves_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "existing.mazeproof"
            target.write_text("original", encoding="utf-8")
            with patch("mazeproof.commands.read_file", return_value=b"synthetic"):
                with patch("mazeproof.commands.Workspace") as workspace:
                    workspace.return_value.evaluate.return_value = {
                        "overallStatus": "NEEDS_REVIEW"
                    }
                    workspace.return_value.export.return_value = {}
                    response = self.invoke(
                        ["problem.png", "--allow-multiple", "--save-project", str(target)]
                    )
            self.assert_error(response, "OUTPUT_ALREADY_EXISTS", policy=False)
            self.assertEqual(target.read_text(encoding="utf-8"), "original")

    def test_unexpected_error_is_sanitized_and_preserves_policy(self):
        with patch("mazeproof.commands.read_file", return_value=b"synthetic"):
            with patch(
                "mazeproof.commands.Workspace",
                side_effect=RuntimeError("PRIVATE_INTERNAL_DETAILS"),
            ):
                response = self.invoke(["problem.png", "--allow-multiple"])
        self.assert_error(response, "INSPECT_FAILED", status="ERROR", policy=False)
        self.assertNotIn("PRIVATE_INTERNAL_DETAILS", json.dumps(response))

    def test_unwritable_stdout_returns_three_without_raising(self):
        for error in (BrokenPipeError(), OSError("unwritable")):
            with self.subTest(error=type(error).__name__):
                with patch(
                    "mazeproof.commands.read_file",
                    side_effect=InputError("INVALID_INPUT", "FILE_READ_ERROR"),
                ):
                    stream = io.StringIO()
                    with contextlib.redirect_stdout(stream), patch.object(stream, "write", side_effect=error):
                        self.assertEqual(inspect_main(["missing.png"]), 3)

    @unittest.skipIf(os.name == "nt", "POSIX pipe descriptors")
    def test_real_closed_stdout_pipe_exits_three_without_shutdown_error(self):
        for args in (["inspect", "missing.png"], ["missing.json"], ["missing.json", "--format", "text"]):
            with self.subTest(args=args):
                read, write = os.pipe()
                os.close(read)
                try:
                    process = subprocess.run(
                        [sys.executable, "-m", "mazeproof", *args],
                        stdout=write, stderr=subprocess.PIPE, timeout=10,
                    )
                finally:
                    os.close(write)
                self.assertEqual(process.returncode, 3)
                self.assertEqual(process.stderr, b"")

    @unittest.skipUnless(Path("/dev/full").exists(), "Linux full device")
    def test_real_unwritable_stdout_exits_three(self):
        with open("/dev/full", "wb") as output:
            process = subprocess.run(
                [sys.executable, "-m", "mazeproof", "inspect", "missing.png"],
                stdout=output, stderr=subprocess.PIPE, timeout=10,
            )
        self.assertEqual(process.returncode, 3)
        self.assertEqual(process.stderr, b"")

    def test_successful_unconfirmed_inspection_still_returns_two(self):
        with patch("mazeproof.commands.read_file", return_value=b"synthetic"):
            with patch("mazeproof.commands.Workspace") as workspace:
                workspace.return_value.evaluate.return_value = {
                    "overallStatus": "NEEDS_REVIEW"
                }
                code, result, errors = self.invoke(
                    ["problem.pdf", "--problem-page", "2", "--allow-multiple"]
                )
                self.assertEqual(code, 2)
                self.assertEqual(result["overallStatus"], "NEEDS_REVIEW")
                self.assertEqual(errors, "")
                self.assertFalse(workspace.return_value.unique_required)
                self.assertEqual(workspace.call_args.args[0]["problem"]["page"], 2)


if __name__ == "__main__":
    unittest.main()
