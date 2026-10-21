"""Independent, synthetic fault corpus for recognition and review gates."""

import base64
import copy
import io
import json
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
from mazeproof import core
from mazeproof.imaging import decode, inspect, recognize
from mazeproof.samples import demo_model, demo_route, render, demo_sources
from mazeproof.workspace import Workspace


def encoded(image, fmt="PNG", **options):
    out = io.BytesIO()
    image.save(out, fmt, **options)
    return out.getvalue()


def local_workspace(sources=None, reference=None):
    # Recognition tests run in-process; separate worker tests verify isolation.
    from mazeproof.imaging import inspect as inspect_direct

    with patch(
        "mazeproof.workspace.run",
        side_effect=lambda op, args, **kwargs: inspect_direct(**args),
    ):
        return Workspace(sources or demo_sources(), reference)


def approve(workspace):
    for role, obs in workspace.observations.items():
        workspace.edits[role]["resolved"] = [u["id"] for u in obs["unknowns"]]
        workspace.edits[role]["routeReviewed"] = True
    return workspace.evaluate(approve=True)


class ImagingTests(unittest.TestCase):
    def test_clean_and_jpeg_geometry_and_exact_walls(self):
        model = demo_model()
        for fmt, options in [
            ("PNG", {}),
            ("JPEG", {"quality": 95}),
            ("JPEG", {"quality": 60}),
        ]:
            with self.subTest(fmt=fmt, options=options):
                item = inspect(
                    encoded(render(model), fmt, **options),
                    "test." + ("png" if fmt == "PNG" else "jpg"),
                )
                self.assertEqual(item["model"], model)
                self.assertEqual(item["geometry"]["cols"], 4)
                self.assertEqual(item["geometry"]["rows"], 4)
                self.assertIn("HUMAN_REVIEW_REQUIRED", item["notices"])

    def test_red_route_and_occlusion_not_copied_from_problem(self):
        answer = inspect(
            encoded(render(demo_model(), demo_route())), "answer.png", answer=True
        )
        self.assertEqual(answer["model"]["route"], demo_route())
        self.assertFalse(answer["routeUncertain"])
        self.assertEqual(len(answer["unknowns"]), 15)
        self.assertTrue(all(u["reason"] == "RED_OCCLUSION" for u in answer["unknowns"]))

    def test_partial_faint_and_broken_walls_are_unknown(self):
        for shade in (110, 160, 220):
            image = render(demo_model())
            ImageDraw.Draw(image).line(
                (96, 168, 130, 168), fill=(shade, shade, shade), width=7
            )
            observed = recognize(
                image, {"x0": 24, "y0": 24, "x1": 312, "y1": 312, "cols": 4, "rows": 4}
            )
            self.assertIn(
                "horizontalWalls:2:1", [u["id"] for u in observed["unknowns"]]
            )

    def test_red_disconnection_branch_diagonal_and_extra_marks(self):
        original = render(demo_model(), demo_route())
        variants = []
        tiny_gap = original.copy()
        ImageDraw.Draw(tiny_gap).rectangle((96, 52, 96, 68), fill="white")
        variants.append(tiny_gap)
        broken = original.copy()
        ImageDraw.Draw(broken).rectangle((90, 52, 103, 68), fill="white")
        variants.append(broken)
        branch = original.copy()
        ImageDraw.Draw(branch).line((132, 60, 132, 132), fill=(230, 20, 20), width=5)
        variants.append(branch)
        diagonal = render(demo_model())
        ImageDraw.Draw(diagonal).line((60, 60, 276, 276), fill=(230, 20, 20), width=5)
        variants.append(diagonal)
        extra = original.copy()
        ImageDraw.Draw(extra).line((150, 95, 170, 110), fill=(230, 20, 20), width=5)
        variants.append(extra)
        for image in variants:
            self.assertTrue(
                recognize(
                    image,
                    {"x0": 24, "y0": 24, "x1": 312, "y1": 312, "cols": 4, "rows": 4},
                    answer=True,
                )["routeUncertain"]
            )

    def test_alpha_exif_and_manual_rotation_recorded(self):
        image = render(demo_model()).convert("RGBA")
        image.putpixel((0, 0), (0, 0, 0, 0))
        decoded, meta = decode(encoded(image), "test.png")
        self.assertEqual(decoded.getpixel((0, 0)), (255, 255, 255))
        self.assertTrue(meta["alphaComposited"])
        jpeg = render(demo_model())
        exif = Image.Exif()
        exif[274] = 6
        _, meta = decode(encoded(jpeg, "JPEG", exif=exif), "test.jpg")
        self.assertEqual(meta["exifOrientation"], 6)
        item = inspect(encoded(render(demo_model())), "test.png", rotation=90)
        self.assertEqual(item["transform"]["userRotation"], 90)

    def test_reject_format_magic_page_crop_and_pixels(self):
        data = encoded(render(demo_model()))
        cases = [
            lambda: decode(data, "x.jpg"),
            lambda: decode(data, "x.png", 1),
            lambda: decode(b"<svg/>", "x.png"),
            lambda: inspect(data, "x.png", rotation=45),
            lambda: inspect(
                data,
                "x.png",
                geometry={"x0": 0, "y0": 0, "x1": 10, "y1": 10, "cols": 4, "rows": 4},
            ),
            lambda: inspect(
                data,
                "x.png",
                geometry={
                    "x0": -1,
                    "y0": 0,
                    "x1": 312,
                    "y1": 312,
                    "cols": 4,
                    "rows": 4,
                },
            ),
        ]
        for fn in cases:
            with self.assertRaises(core.Rejected):
                fn()
        with patch("mazeproof.imaging.MAX_PIXELS", 100):
            with self.assertRaises(core.Rejected) as caught:
                decode(data, "x.png")
        self.assertEqual(caught.exception.status, "RESOURCE_LIMIT")
        animated = io.BytesIO()
        render(demo_model()).save(
            animated,
            "PNG",
            save_all=True,
            append_images=[Image.new("RGB", (337, 337), "red")],
            duration=100,
        )
        with self.assertRaises(core.Rejected):
            decode(animated.getvalue(), "x.png")

    def test_pdf_explicit_page_and_rendered_scope(self):
        pdf = encoded(render(demo_model()), "PDF")
        image, meta = decode(pdf, "x.pdf", 1)
        self.assertEqual(meta["page"], 1)
        self.assertEqual(meta["pdfMode"], "rendered_appearance_only")
        self.assertEqual(meta["vectorAgreement"], "NOT_RUN")
        for page in (None, 0, 2, True):
            with self.assertRaises(core.Rejected):
                decode(pdf, "x.pdf", page)
        with self.assertRaises(core.Rejected):
            decode(b"%PDF-broken", "x.pdf", 1)

    def test_every_unconfirmed_corpus_case_is_needs_review(self):
        base = render(demo_model())
        images = [
            base,
            base.resize((168, 168)),
            base.rotate(2, fillcolor="white"),
            base.convert("RGBA"),
        ]
        for quality in (10, 40, 80):
            images.append(
                Image.open(io.BytesIO(encoded(base, "JPEG", quality=quality)))
            )
        for image in images:
            sources = {
                "problem": {
                    "name": "case.png",
                    "data": base64.b64encode(encoded(image)).decode(),
                }
            }
            workspace = local_workspace(sources)
            result = workspace.evaluate()
            self.assertEqual(result["overallStatus"], "NEEDS_REVIEW")
            self.assertEqual(
                result["recognition"]["assurance"], "recognized_unconfirmed"
            )

    def test_approval_bound_to_edits_policy_and_restoration(self):
        workspace = local_workspace()
        before = workspace.evaluate()
        self.assertEqual(before["overallStatus"], "NEEDS_REVIEW")
        with self.assertRaises(core.Rejected):
            workspace.evaluate(approve=True)
        confirmed = approve(workspace)
        self.assertEqual(confirmed["overallStatus"], "PASS")
        self.assertEqual(confirmed["recognition"]["assurance"], "human_confirmed")
        project = workspace.export()
        with patch(
            "mazeproof.workspace.run",
            side_effect=lambda op, args, **kwargs: inspect(**args),
        ):
            restored = Workspace.restore(project)
        self.assertEqual(restored.evaluate()["overallStatus"], "NEEDS_REVIEW")
        edits = copy.deepcopy(workspace.edits)
        edits["problem"]["model"]["verticalWalls"][0][1] = True
        workspace.set_edits(edits, True)
        result = workspace.evaluate()
        self.assertEqual(result["overallStatus"], "NEEDS_REVIEW")
        self.assertEqual(result["checks"]["reachability"]["status"], "FAIL")
        self.assertEqual(workspace.evaluate(approve=True)["overallStatus"], "FAIL")
        workspace.set_edits(workspace.edits, False)
        self.assertEqual(workspace.evaluate()["overallStatus"], "NEEDS_REVIEW")

    def test_pair_mismatch_and_wall_crossing_with_independent_observations(self):
        sources = demo_sources()
        model = demo_model()
        model["horizontalWalls"][1][1] = False
        sources["solution"]["data"] = base64.b64encode(
            encoded(render(model, demo_route()))
        ).decode()
        workspace = local_workspace(sources)
        result = approve(workspace)
        self.assertEqual(result["overallStatus"], "FAIL")
        self.assertEqual(result["checks"]["mazeIdentity"]["status"], "FAIL")
        self.assertIn(
            {"field": "horizontalWalls", "row": 1, "col": 1},
            result["evidence"]["mazeDifferences"],
        )
        workspace = local_workspace()
        edit = copy.deepcopy(workspace.edits)
        edit["solution"]["model"]["route"] = [
            {"row": 0, "col": 0},
            {"row": 1, "col": 0},
            {"row": 2, "col": 0},
            {"row": 3, "col": 0},
        ]
        workspace.set_edits(edit, True)
        self.assertEqual(
            approve(workspace)["checks"]["routeValidity"]["reasonCode"],
            "ROUTE_WALL_CROSSING",
        )

    def test_reference_agreement_missing_wall_cannot_borrow_json_pass(self):
        reference = demo_model()
        workspace = local_workspace(reference=reference)
        self.assertEqual(
            approve(workspace)["checks"]["renderedAgreement"]["status"], "PASS"
        )
        model = demo_model()
        model["horizontalWalls"][1][1] = False
        sources = {
            "problem": {
                "name": "render.png",
                "data": base64.b64encode(encoded(render(model))).decode(),
            }
        }
        workspace = local_workspace(sources, reference)
        result = approve(workspace)
        self.assertEqual(result["overallStatus"], "FAIL")
        self.assertEqual(result["checks"]["renderedAgreement"]["status"], "FAIL")
        self.assertEqual(result["evidence"]["referenceResult"]["overallStatus"], "PASS")

    def test_result_schema_for_all_review_states(self):
        import jsonschema
        from pathlib import Path

        schema = json.loads(
            (
                Path(__file__).resolve().parents[1] / "schemas/result.schema.json"
            ).read_text()
        )
        workspace = local_workspace()
        for result in (
            workspace.evaluate(),
            approve(workspace),
            core.error_result("ERROR", "TEST"),
        ):
            jsonschema.validate(result, schema)

    def test_failed_auto_grid_still_opens_for_manual_review(self):
        item = inspect(encoded(Image.new("RGB", (16, 16), "white")), "blank.png")
        self.assertIn("GRID_ESTIMATE_UNCERTAIN", item["notices"])
        self.assertEqual(item["geometry"]["cols"], 1)

    def test_invalid_edit_and_injection_never_approved(self):
        workspace = local_workspace()
        for mutation in ("shape", "extra", "resolve", "route"):
            edits = copy.deepcopy(workspace.edits)
            if mutation == "shape":
                edits["problem"]["model"]["horizontalWalls"][0] = [1]
            if mutation == "extra":
                edits["problem"]["model"]["unexpected"] = True
            if mutation == "resolve":
                edits["problem"]["resolved"] = ["fake"]
            if mutation == "route":
                edits["solution"]["model"]["route"] = [{"row": 100, "col": 0}]
            with self.assertRaises(core.Rejected):
                workspace.set_edits(edits, True)
        edits = copy.deepcopy(workspace.edits)
        edits["problem"]["model"]["horizontalWalls"][0][1] = False
        workspace.set_edits(edits, True)
        for role, obs in workspace.observations.items():
            workspace.edits[role]["resolved"] = [u["id"] for u in obs["unknowns"]]
        with self.assertRaises(core.Rejected):
            workspace.evaluate(approve=True)
        self.assertIsNone(workspace.approved_digest)


class PdfBoundsTests(unittest.TestCase):
    def test_vector_rotation_and_metadata(self):
        from pdf_fixture import pdf_bytes

        image, meta = decode(
            pdf_bytes(width=337, height=250, rotation=90), "vector.pdf", 1
        )
        self.assertEqual(meta["rotation"], 90)
        self.assertEqual(meta["pageSize"], [250.0, 337.0])
        self.assertEqual(list(image.size), [500, 674])
        self.assertEqual(meta["vectorAgreement"], "NOT_RUN")

    def test_pdf_limits_and_active_content(self):
        from pdf_fixture import pdf_bytes

        for kwargs, code in [
            ({"pages": 21}, "PDF_PAGE_LIMIT"),
            ({"width": 100000}, "PIXEL_LIMIT"),
            ({"javascript": True}, "PDF_DOCUMENT_JAVASCRIPT"),
            ({"attachment": True}, "PDF_ATTACHMENTS"),
        ]:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(core.Rejected) as caught:
                    decode(pdf_bytes(**kwargs), "test.pdf", 1)
                self.assertEqual(caught.exception.code, code)

    def test_empty_password_encryption_flag_rejected(self):
        from pdf_fixture import pdf_bytes

        with patch("pypdfium2.raw.FPDF_GetSecurityHandlerRevision", return_value=4):
            with self.assertRaises(core.Rejected) as caught:
                decode(pdf_bytes(), "encrypted.pdf", 1)
        self.assertEqual(caught.exception.code, "ENCRYPTED_PDF")
