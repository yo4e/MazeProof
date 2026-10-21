"""Shared image inspection for the UI queue and read-only MCP batch calls."""

import time
import uuid

from . import core
from .workspace import Workspace, canonical

MAX_ITEMS = 100
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_BATCH_SECONDS = 60


def inspect_item(item):
    """Return an unapproved workspace; never trust saved result/approval fields."""
    if type(item) is dict and "project" in item:
        core._keys(item, ("project",))
        return Workspace.restore(item["project"])
    core._keys(item, ("sources",), ("reference", "uniqueRequired"))
    policy = item.get("uniqueRequired", True)
    if type(policy) is not bool:
        raise core.Rejected("INVALID_INPUT", "POLICY_TYPE")
    workspace = Workspace(item["sources"], item.get("reference"))
    workspace.unique_required = policy
    return workspace


def inspect_many(items, load_item):
    """Process explicit items independently; leave a resumable tail on limits.

    The time budget is checked between items. Each active item retains the
    existing worker/core budgets; its call is allowed to finish.
    """
    if type(items) is not list or not 1 <= len(items) <= MAX_ITEMS:
        raise core.Rejected("INVALID_INPUT", "BATCH_ITEM_LIMIT")
    ids = []
    for item in items:
        if (
            type(item) is not dict
            or type(item.get("id")) is not str
            or not 1 <= len(item["id"]) <= 128
            or item["id"] in ids
        ):
            raise core.Rejected("INVALID_INPUT", "BATCH_ITEM_ID")
        ids.append(item["id"])
    deadline = time.monotonic() + MAX_BATCH_SECONDS
    output = []
    output_bytes = 0
    stop_reason = None
    for item in items:
        if stop_reason or time.monotonic() >= deadline:
            stop_reason = stop_reason or "BATCH_TIME_LIMIT"
            output.append({"id": item["id"], "state": "QUEUED", "reason": stop_reason})
            continue
        try:
            workspace = inspect_item(load_item(item))
            result = workspace.evaluate()
        except core.Rejected as error:
            result = core.error_result(error.status, error.code)
        except Exception:
            result = core.error_result("ERROR", "BATCH_ITEM_FAILED")
        row = {
            "id": item["id"],
            "state": "ERROR"
            if result["overallStatus"]
            in ("ERROR", "INVALID_INPUT", "UNSUPPORTED", "RESOURCE_LIMIT")
            else "NEEDS_REVIEW",
            "result": result,
        }
        size = len(canonical(row).encode())
        if size > MAX_RESULT_BYTES:
            row = {
                "id": item["id"],
                "state": "ERROR",
                "result": core.error_result("RESOURCE_LIMIT", "BATCH_RESULT_LIMIT"),
            }
            size = len(canonical(row).encode())
        if output_bytes + size > MAX_RESULT_BYTES:
            stop_reason = "BATCH_RESULT_LIMIT"
            output.append({"id": item["id"], "state": "QUEUED", "reason": stop_reason})
            continue
        output.append(row)
        output_bytes += size
    counts = {
        state: sum(row["state"] == state for row in output)
        for state in ("NEEDS_REVIEW", "ERROR", "QUEUED")
    }
    return {
        "schemaVersion": "mazeproof.batch-result/1",
        "requestId": str(uuid.uuid4()),
        "overallStatus": "ERROR" if counts["ERROR"] == len(output) else "NEEDS_REVIEW",
        "counts": counts,
        "items": output,
        "limits": {
            "maxItems": MAX_ITEMS,
            "betweenItemSeconds": MAX_BATCH_SECONDS,
            "maxResultBytes": MAX_RESULT_BYTES,
        },
        "notice": "Images are never approved by this operation. Resubmit QUEUED IDs with their original inputs.",
    }
