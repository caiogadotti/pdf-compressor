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
