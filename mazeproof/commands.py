"""Image/project CLI, sharing the same review state as the browser."""

import argparse
import base64
import json
import sys

from . import core
from .cli import EXIT_CODES, InputError, read_file
from .workspace import Workspace


def inspect_main(argv=None):
    parser = argparse.ArgumentParser(
        description="Inspect local image/PDF. Output remains NEEDS_REVIEW until a human reviews it in the UI."
    )
    parser.add_argument("problem")
    parser.add_argument("--solution")
    parser.add_argument("--problem-page", type=int)
    parser.add_argument("--solution-page", type=int)
    parser.add_argument(
        "--settings",
        help="JSON object keyed by problem/solution, with geometry and/or rotation",
    )
    parser.add_argument(
        "--reference",
        help="Exact problem structure JSON to compare with rendered appearance",
    )
    parser.add_argument("--allow-multiple", action="store_true")
    parser.add_argument(
        "--save-project",
        help="Write an editable project to a NEW file; never overwrites",
    )
    args = parser.parse_args(argv)
    try:
        settings = core._decode(read_file(args.settings))[0] if args.settings else {}
        core._keys(settings, (), ("problem", "solution"))
        sources = {}
        for role in ("problem", "solution"):
            path = getattr(args, role)
            if path is None:
                continue
            option = settings.get(role, {})
            core._keys(option, (), ("geometry", "rotation"))
            from pathlib import Path

            sources[role] = {
                "name": Path(path).name,
                "data": base64.b64encode(read_file(path)).decode(),
                **option,
            }
            page = getattr(args, role + "_page")
            if page is not None:
                sources[role]["page"] = page
        reference = (
            core._decode(read_file(args.reference))[0] if args.reference else None
        )
        workspace = Workspace(sources, reference)
        workspace.unique_required = not args.allow_multiple
        result = workspace.evaluate()
        if args.save_project:
            with open(args.save_project, "x", encoding="utf-8") as stream:
                json.dump(
                    workspace.export(), stream, ensure_ascii=True, allow_nan=False
                )
    except (InputError, core.Rejected) as error:
        result = core.error_result(
            error.status,
            getattr(error, "code", getattr(error, "reason", "INPUT_REJECTED")),
        )
    except FileExistsError:
        result = core.error_result("INVALID_INPUT", "OUTPUT_ALREADY_EXISTS")
    except Exception:
        result = core.error_result("ERROR", "INSPECT_FAILED")
    sys.stdout.write(
        json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    )
    return EXIT_CODES[result["overallStatus"]]
