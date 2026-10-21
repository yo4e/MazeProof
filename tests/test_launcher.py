"""Portable startup, browser failure recovery, and no implicit desktop actions."""

import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from mazeproof import server

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = "MazeProof一括検品を開く.command"


class LaunchTests(unittest.TestCase):
    def test_default_is_headless_and_opt_in_opens_batch_in_new_tab(self):
        for arguments, expected_path in (([], "/#"), (["--batch", "--open-browser"], "/batch#")):
            with self.subTest(arguments=arguments):
                local = MagicMock(origin="http://127.0.0.1:12345", token="test-session")
                opened = threading.Event()

                def open_browser(*_args, **_kwargs):
                    opened.set()
                    return True

                def serving(**_kwargs):
                    if arguments:
                        self.assertTrue(opened.wait(2), "browser launch did not run")
                    raise KeyboardInterrupt

                local.serve_forever.side_effect = serving
                out = io.StringIO()
                with patch.object(server, "LocalServer", return_value=local), patch.object(
                    server.webbrowser, "open", side_effect=open_browser
                ) as browser, contextlib.redirect_stdout(out):
                    self.assertEqual(server.main(arguments), 0)
                expected = local.origin + expected_path + local.token
                self.assertEqual(out.getvalue().splitlines()[0], "MazeProof: " + expected)
                if arguments:
                    browser.assert_called_once_with(expected, new=2)
                else:
                    browser.assert_not_called()
                local.server_close.assert_called_once()

    def test_browser_failure_has_manual_fallback_without_exception_details(self):
        for outcome in (False, OSError("private command and token")):
            out = io.StringIO()
            kwargs = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
            with patch.object(server.webbrowser, "open", **kwargs), contextlib.redirect_stdout(out):
                server._open_browser("http://127.0.0.1:12345/#test-session")
            self.assertIn("手動で開いて", out.getvalue())
            self.assertNotIn("private", out.getvalue())
            self.assertNotIn("test-session", out.getvalue())

    def test_busy_port_does_not_open_browser(self):
        with patch.object(server, "LocalServer", side_effect=OSError), patch.object(
            server.webbrowser, "open"
        ) as browser, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                server.main(["--open-browser"])
            self.assertEqual(error.exception.code, 3)
            browser.assert_not_called()

    @unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "POSIX launcher")
    def test_launcher_from_unrelated_directory_with_spaces_and_no_saved_url(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "迷路の作業 folder"
            target.mkdir()
            launcher = target / LAUNCHER
            shutil.copy2(ROOT / LAUNCHER, launcher)
            missing = subprocess.run(["bash", str(launcher)], cwd=temp, capture_output=True, text=True, timeout=5)
            self.assertEqual(missing.returncode, 1)
            self.assertIn("初回準備", missing.stdout)
            python = target / ".venv/bin/python"
            python.parent.mkdir(parents=True)
            python.write_text('#!/bin/sh\nif [ "$2" = "-c" ]; then exit 0; fi\nprintf "%s\\n" "$@"\n')
            python.chmod(0o755)
            launched = subprocess.run(["bash", str(launcher), "--port", "0"], cwd=temp, capture_output=True, text=True, timeout=5)
            self.assertEqual(launched.returncode, 0, launched.stderr)
            self.assertEqual(launched.stdout.splitlines(), ["-I", "-m", "mazeproof", "serve", "--batch", "--open-browser", "--port", "0"])
            self.assertFalse(list(target.glob("*.url")))
