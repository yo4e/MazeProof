"""Image/project CLI, sharing the same review state as the browser."""

import base64
import json
import sys

from . import core
from .cli import EXIT_CODES, InputError, Parser, read_file
from .workspace import Workspace, project_json


def inspect_main(argv=None):
    parser = Parser(
        prog="mazeproof inspect",
        description="Inspect local image/PDF. Output remains NEEDS_REVIEW until a human reviews it in the UI.",
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
    unique_required = True
    try:
        args = parser.parse_args(argv)
        unique_required = not args.allow_multiple
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
        workspace.unique_required = unique_required
        result = workspace.evaluate()
        if args.save_project:
            # Validate the complete saved document before creating a file.
            text = project_json(workspace.export())
            with open(args.save_project, "x", encoding="utf-8") as stream:
                stream.write(text)
    except (InputError, core.Rejected) as error:
        result = core.error_result(
            error.status,
            getattr(error, "code", getattr(error, "reason", "INPUT_REJECTED")),
            unique_required=unique_required,
        )
    except FileExistsError:
        result = core.error_result(
            "INVALID_INPUT", "OUTPUT_ALREADY_EXISTS", unique_required=unique_required
        )
    except Exception:
        result = core.error_result(
            "ERROR", "INSPECT_FAILED", unique_required=unique_required
        )
    try:
        sys.stdout.write(
            json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
        )
    except (BrokenPipeError, OSError):
        # A closed output stream cannot carry a result; avoid leaking a traceback.
        return 3
    return EXIT_CODES[result["overallStatus"]]
