import io
import os

import fitz
from PIL import Image

MAX_DIM = 1600
JPEG_QUALITY = 55


def compress_pdf(src_path, out_path, max_dim=MAX_DIM, quality=JPEG_QUALITY):
    doc = fitz.open(src_path)
    for page in doc:
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                pix = fitz.Pixmap(doc, xref)
            except Exception:
                continue
            if pix.n - pix.alpha >= 4:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            w, h = pix.width, pix.height
            if w == 0 or h == 0:
                continue
            try:
                mode = "RGB" if pix.n >= 3 else "L"
                im = Image.frombytes(mode, (w, h), pix.samples)
                if max(w, h) > max_dim:
                    scale = max_dim / max(w, h)
                    im = im.resize(
                        (max(1, int(w * scale)), max(1, int(h * scale))),
                        Image.LANCZOS,
                    )
                buf = io.BytesIO()
                im.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
                page.replace_image(xref, stream=buf.getvalue())
            except Exception:
                pass
            pix = None
    doc.save(out_path, garbage=4, deflate=True, clean=True)
    doc.close()


def render_preview(pdf_path, page_no=0, max_dim=320):
    """Rasterizes one PDF page as a PIL image, for the "before" side of the preview.

    Renders the whole page (not just embedded images), because a PDF can be
    heavy from other things than a photo (vector art, many small images),
    and the preview should show what the page actually looks like, not
    assume it's a scan.
    """
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_no]
        zoom = max_dim / max(page.rect.width, page.rect.height)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        mode = "RGB" if pix.n >= 3 else "L"
        return Image.frombytes(mode, (pix.width, pix.height), pix.samples).convert("RGB")
    finally:
        doc.close()


def simulate_compression(image, max_dim, quality):
    """Applies the same downscale+JPEG requantization compress_pdf would, to a preview image.

    Reuses the rendered "before" page instead of re-rasterizing and
    recompressing the whole PDF on every slider tick, since that would be
    too slow to feel live. The visual result is the same transform
    compress_pdf applies to embedded images, just run once on a small
    already-rendered thumbnail.
    """
    im = image
    if max(im.size) > max_dim:
        scale = max_dim / max(im.size)
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality, optimize=True)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def collect_pdfs(paths):
    """Takes a list of paths (files and/or folders) and returns [(src, output_dir), ...]."""
    jobs = []
    for p in paths:
        if not os.path.exists(p):
            continue
        if os.path.isdir(p):
            out_dir = os.path.join(p, "compressed")
            out_abs = os.path.abspath(out_dir)
            for root, _dirs, files in os.walk(p):
                if os.path.abspath(root).startswith(out_abs):
                    continue
                for fname in files:
                    if fname.lower().endswith(".pdf"):
                        src = os.path.join(root, fname)
                        rel = os.path.relpath(root, p)
                        dest_dir = out_dir if rel == "." else os.path.join(out_dir, rel)
                        jobs.append((src, dest_dir))
        elif p.lower().endswith(".pdf"):
            out_dir = os.path.join(os.path.dirname(p), "compressed")
            jobs.append((p, out_dir))
    return jobs
