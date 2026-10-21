"""Create original synthetic demo files in a new folder (never overwrites)."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mazeproof.samples import demo_model, demo_route, render  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    target = parser.parse_args().directory
    target.mkdir(parents=True, exist_ok=False)
    problem = render(demo_model())
    answer = render(demo_model(), demo_route())
    problem.save(target / "problem.png")
    answer.save(target / "solution.png")
    problem.save(target / "problem.jpg", quality=90)
    answer.save(target / "solution.jpg", quality=90)
    problem.save(target / "pair.pdf", "PDF", save_all=True, append_images=[answer])
    (target / "problem.json").write_text(json.dumps(demo_model(), indent=2) + "\n")
    (target / "PROVENANCE.txt").write_text(
        "Original MazeProof synthetic 4x4 snake, MIT, deterministic; no product or private data.\nPDF: problem page 1, solution page 2.\n"
    )
    print("Created synthetic PNG/JPEG/PDF/JSON samples.")


if __name__ == "__main__":
    main()
