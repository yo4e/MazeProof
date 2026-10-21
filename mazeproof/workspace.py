"""Review state, bound approvals, and common UI/CLI/MCP image results."""

import base64
import copy
import hashlib
import json
import time

from . import core
from .core import Rejected
from .worker import run

VERSION = "mazeproof.project/1"


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _unpack(source):
    core._keys(source, ("name", "data"), ("page", "geometry", "rotation"))
    if (
        type(source["name"]) is not str
        or len(source["name"]) > 255
        or type(source["data"]) is not str
    ):
        raise Rejected("INVALID_INPUT", "SOURCE_FIELDS")
    if len(source["data"]) > (core.MAX_BYTES + 2) // 3 * 4:
        raise Rejected("RESOURCE_LIMIT", "BYTE_LIMIT")
    try:
        data = base64.b64decode(source["data"], validate=True)
    except (ValueError, TypeError):
        raise Rejected("INVALID_INPUT", "BASE64_REQUIRED") from None
    return data


def inspect_sources(sources):
    core._keys(sources, ("problem",), ("solution",))
    inspected = {}
    deadline = time.monotonic() + 30
    for role, source in sources.items():
        data = _unpack(source)
        inspected[role] = run(
            "inspect",
            {
                "data": data,
                "name": source["name"],
                "answer": role == "solution",
                "page": source.get("page"),
                "geometry": source.get("geometry"),
                "rotation": source.get("rotation", 0),
            },
            seconds=max(0, deadline - time.monotonic()),
        )
    return inspected


class Workspace:
    def __init__(self, sources, reference=None):
        self.sources = copy.deepcopy(sources)
        self.observations = inspect_sources(sources)
        if reference is not None:
            parsed, _ = core._decode(canonical(reference))
            core._parse(parsed)
        self.reference = copy.deepcopy(reference)
        self.edits = {
            role: {
                "model": copy.deepcopy(obs["model"]),
                "resolved": [],
                "routeReviewed": not obs["routeUncertain"],
            }
            for role, obs in self.observations.items()
        }
        self.unique_required = True
        self.approved_digest = None
        self.revision = 0

    def snapshot(self):
        return {
            "observations": self.observations,
            "edits": self.edits,
            "reference": self.reference,
            "uniqueRequired": self.unique_required,
            "revision": self.revision,
            "digest": self.digest(),
            "approved": self.approved_digest == self.digest(),
        }

    def digest(self):
        return fingerprint(
            {
                "observations": {
                    role: {k: v for k, v in obs.items() if k != "image"}
                    for role, obs in self.observations.items()
                },
                "edits": self.edits,
                "reference": self.reference,
                "policy": self.unique_required,
            }
        )

    def set_edits(self, edits, unique_required, *, revoke_approval=False):
        core._keys(edits, tuple(self.edits))
        if type(unique_required) is not bool:
            raise Rejected("INVALID_INPUT", "POLICY_TYPE")
        if type(revoke_approval) is not bool:
            raise Rejected("INVALID_INPUT", "APPROVAL_REVOCATION_TYPE")
        # Allow semantically invalid edits (e.g. an extra opening), but bound shape
        # and types. The verifier explains the exact repair needed.
        for role, edit in edits.items():
            core._keys(edit, ("model", "resolved", "routeReviewed"))
            model = edit["model"]
            core._keys(
                model,
                (
                    "schemaVersion",
                    "width",
                    "height",
                    "horizontalWalls",
                    "verticalWalls",
                    "entrance",
                    "exit",
                ),
                ("route",),
            )
            original = self.observations[role]["model"]
            if any(
                model[k] != original[k] for k in ("schemaVersion", "width", "height")
            ):
                raise Rejected("INVALID_INPUT", "REANALYZE_TO_CHANGE_GRID")
            for field in ("horizontalWalls", "verticalWalls"):
                if type(model[field]) is not list or len(model[field]) != len(
                    original[field]
                ):
                    raise Rejected("INVALID_INPUT", "WALL_SHAPE")
                for row, expected in zip(model[field], original[field]):
                    if (
                        type(row) is not list
                        or len(row) != len(expected)
                        or any(type(x) is not bool for x in row)
                    ):
                        raise Rejected("INVALID_INPUT", "WALL_SHAPE")
            for endpoint in ("entrance", "exit"):
                point = model[endpoint]
                core._keys(point, ("row", "col", "side"))
                core._cell(
                    {"row": point["row"], "col": point["col"]},
                    model["width"],
                    model["height"],
                )
                if point["side"] not in ("N", "S", "E", "W"):
                    raise Rejected("INVALID_INPUT", "ENDPOINT_SIDE")
            if "route" in model:
                if (
                    type(model["route"]) is not list
                    or len(model["route"]) > model["width"] * model["height"]
                ):
                    raise Rejected("INVALID_INPUT", "ROUTE_LIMIT")
                for point in model["route"]:
                    core._cell(point, model["width"], model["height"])
            known = {u["id"] for u in self.observations[role]["unknowns"]}
            if type(edit["resolved"]) is not list or any(
                type(x) is not str or x not in known for x in edit["resolved"]
            ):
                raise Rejected("INVALID_INPUT", "UNKNOWN_RESOLUTION")
            if type(edit["routeReviewed"]) is not bool:
                raise Rejected("INVALID_INPUT", "ROUTE_REVIEW_TYPE")
        # A client edit followed by undo can produce the same model. Its human
        # confirmation is still invalidated; a digest comparison cannot see it.
        if revoke_approval:
            self.approved_digest = None
        if (
            canonical(edits) != canonical(self.edits)
            or unique_required != self.unique_required
        ):
            self.edits = copy.deepcopy(edits)
            self.unique_required = unique_required
            self.approved_digest = None
            self.revision += 1

    def pending(self):
        pending = []
        for role, obs in self.observations.items():
            resolved = self.edits[role]["resolved"]
            pending.extend(
                {"source": role, **item}
                for item in obs["unknowns"]
                if item["id"] not in resolved
            )
            if not self.edits[role]["routeReviewed"]:
                pending.append(
                    {"source": role, "id": "route", "reason": "RED_ROUTE_UNCERTAIN"}
                )
        return pending

    def evaluate(self, *, approve=False):
        models = {role: edit["model"] for role, edit in self.edits.items()}
        result = core.validate_structure(
            canonical(models["problem"]),
            canonical(models["solution"]) if "solution" in models else None,
            unique_required=self.unique_required,
        )
        pending = self.pending()
        if approve:
            if pending:
                raise Rejected("INVALID_INPUT", "UNRESOLVED_OBSERVATIONS")
            if result["overallStatus"] not in ("PASS", "FAIL"):
                raise Rejected("INVALID_INPUT", "FIX_MODEL_BEFORE_APPROVAL")
            self.approved_digest = self.digest()
        confirmed = self.approved_digest == self.digest()
        assurance = "human_confirmed" if confirmed else "recognized_unconfirmed"
        result["engineVersion"] = "0.2.0"
        result["inputDigests"] = {
            role: obs["digest"] for role, obs in self.observations.items()
        }
        result["transforms"] = [
            {"source": role, **obs["transform"], "grid": obs["geometry"]}
            for role, obs in self.observations.items()
        ]
        pdf_pages = {
            role: obs["transform"]["page"]
            for role, obs in self.observations.items()
            if obs["transform"]["format"] == "PDF"
        }
        result["pagePairs"] = [pdf_pages] if pdf_pages else []
        result["recognition"] = {
            "status": "CONFIRMED" if confirmed else "NEEDS_REVIEW",
            "assurance": assurance,
            "modelDigest": self.digest(),
            "pending": pending,
            "statement": "Conclusion applies to the reviewed model, not a proof of source pixels.",
            "referenceDigest": fingerprint(self.reference) if self.reference else None,
        }
        result["limits"].update(
            maxPixels=20_000_000,
            maxPages=20,
            maxMemoryBytes=512 * 1024 * 1024,
            maxSeconds=60,
            maxAdapterSeconds=30,
        )
        result["evidence"]["recognitionEdits"] = self.edits
        result["evidence"]["observations"] = {
            role: {
                key: value for key, value in obs.items() if key not in ("image", "name")
            }
            for role, obs in self.observations.items()
        }
        if self.reference is not None and result["overallStatus"] in ("PASS", "FAIL"):
            # Compare independently supplied JSON to the reviewed rendered model.
            differences = []
            for field in (
                "width",
                "height",
                "entrance",
                "exit",
                "horizontalWalls",
                "verticalWalls",
            ):
                a, b = self.reference[field], models["problem"][field]
                if a != b:
                    if field.endswith("Walls") and (
                        self.reference["width"],
                        self.reference["height"],
                    ) == (models["problem"]["width"], models["problem"]["height"]):
                        differences.extend(
                            {"field": field, "row": r, "col": c}
                            for r, row in enumerate(a)
                            for c, value in enumerate(row)
                            if value != b[r][c]
                        )
                    else:
                        differences.append({"field": field})
            result["checks"]["renderedAgreement"] = core._check(
                "FAIL" if differences else "PASS",
                "RENDERED_MISMATCH" if differences else "RENDERED_AGREEMENT",
                ["problem"],
                differences or None,
            )
            result["evidence"]["renderedDifferences"] = differences
            result["evidence"]["referenceResult"] = core.validate_structure(
                canonical(self.reference), unique_required=self.unique_required
            )
            if differences:
                result["overallStatus"] = "FAIL"
                result["issues"].append(
                    {
                        "check": "renderedAgreement",
                        "reasonCode": "RENDERED_MISMATCH",
                        "coordinates": differences,
                    }
                )
        if self.reference is None and result["overallStatus"] in ("PASS", "FAIL"):
            result["checks"]["renderedAgreement"] = core._check(
                "NOT_RUN", "NO_REFERENCE_STRUCTURE", []
            )
        result["evidence"]["provisionalStatus"] = result["overallStatus"]
        for check in result["checks"].values():
            check["assurance"] = assurance
        if not confirmed and result["overallStatus"] in (
            "PASS",
            "FAIL",
            "INVALID_INPUT",
        ):
            result["overallStatus"] = "NEEDS_REVIEW"
            result["issues"].append(
                {
                    "check": None,
                    "reasonCode": "HUMAN_REVIEW_REQUIRED",
                    "coordinates": None,
                }
            )
        result["scope"] = {
            "checked": [
                k for k, c in result["checks"].items() if c["status"] != "NOT_RUN"
            ],
            "notChecked": [
                k for k, c in result["checks"].items() if c["status"] == "NOT_RUN"
            ],
        }
        return result

    def export(self):
        return {
            "schemaVersion": VERSION,
            "sources": self.sources,
            "reference": self.reference,
            "edits": self.edits,
            "uniqueRequired": self.unique_required,
            "result": self.evaluate(),
            "notice": "Reopening always requires fresh human confirmation. Originals are embedded.",
        }

    @classmethod
    def restore(cls, project):
        core._keys(
            project,
            (
                "schemaVersion",
                "sources",
                "reference",
                "edits",
                "uniqueRequired",
                "result",
                "notice",
            ),
        )
        if project["schemaVersion"] != VERSION:
            raise Rejected("INVALID_INPUT", "PROJECT_VERSION")
        workspace = cls(project["sources"], project["reference"])
        workspace.set_edits(project["edits"], project["uniqueRequired"])
        return workspace
