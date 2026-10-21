"""Measure wall extraction separately from the mandatory review gate."""

import base64
import io
import json
from pathlib import Path
import random
import resource
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mazeproof.imaging import inspect  # noqa: E402
from mazeproof.samples import render  # noqa: E402
from mazeproof.workspace import Workspace  # noqa: E402


def model(width, height, seed):
    rng = random.Random(seed)
    horizontal = (
        [[True] * width]
        + [[rng.random() < 0.5 for _ in range(width)] for _ in range(height - 1)]
        + [[True] * width]
    )
    vertical = [
        [True] + [rng.random() < 0.5 for _ in range(width - 1)] + [True]
        for _ in range(height)
    ]
    horizontal[0][0] = False
    horizontal[-1][-1] = False
    return {
        "schemaVersion": "mazeproof.maze/1",
        "width": width,
        "height": height,
        "horizontalWalls": horizontal,
        "verticalWalls": vertical,
        "entrance": {"row": 0, "col": 0, "side": "N"},
        "exit": {"row": height - 1, "col": width - 1, "side": "S"},
    }


def main():
    started = time.monotonic()
    cases = []
    for width, height in ((3, 4), (10, 8), (25, 20)):
        expected = model(width, height, 20261020 + width)
        for thickness in (1, 3, 5):
            for fmt, quality in (("PNG", None), ("JPEG", 90), ("JPEG", 40)):
                image = render(expected, cell=36, margin=24, thickness=thickness)
                stream = io.BytesIO()
                image.save(stream, fmt, **({"quality": quality} if quality else {}))
                raw = stream.getvalue()
                name = "synthetic." + ("png" if fmt == "PNG" else "jpg")
                geometry = {
                    "x0": 24,
                    "y0": 24,
                    "x1": 24 + 36 * width,
                    "y1": 24 + 36 * height,
                    "cols": width,
                    "rows": height,
                }
                before = time.monotonic()
                observed = inspect(raw, name, geometry=geometry)
                automatic = inspect(raw, name)
                walls = sum(
                    len(row)
                    for field in ("horizontalWalls", "verticalWalls")
                    for row in expected[field]
                )
                correct = sum(
                    a == b
                    for field in ("horizontalWalls", "verticalWalls")
                    for row, other in zip(expected[field], observed["model"][field])
                    for a, b in zip(row, other)
                )
                sources = {
                    "problem": {
                        "name": name,
                        "data": base64.b64encode(raw).decode(),
                        "geometry": geometry,
                    }
                }
                with patch("mazeproof.workspace.run", return_value=observed):
                    workspace = Workspace(sources)
                result = workspace.evaluate()
                assert result["overallStatus"] == "NEEDS_REVIEW"
                cases.append(
                    {
                        "grid": [width, height],
                        "wallPixels": thickness,
                        "format": fmt,
                        "quality": quality,
                        "walls": walls,
                        "correctWalls": correct,
                        "topologyExactWithKnownGrid": correct == walls,
                        "automaticModelExact": automatic["model"] == expected,
                        "unknownBoundaries": len(observed["unknowns"]),
                        "overallStatus": result["overallStatus"],
                        "seconds": round(time.monotonic() - before, 4),
                    }
                )
    report = {
        "seedRule": "20261020 + width",
        "cases": cases,
        "count": len(cases),
        "knownGridExact": sum(c["topologyExactWithKnownGrid"] for c in cases),
        "automaticExact": sum(c["automaticModelExact"] for c in cases),
        "unconfirmedPass": sum(c["overallStatus"] == "PASS" for c in cases),
        "seconds": round(time.monotonic() - started, 3),
        "peakRssPlatformUnits": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "runtime": sys.version.split()[0],
    }
    folder = ROOT / ".evidence"
    folder.mkdir(exist_ok=True)
    (folder / "corpus.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))


if __name__ == "__main__":
    main()
