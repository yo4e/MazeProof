"""Conservative raster observations. Never grants human confirmation."""

import base64
import hashlib
import io
import math
import warnings
from pathlib import PurePath

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .core import MAX_BYTES, MAX_DIMENSION, Rejected

MAX_PIXELS = 20_000_000
MAX_PAGES = 20
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def reject(code, status="INVALID_INPUT"):
    raise Rejected(status, code)


def png_data(image):
    stream = io.BytesIO()
    image.save(stream, "PNG")
    return base64.b64encode(stream.getvalue()).decode("ascii")


def decode(data, name, page=None):
    """Decode without executing PDF actions or initializing its form environment."""
    if not isinstance(data, bytes) or len(data) > MAX_BYTES:
        reject("BYTE_LIMIT", "RESOURCE_LIMIT")
    suffix = PurePath(name).suffix.lower()
    meta = {"sourceDigest": hashlib.sha256(data).hexdigest(), "whiteBackground": True}
    if data.startswith(b"%PDF-"):
        if suffix != ".pdf":
            reject("FORMAT_MISMATCH")
        if type(page) is not int or page < 1:
            reject("EXPLICIT_PDF_PAGE_REQUIRED")
        import pypdfium2 as pdfium

        try:
            with pdfium.PdfDocument(data) as doc:
                count = len(doc)
                if count > MAX_PAGES:
                    reject("PDF_PAGE_LIMIT", "RESOURCE_LIMIT")
                if page > count:
                    reject("PDF_PAGE_RANGE")
                # Password-protected PDFs (including empty-user-password files)
                # are outside the supported profile.
                if pdfium.raw.FPDF_GetSecurityHandlerRevision(doc) >= 0:
                    reject("ENCRYPTED_PDF", "UNSUPPORTED")
                if pdfium.raw.FPDFDoc_GetJavaScriptActionCount(doc) > 0:
                    reject("PDF_DOCUMENT_JAVASCRIPT", "UNSUPPORTED")
                if pdfium.raw.FPDFDoc_GetAttachmentCount(doc) > 0:
                    reject("PDF_ATTACHMENTS", "UNSUPPORTED")
                sheet = doc[page - 1]
                try:
                    width, height = sheet.get_size()
                    scale = 2.0  # explicit 144 DPI; no silent downsampling
                    if not all(math.isfinite(v) and v > 0 for v in (width, height)):
                        reject("PDF_PAGE_SIZE")
                    if (
                        math.ceil(width * scale) * math.ceil(height * scale)
                        > MAX_PIXELS
                    ):
                        reject("PIXEL_LIMIT", "RESOURCE_LIMIT")
                    meta.update(
                        format="PDF",
                        page=page,
                        pageCount=count,
                        dpi=144,
                        pageSize=[width, height],
                        rotation=sheet.get_rotation(),
                        cropBox=list(sheet.get_cropbox()),
                        pdfMode="rendered_appearance_only",
                        vectorAgreement="NOT_RUN",
                        actions="not_executed",
                    )
                    bitmap = sheet.render(scale=scale)
                    try:
                        image = bitmap.to_pil().convert("RGB")
                    finally:
                        bitmap.close()
                finally:
                    sheet.close()
        except Rejected:
            raise
        except Exception:
            reject("PDF_DECODE_FAILED", "UNSUPPORTED")
    else:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            expected, extensions = "PNG", (".png",)
        elif data.startswith(b"\xff\xd8\xff"):
            expected, extensions = "JPEG", (".jpg", ".jpeg")
        else:
            reject("PNG_JPEG_PDF_REQUIRED", "UNSUPPORTED")
        if suffix not in extensions or page is not None:
            reject(
                "FORMAT_MISMATCH" if suffix not in extensions else "PAGE_FOR_NON_PDF"
            )
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data), formats=[expected]) as original:
                    if original.width * original.height > MAX_PIXELS:
                        reject("PIXEL_LIMIT", "RESOURCE_LIMIT")
                    if getattr(original, "n_frames", 1) != 1:
                        reject("ANIMATED_IMAGE", "UNSUPPORTED")
                    orientation = original.getexif().get(274, 1)
                    transparent = (
                        original.mode in ("RGBA", "LA")
                        or "transparency" in original.info
                    )
                    image = ImageOps.exif_transpose(original).convert("RGBA")
                    background = Image.new("RGBA", image.size, "white")
                    image = Image.alpha_composite(background, image).convert("RGB")
                    meta.update(
                        format=expected,
                        exifOrientation=orientation,
                        alphaComposited=transparent,
                    )
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            reject("PIXEL_LIMIT", "RESOURCE_LIMIT")
        except (UnidentifiedImageError, OSError, ValueError):
            reject("IMAGE_DECODE_FAILED")
    if min(image.size) < 16:
        reject("IMAGE_TOO_SMALL", "UNSUPPORTED")
    meta["decodedSize"] = list(image.size)
    return image, meta


def _peaks(values):
    """Contiguous projection peaks, weighted centers; only a grid proposal."""
    top = float(values.max())
    if top == 0:
        return []
    indices = np.flatnonzero(values >= max(5, top * 0.28))
    groups = np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1)
    return [float(np.average(g, weights=values[g])) for g in groups if len(g)]


def _axis_grid(peaks, extent):
    if len(peaks) < 2:
        return 0.0, float(extent - 1), 10, False
    differences = np.diff(peaks)
    pitch = float(np.median(differences))
    count = round((peaks[-1] - peaks[0]) / pitch) if pitch else 0
    regular = (
        count >= 1
        and count <= MAX_DIMENSION
        and pitch >= 8
        and all(abs(v / pitch - round(v / pitch)) < 0.16 for v in differences)
    )
    return peaks[0], peaks[-1], max(1, min(MAX_DIMENSION, count)), bool(regular)


def propose_geometry(image):
    arr = np.asarray(image)
    dark = np.max(arr, axis=2) < 128
    x0, x1, cols, a = _axis_grid(_peaks(dark.sum(axis=0)), image.width)
    y0, y1, rows, b = _axis_grid(_peaks(dark.sum(axis=1)), image.height)
    # A long corridor can contain no walls on one axis. Propose square cells
    # using the other axis, explicitly marking that assumption as uncertain.
    if cols == 1 and rows > 1:
        cols = max(1, min(MAX_DIMENSION, round((x1 - x0) / ((y1 - y0) / rows))))
        a = False
    elif rows == 1 and cols > 1:
        rows = max(1, min(MAX_DIMENSION, round((y1 - y0) / ((x1 - x0) / cols))))
        b = False
    return {
        "x0": round(x0, 2),
        "y0": round(y0, 2),
        "x1": round(x1, 2),
        "y1": round(y1, 2),
        "cols": cols,
        "rows": rows,
    }, a and b


def check_geometry(geometry, image):
    if type(geometry) is not dict or set(geometry) != {
        "x0",
        "y0",
        "x1",
        "y1",
        "cols",
        "rows",
    }:
        reject("GEOMETRY_FIELDS")
    if any(
        type(geometry[k]) is not int or not 1 <= geometry[k] <= MAX_DIMENSION
        for k in ("rows", "cols")
    ):
        reject("GRID_LIMIT", "RESOURCE_LIMIT")
    if any(
        type(geometry[k]) not in (int, float) or not math.isfinite(geometry[k])
        for k in ("x0", "y0", "x1", "y1")
    ):
        reject("GEOMETRY_NUMBER")
    x0, y0, x1, y1 = (geometry[k] for k in ("x0", "y0", "x1", "y1"))
    if not (0 <= x0 < x1 <= image.width - 1 and 0 <= y0 < y1 <= image.height - 1):
        reject("CROP_RANGE")
    if min((x1 - x0) / geometry["cols"], (y1 - y0) / geometry["rows"]) < 8:
        reject("CELL_TOO_SMALL", "UNSUPPORTED")


def _patch(arr, x0, y0, x1, y1):
    height, width = arr.shape[:2]
    return arr[
        max(0, round(y0)) : min(height, round(y1) + 1),
        max(0, round(x0)) : min(width, round(x1) + 1),
    ]


def _openings(model):
    rows, cols = model["height"], model["width"]
    found = []
    for c in range(cols):
        if not model["horizontalWalls"][0][c]:
            found.append({"row": 0, "col": c, "side": "N"})
        if not model["horizontalWalls"][rows][c]:
            found.append({"row": rows - 1, "col": c, "side": "S"})
    for r in range(rows):
        if not model["verticalWalls"][r][0]:
            found.append({"row": r, "col": 0, "side": "W"})
        if not model["verticalWalls"][r][cols]:
            found.append({"row": r, "col": cols - 1, "side": "E"})
    return found


def recognize(image, geometry=None, *, answer=False):
    suggested, regular = propose_geometry(image)
    geom = suggested if geometry is None else geometry
    try:
        check_geometry(geom, image)
    except Rejected:
        if geometry is not None:
            raise
        # Failed estimates must still be editable in the workbench. A bounded
        # full-image grid is only a starting point, never a confirmed model.
        geom = {
            "x0": 0,
            "y0": 0,
            "x1": image.width - 1,
            "y1": image.height - 1,
            "cols": max(1, min(10, (image.width - 1) // 8)),
            "rows": max(1, min(10, (image.height - 1) // 8)),
        }
        regular = False
        check_geometry(geom, image)
    x0, y0, x1, y1, cols, rows = (
        geom[k] for k in ("x0", "y0", "x1", "y1", "cols", "rows")
    )
    dx, dy = (x1 - x0) / cols, (y1 - y0) / rows
    arr = np.asarray(image)
    light = np.max(arr, axis=2)
    # int16 prevents uint8 overflow when comparing red dominance.
    rgb = arr.astype(np.int16)
    red = (
        (rgb[:, :, 0] > 140)
        & (rgb[:, :, 0] > rgb[:, :, 1] + 65)
        & (rgb[:, :, 0] > rgb[:, :, 2] + 65)
    )
    del rgb
    model = {"schemaVersion": "mazeproof.maze/1", "width": cols, "height": rows}
    unknowns = []
    for field, nr, nc in (
        ("horizontalWalls", rows + 1, cols),
        ("verticalWalls", rows, cols + 1),
    ):
        matrix = []
        horizontal = field == "horizontalWalls"
        for r in range(nr):
            line = []
            for c in range(nc):
                radius = max(1.0, min(4.0, min(dx, dy) * 0.09))
                if horizontal:
                    box = (
                        x0 + (c + 0.18) * dx,
                        y0 + r * dy - radius,
                        x0 + (c + 0.82) * dx,
                        y0 + r * dy + radius,
                    )
                else:
                    box = (
                        x0 + c * dx - radius,
                        y0 + (r + 0.18) * dy,
                        x0 + c * dx + radius,
                        y0 + (r + 0.82) * dy,
                    )
                patch = _patch(light, *box)
                scores = [
                    float(np.any(patch < t, axis=0 if horizontal else 1).mean())
                    for t in (80, 128, 176)
                ]
                occupied = scores[1] >= 0.55
                covered = bool(_patch(red, *box).any())
                reason = None
                if covered and answer:
                    reason = "RED_OCCLUSION"
                elif max(scores) > 0.02 and min(scores) < 0.995:
                    reason = "PARTIAL_OR_UNSTABLE_WALL"
                if reason:
                    unknowns.append(
                        {
                            "id": f"{field}:{r}:{c}",
                            "field": field,
                            "row": r,
                            "col": c,
                            "reason": reason,
                            "coverage": round(scores[1], 3),
                        }
                    )
                line.append(bool(occupied))
            matrix.append(line)
        model[field] = matrix
    openings = _openings(model)
    model["entrance"] = openings[0] if openings else {"row": 0, "col": 0, "side": "N"}
    model["exit"] = (
        openings[-1]
        if len(openings) >= 2
        else {"row": rows - 1, "col": cols - 1, "side": "S"}
    )
    notices = ["HUMAN_REVIEW_REQUIRED"]
    if not regular and geometry is None:
        notices.append("GRID_ESTIMATE_UNCERTAIN")
    if len(openings) != 2:
        notices.append("CHOOSE_TWO_OPENINGS")
    route_uncertain = False
    if answer:
        route, route_uncertain = recognize_route(red, geom, model)
        model["route"] = route
        if route_uncertain:
            notices.append("RED_ROUTE_UNCERTAIN")
    return {
        "model": model,
        "geometry": geom,
        "unknowns": unknowns,
        "notices": notices,
        "routeUncertain": route_uncertain,
    }


def _one_component(mask):
    """Exact 8-neighbor connectivity, keeping only the previous row's runs.

    No dilation, gap filling, full-size label image, or per-pixel Python queue.
    A component that ends before another begins proves disconnection early.
    """
    previous = []
    labels = 0
    finished = False
    for row in mask:
        changes = np.diff(np.pad(row.astype(np.int8), (1, 1)))
        starts = np.flatnonzero(changes == 1)
        ends = np.flatnonzero(changes == -1) - 1
        parents = list(range(labels + len(starts)))

        def root(value):
            while parents[value] != value:
                parents[value] = parents[parents[value]]
                value = parents[value]
            return value

        offset = 0
        for index, (start, end) in enumerate(zip(starts, ends)):
            while offset < len(previous) and previous[offset][1] < start - 1:
                offset += 1
            cursor = offset
            while cursor < len(previous) and previous[cursor][0] <= end + 1:
                parents[root(previous[cursor][2])] = root(labels + index)
                cursor += 1
        current_roots = {root(labels + i) for i in range(len(starts))}
        ended = {root(i) for i in range(labels)} - current_roots
        if finished and current_roots:
            return False
        if ended:
            if current_roots or len(ended) > 1 or finished:
                return False
            finished = True
        compact = {label: i for i, label in enumerate(current_roots)}
        previous = [
            (start, end, compact[root(labels + i)])
            for i, (start, end) in enumerate(zip(starts, ends))
        ]
        labels = len(current_roots)
    return finished or labels == 1


def recognize_route(red, geom, model):
    """Infer a single red chain without using the maze solver to fill gaps."""
    x0, y0, x1, y1, cols, rows = (
        geom[k] for k in ("x0", "y0", "x1", "y1", "cols", "rows")
    )
    dx, dy = (x1 - x0) / cols, (y1 - y0) / rows
    graph = {r * cols + c: [] for r in range(rows) for c in range(cols)}
    accounted = np.zeros(red.shape, dtype=bool)
    uncertain = False
    radius = max(2, min(dx, dy) * 0.16)
    for r in range(rows):
        for c in range(cols):
            node = r * cols + c
            cx, cy = x0 + (c + 0.5) * dx, y0 + (r + 0.5) * dy
            for horizontal in (True, False):
                if horizontal and c + 1 >= cols or not horizontal and r + 1 >= rows:
                    continue
                box = (
                    (cx, cy - radius, cx + dx, cy + radius)
                    if horizontal
                    else (cx - radius, cy, cx + radius, cy + dy)
                )
                patch = _patch(red, *box)
                coverage = float(np.any(patch, axis=0 if horizontal else 1).mean())
                if coverage >= 0.995:
                    # Projection alone also covers disconnected, offset strokes.
                    # Keep the candidate for editing, but require route review.
                    if not _one_component(patch):
                        uncertain = True
                    neighbor = node + (1 if horizontal else cols)
                    graph[node].append(neighbor)
                    graph[neighbor].append(node)
                    _patch(accounted, *box)[:] = True
                elif coverage > 0.15:
                    uncertain = True
    active = {n for n, neighbors in graph.items() if neighbors}
    start = model["entrance"]["row"] * cols + model["entrance"]["col"]
    end = model["exit"]["row"] * cols + model["exit"]["col"]
    path, seen, node, previous = [], set(), start, None
    while node not in seen:
        path.append(node)
        seen.add(node)
        if node == end:
            break
        choices = [v for v in graph[node] if v != previous]
        if len(choices) != 1:
            break
        previous, node = node, choices[0]
    if not path or path[-1] != end or seen != active:
        uncertain = True
    if any(len(graph[n]) != (1 if n in (start, end) else 2) for n in active):
        uncertain = True
    # Exterior entrance/exit tails are permitted; unexplained interior marks are not.
    inside = _patch(
        red & ~accounted, x0 + radius, y0 + radius, x1 - radius, y1 - radius
    )
    if inside.sum() > 3:
        uncertain = True
    # Connections must also agree across cell centers and corridor boundaries.
    if not _one_component(_patch(red, x0, y0, x1 + 1, y1 + 1)):
        uncertain = True
    return [{"row": n // cols, "col": n % cols} for n in path], bool(uncertain)


def inspect(data, name, *, page=None, geometry=None, answer=False, rotation=0):
    image, meta = decode(data, name, page)
    if type(rotation) is not int or rotation not in (0, 90, 180, 270):
        reject("ROTATION")
    if rotation:
        image = image.rotate(-rotation, expand=True)
    meta["userRotation"] = rotation
    observed = recognize(image, geometry, answer=answer)
    observed.update(
        image=png_data(image),
        imageSize=list(image.size),
        transform=meta,
        digest=meta["sourceDigest"],
        name=PurePath(name).name,
    )
    return observed
