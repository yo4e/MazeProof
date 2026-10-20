"""Original MIT synthetic demonstration, independent of any product data."""

import base64
import io

from PIL import Image, ImageDraw


def demo_model():
    # A 4x4 snake has exactly one path and no hidden generator dependency.
    return {
        "schemaVersion": "mazeproof.maze/1",
        "width": 4,
        "height": 4,
        "horizontalWalls": [
            [False, True, True, True],
            [True, True, True, False],
            [False, True, True, True],
            [True, True, True, False],
            [False, True, True, True],
        ],
        "verticalWalls": [[True, False, False, False, True] for _ in range(4)],
        "entrance": {"row": 0, "col": 0, "side": "N"},
        "exit": {"row": 3, "col": 0, "side": "S"},
    }


def demo_route():
    return [
        {"row": r, "col": c}
        for r in range(4)
        for c in (range(4) if r % 2 == 0 else range(3, -1, -1))
    ]


def render(model, route=None, *, cell=72, margin=24, thickness=5):
    image = Image.new(
        "RGB",
        (
            model["width"] * cell + margin * 2 + 1,
            model["height"] * cell + margin * 2 + 1,
        ),
        "white",
    )
    draw = ImageDraw.Draw(image)
    for r, row in enumerate(model["horizontalWalls"]):
        for c, wall in enumerate(row):
            if wall:
                draw.line(
                    (
                        margin + c * cell,
                        margin + r * cell,
                        margin + (c + 1) * cell,
                        margin + r * cell,
                    ),
                    fill="black",
                    width=thickness,
                )
    for r, row in enumerate(model["verticalWalls"]):
        for c, wall in enumerate(row):
            if wall:
                draw.line(
                    (
                        margin + c * cell,
                        margin + r * cell,
                        margin + c * cell,
                        margin + (r + 1) * cell,
                    ),
                    fill="black",
                    width=thickness,
                )
    if route:
        draw.line(
            [
                (margin + (p["col"] + 0.5) * cell, margin + (p["row"] + 0.5) * cell)
                for p in route
            ],
            fill=(225, 35, 55),
            width=5,
        )
    return image


def demo_sources():
    sources = {}
    for role in ("problem", "solution"):
        output = io.BytesIO()
        render(demo_model(), demo_route() if role == "solution" else None).save(
            output, "PNG"
        )
        sources[role] = {
            "name": role + ".png",
            "data": base64.b64encode(output.getvalue()).decode(),
        }
    return sources
