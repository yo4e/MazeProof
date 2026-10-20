"""Check a wheel installed into another environment, outside the source tree."""

import argparse
import json
import subprocess
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as working:
        module = subprocess.check_output(
            [args.python, "-c", "import mazeproof;print(mazeproof.__file__)"],
            cwd=working,
            text=True,
        ).strip()
        if "site-packages" not in module:
            raise AssertionError("Expected an installed package")
        server = subprocess.Popen(
            [args.python, "-m", "mazeproof", "serve"],
            cwd=working,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            line = server.stdout.readline().strip()
            if not line.startswith("MazeProof: "):
                raise AssertionError("Installed server failed to start")
            parts = urlsplit(line.removeprefix("MazeProof: "))
            origin = parts.scheme + "://" + parts.netloc
            assets = ("/", "/app.js", "/style.css", "/help", "/help.css")
            for path in assets:
                with urlopen(origin + path, timeout=10) as response:
                    assert response.status == 200 and len(response.read()) > 100

            def post(path, body):
                request = Request(
                    origin + "/api/" + path,
                    json.dumps(body).encode(),
                    {
                        "Content-Type": "application/json",
                        "Origin": origin,
                        "Authorization": "Bearer " + parts.fragment,
                    },
                )
                with urlopen(request, timeout=40) as response:
                    return json.load(response)

            document = post("demo", {})
            assert document["result"]["overallStatus"] == "NEEDS_REVIEW"
            for role, obs in document["observations"].items():
                document["edits"][role]["resolved"] = [
                    item["id"] for item in obs["unknowns"]
                ]
            confirmed = post(
                "approve",
                {
                    "id": document["id"],
                    "revision": document["revision"],
                    "edits": document["edits"],
                    "uniqueRequired": True,
                },
            )
            assert confirmed["result"]["overallStatus"] == "PASS"
            print(
                json.dumps(
                    {
                        "installedOutsideRepository": True,
                        "staticAssets": len(assets),
                        "workerImageDecode": True,
                        "unconfirmedThenApproved": True,
                    },
                    indent=2,
                )
            )
        finally:
            server.terminate()
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()
