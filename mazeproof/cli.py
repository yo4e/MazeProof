"""A thin local file adapter over the same structure verification core."""
import argparse
import json
import os
import stat
import sys

from . import core

EXIT_CODES = {"PASS": 0, "FAIL": 1, "NEEDS_REVIEW": 2,
              "INVALID_INPUT": 3, "UNSUPPORTED": 3, "RESOURCE_LIMIT": 3, "ERROR": 3}


class InputError(Exception):
    def __init__(self, status, reason):
        self.status, self.reason = status, reason


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's message may contain private filenames or payload fragments.
        self.print_usage(sys.stderr)
        raise InputError("INVALID_INPUT", "CLI_ARGUMENTS")


def read_file(path):
    """Bounded read from an opened regular file; FIFO/device/URL not accepted."""
    if "://" in path or path.startswith(("//", "\\\\")):
        raise InputError("INVALID_INPUT", "LOCAL_FILE_REQUIRED")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise InputError("INVALID_INPUT", "REGULAR_FILE_REQUIRED")
            if metadata.st_size > core.MAX_BYTES:
                raise InputError("RESOURCE_LIMIT", "BYTE_LIMIT")
            # fstat checks the actual opened object, rather than a raced path.
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = None
                data = stream.read(core.MAX_BYTES + 1)
            if len(data) > core.MAX_BYTES:
                raise InputError("RESOURCE_LIMIT", "BYTE_LIMIT")
            return data
        finally:
            if descriptor is not None:
                os.close(descriptor)
    except (OSError, ValueError):
        raise InputError("INVALID_INPUT", "FILE_READ_ERROR") from None


def _render_text(result):
    lines = [result["overallStatus"] + " (exact_structure; structured JSON only)"]
    for name, check in result["checks"].items():
        lines.append("{}: {} ({})".format(name, check["status"], check["reasonCode"]))
    for issue in result["issues"]:
        where = "" if issue["coordinates"] is None else " " + json.dumps(issue["coordinates"], ensure_ascii=True)
        lines.append("issue: " + issue["reasonCode"] + where)
    lines.append("not checked: " + ", ".join(result["scope"]["notChecked"]))
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = Parser(prog="mazeproof", description="Validate local structured maze JSON; images/PDF are unsupported.")
    parser.add_argument("problem", help="Local problem JSON file; may contain a route if --solution is omitted")
    parser.add_argument("--solution", help="Local complete solution maze JSON with route")
    parser.add_argument("--allow-multiple", action="store_true", help="Allow multiple paths; still require reachability and a valid supplied route")
    parser.add_argument("--format", choices=("json", "text"), default="json", help="Output format (default: JSON result schema)")
    arguments = None
    try:
        arguments = parser.parse_args(argv)
        problem = read_file(arguments.problem)
        solution = read_file(arguments.solution) if arguments.solution is not None else None
        result = core.validate_structure(problem, solution, unique_required=not arguments.allow_multiple)
    except InputError as error:
        unique_required = arguments is None or not arguments.allow_multiple
        result = core.error_result(error.status, error.reason, unique_required=unique_required)
    except Exception:
        result = core.error_result("ERROR", "CLI_INTERNAL_ERROR",
                                   unique_required=arguments is None or not arguments.allow_multiple)
    try:
        if arguments is not None and arguments.format == "text":
            sys.stdout.write(_render_text(result))
        else:
            sys.stdout.write(json.dumps(result, ensure_ascii=True, allow_nan=False, indent=2) + "\n")
    except (BrokenPipeError, OSError):
        # A closed/unwritable output stream cannot carry a result. No traceback.
        return 3
    return EXIT_CODES[result["overallStatus"]]
