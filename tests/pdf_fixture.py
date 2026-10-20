"""Hand-written, dependency-free PDF fixture builder; original MIT test data."""


def pdf_bytes(
    *, pages=1, width=337, height=337, rotation=0, javascript=False, attachment=False
):
    objects = []

    def add(value):
        objects.append(value)
        return len(objects)

    add(b"")  # catalog
    add(b"")  # page tree
    page_ids = []
    for _ in range(pages):
        stream = (
            b"0 0 0 RG 5 w 24 24 m 312 24 l 312 312 l 24 312 l S 24 24 m 24 250 l S"
        )
        content_id = add(
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
        page_ids.append(
            add(
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /CropBox [0 0 {width} {height}] /Rotate {rotation} /Contents {content_id} 0 R /Resources << >> >>".encode()
            )
        )
    names = []
    if javascript:
        script_id = add(b"<< /S /JavaScript /JS (app.alert\\(1\\)) >>")
        names.append(f"/JavaScript << /Names [(test) {script_id} 0 R] >>")
    if attachment:
        data_id = add(b"<< /Type /EmbeddedFile /Length 4 >>\nstream\ntest\nendstream")
        file_id = add(
            f"<< /Type /Filespec /F (test.txt) /EF << /F {data_id} 0 R >> >>".encode()
        )
        names.append(f"/EmbeddedFiles << /Names [(test.txt) {file_id} 0 R] >>")
    objects[0] = (
        "<< /Type /Catalog /Pages 2 0 R"
        + (" /Names << " + " ".join(names) + " >>" if names else "")
        + " >>"
    ).encode()
    objects[1] = (
        f"<< /Type /Pages /Count {pages} /Kids [{' '.join(str(i) + ' 0 R' for i in page_ids)}] >>".encode()
    )
    output = b"%PDF-1.7\n"
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    output += b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:])
    output += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return output
