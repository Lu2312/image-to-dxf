"""
Módulo — Mueble 3D desde PDF (vista isometrica + OCR).

Genera un DXF 3D (3DFACE) por extrusión de placas con espesor fijo.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import List, Tuple

import os
import re

import ezdxf
import cv2
import numpy as np


@dataclass
class Mueble3DParams:
    pdf_bytes: bytes
    width: float
    height: float
    depth: float
    thickness: float = 19.0
    back_thickness: float = 6.0
    use_ocr: bool = True
    ocr_lang: str = "spa"
    pdf_dpi: int = 200


@dataclass
class Mueble3DResult:
    dxf_bytes: bytes
    width: float
    height: float
    depth: float
    thickness: float
    ocr_dims: Tuple[int, int, int] | None
    notes: List[str]


@dataclass
class CutPiece:
    idx: int
    name: str
    length: int
    width: int
    qty: int


DEFAULT_PROFILE = {
    "header_tokens": [
        "NOMBRE", "LARGO", "ANCHO", "TAPACANTO", "RANURA", "ACCESORIOS", "BASICOS",
        "L1", "L2", "A1", "A2", "NAC", "TSID", "EPSE", "ORP",
    ],
    "ignore_tokens": [
        "CREATIVO", "MODELO", "TORNILLOS", "TORNILLO", "LISTA", "CORTE",
    ],
    "lateral_keywords": ["LATERAL", "COSTADO"],
    "base_keywords": ["BASE", "TECHO"],
    "shelf_keywords": ["REPISA", "ENTRE", "ENTREPANO", "ENTREPANO", "ENTREPA"],
    "back_keywords": ["FONDO", "RESPALDO", "TRASERA"],
    "zocalo_keywords": ["ZOCALO", "AMARRE", "AMARRES"],
    "center_keywords": ["DIVIS", "DIVISION", "DIVISOR", "VERTICAL", "CENTRAL"],
}


def _load_profile() -> dict:
    repo_root = Path(__file__).resolve().parents[2]
    profile_path = repo_root / "cutlist_profile.json"
    if not profile_path.exists():
        return DEFAULT_PROFILE.copy()
    try:
        import json
        data = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_PROFILE.copy()
    merged = DEFAULT_PROFILE.copy()
    for k, v in data.items():
        if isinstance(v, list):
            merged[k] = v
    return merged


_PROFILE = _load_profile()


def _profile_list(key: str) -> List[str]:
    return [str(x) for x in _PROFILE.get(key, DEFAULT_PROFILE.get(key, []))]


def _profile_set(key: str) -> set[str]:
    return set(_profile_list(key))


def _add_3dface(msp, pts: List[Tuple[float, float, float]], layer: str) -> None:
    msp.add_3dface(pts, dxfattribs={"layer": layer})


def _add_box_faces(
    msp,
    x0: float,
    y0: float,
    z0: float,
    x1: float,
    y1: float,
    z1: float,
    layer: str,
) -> None:
    # Bottom
    _add_3dface(msp, [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)], layer)
    # Top
    _add_3dface(msp, [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], layer)
    # Front
    _add_3dface(msp, [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], layer)
    # Back
    _add_3dface(msp, [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)], layer)
    # Left
    _add_3dface(msp, [(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)], layer)
    # Right
    _add_3dface(msp, [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], layer)


def _build_boxes(
    width: float,
    height: float,
    depth: float,
    t: float,
    shelf_count: int = 0,
    center_panel: bool = False,
    zocalo_height: float | None = None,
    back_thickness: float | None = None,
) -> List[Tuple[float, float, float, float, float, float]]:
    boxes: List[Tuple[float, float, float, float, float, float]] = []
    # Laterales
    boxes.append((0, 0, 0, t, depth, height))
    boxes.append((width - t, 0, 0, width, depth, height))

    # Base y techo
    boxes.append((t, 0, 0, width - t, depth, t))
    boxes.append((t, 0, height - t, width - t, depth, height))

    # Panel vertical centrado (opcional)
    if center_panel:
        x0 = (width - t) * 0.5
        boxes.append((x0, 0, t, x0 + t, depth, height - t))

    # Repisas
    if shelf_count > 0:
        span = height - 2 * t
        step = span / (shelf_count + 1)
        for i in range(shelf_count):
            z0 = t + step * (i + 1) - t * 0.5
            z1 = z0 + t
            boxes.append((t, 0, z0, width - t, depth, z1))

    # Zocalo frontal (opcional)
    if zocalo_height and zocalo_height > 0:
        boxes.append((t, 0, 0, width - t, t, zocalo_height))

    # Fondo / respaldo (opcional)
    if back_thickness and back_thickness > 0:
        y0 = max(depth - back_thickness, 0)
        boxes.append((t, y0, t, width - t, depth, height - t))

    return boxes


def _norm_name(name: str) -> str:
    n = name.upper()
    n = n.replace("Á", "A").replace("É", "E").replace("Í", "I").replace("Ó", "O").replace("Ú", "U")
    n = n.replace("Ñ", "N")
    return n


def _derive_from_cutlist(
    items: List[CutPiece],
    width: float,
    height: float,
    depth: float,
    t: float,
    back_t: float,
) -> Tuple[List[Tuple[float, float, float, float, float, float]], float, float, float, List[str]]:
    notes: List[str] = []
    by_name = [(i, _norm_name(i.name)) for i in items]
    lateral_kw = _profile_list("lateral_keywords")
    base_kw = _profile_list("base_keywords")
    shelf_kw = _profile_list("shelf_keywords")
    zocalo_kw = _profile_list("zocalo_keywords")
    back_kw = _profile_list("back_keywords")
    center_kw = _profile_list("center_keywords")

    def _has(n: str, kws: List[str]) -> bool:
        return any(k in n for k in kws)

    laterals = [i for i, n in by_name if _has(n, lateral_kw)]
    base_techo = [i for i, n in by_name if _has(n, base_kw)]
    repisas = [i for i, n in by_name if _has(n, shelf_kw)]
    zocalos = [i for i, n in by_name if _has(n, zocalo_kw)]
    fondos = [i for i, n in by_name if _has(n, back_kw)]
    center = any(_has(n, center_kw) for _, n in by_name)

    if height <= 0 and laterals:
        height = float(laterals[0].length)
        depth = depth if depth > 0 else float(laterals[0].width)
        notes.append("Altura y fondo derivados de LATERAL.")

    if width <= 0 and base_techo:
        width = float(base_techo[0].length + 2 * t)
        notes.append("Ancho derivado de BASE/TECHO + laterales.")

    if depth <= 0:
        depth = float(max((i.width for i in items), default=depth))
        if depth > 0:
            notes.append("Fondo derivado de tabla de piezas.")

    shelf_count = 0
    if repisas:
        shelf_count = sum(i.qty for i in repisas)
        notes.append("Repisas derivadas de piezas REPISA.")
    elif base_techo:
        qty = base_techo[0].qty
        shelf_count = max(qty - 2, 0)
        if shelf_count:
            notes.append("Repisas derivadas de BASE/TECHO.")

    zocalo_height = None
    if zocalos:
        zocalo_height = float(zocalos[0].width)
        notes.append("Zocalo frontal detectado.")

    back = back_t if fondos else None
    if fondos:
        notes.append("Fondo cerrado detectado.")

    boxes = _build_boxes(
        width=width,
        height=height,
        depth=depth,
        t=t,
        shelf_count=shelf_count,
        center_panel=center,
        zocalo_height=zocalo_height,
        back_thickness=back,
    )

    return boxes, width, height, depth, notes


def _configure_tesseract(pytesseract) -> None:
    cmd_env = os.environ.get("TESSERACT_CMD", "")
    if cmd_env:
        pytesseract.pytesseract.tesseract_cmd = cmd_env
    else:
        exe = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
        if exe.exists():
            pytesseract.pytesseract.tesseract_cmd = str(exe)

    if "TESSDATA_PREFIX" not in os.environ:
        repo_root = Path(__file__).resolve().parents[2]
        local_tessdata = repo_root / "tessdata"
        if local_tessdata.exists():
            os.environ["TESSDATA_PREFIX"] = str(local_tessdata)


def _render_pdf_gray(pdf_bytes: bytes, dpi: int) -> np.ndarray:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
        gray = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width)
        return gray
    finally:
        doc.close()


def _find_table_roi(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape
    crop = gray[int(h * 0.45):, :]
    thr = cv2.adaptiveThreshold(crop, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                cv2.THRESH_BINARY_INV, 21, 8)
    horiz = cv2.getStructuringElement(cv2.MORPH_RECT, (w // 15, 1))
    vert = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(10, h // 50)))
    h_lines = cv2.morphologyEx(thr, cv2.MORPH_OPEN, horiz)
    v_lines = cv2.morphologyEx(thr, cv2.MORPH_OPEN, vert)
    grid = cv2.bitwise_or(h_lines, v_lines)
    contours, _ = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return crop
    x, y, cw, ch = max((cv2.boundingRect(c) for c in contours), key=lambda r: r[2] * r[3])
    pad = 8
    x0 = max(x - pad, 0)
    y0 = max(y - pad, 0)
    x1 = min(x + cw + pad, crop.shape[1])
    y1 = min(y + ch + pad, crop.shape[0])
    return crop[y0:y1, x0:x1]


def _fallback_table_roi(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape
    y0 = int(h * 0.62)
    y1 = int(h * 0.95)
    x0 = int(w * 0.04)
    x1 = int(w * 0.78)
    return gray[y0:y1, x0:x1]


def _roi_from_keyword(gray: np.ndarray, keyword: str) -> np.ndarray | None:
    try:
        import pytesseract
        from pytesseract import Output
    except Exception:
        return None

    h, w = gray.shape
    scale = 1.5
    small = cv2.resize(gray, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    data = pytesseract.image_to_data(small, lang="spa", config="--psm 6", output_type=Output.DICT)

    hits = []
    for i, text in enumerate(data.get("text", [])):
        t = (text or "").strip().upper()
        t = re.sub(r"[^A-Z]", "", t)
        if t.startswith(keyword[:3]):
            try:
                y = int(data["top"][i] / scale)
            except Exception:
                y = None
            if y is not None:
                hits.append(y)
    if not hits:
        return None

    y0 = max(min(hits) - 20, 0)
    return gray[y0:h, int(w * 0.05):int(w * 0.95)]


def _parse_cutlist_text(text: str) -> List[CutPiece]:
    items: List[CutPiece] = []
    tokens = re.findall(r"[A-ZÁÉÍÓÚÑ/]+|\d{1,4}", text.upper())
    header = {"NOMBRE", "LARGO", "ANCHO", "TAPACANTO", "RANURA", "ACCESORIOS", "BASICOS",
              "L1", "L2", "A1", "A2", "NAC", "TSID", "EPSE", "ORP"}
    if "NOMBRE" in tokens:
        i = tokens.index("NOMBRE") + 1
        while i < len(tokens):
            if tokens[i].isdigit():
                i += 1
                continue
            if tokens[i] in header or len(tokens[i]) <= 2:
                i += 1
                continue
            name_tokens: List[str] = []
            while i < len(tokens) and not tokens[i].isdigit():
                if tokens[i] not in header and len(tokens[i]) > 2:
                    name_tokens.append(tokens[i])
                i += 1
            if not name_tokens:
                continue
            name = " ".join(name_tokens).replace(" / ", "/")
            length = None
            width = None
            qty = 1
            while i < len(tokens):
                token = tokens[i]
                if token.isdigit():
                    val = int(token)
                    if val >= 100 and length is None:
                        length = val
                    elif val >= 100 and width is None:
                        width = val
                    elif length is not None and width is not None and val <= 50:
                        qty = val
                        i += 1
                        break
                elif length is not None and width is not None and token not in header and len(token) > 2:
                    break
                i += 1
            if length is None or width is None:
                continue
            items.append(CutPiece(idx=len(items) + 1, name=name, length=length, width=width, qty=qty))
        if items:
            return items

    lines = [re.sub(r"\s+", " ", l.strip()) for l in text.splitlines() if l.strip()]
    header = {"NOMBRE", "LARGO", "ANCHO", "TAPACANTO", "RANURA", "ACCESORIOS", "BASICOS"}

    for line in lines:
        up = line.upper()
        m = re.match(r"^(\d+)\s+(.+?)\s+(\d{2,4})\s+(\d{2,4})(?:\s+(\d{1,3}))?$", up)
        if not m:
            continue
        idx = int(m.group(1))
        name = m.group(2).strip()
        length = int(m.group(3))
        width = int(m.group(4))
        qty = int(m.group(5)) if m.group(5) else 1
        items.append(CutPiece(idx=idx, name=name, length=length, width=width, qty=qty))

    if items:
        return items

    i = 0
    while i < len(lines):
        line = lines[i]
        up = line.upper()
        if any(h in up for h in header):
            i += 1
            continue
        if not re.search(r"[A-Z]", up):
            i += 1
            continue

        name = line.strip()
        nums: List[int] = []
        j = i + 1
        while j < len(lines) and len(nums) < 4:
            token = lines[j].strip()
            if re.fullmatch(r"\d{1,4}", token):
                nums.append(int(token))
            elif re.search(r"[A-Z]", token) and nums:
                break
            j += 1
        dims = [n for n in nums if n >= 100]
        if len(dims) >= 2:
            qty = next((n for n in nums if 1 <= n <= 50 and n not in dims), 1)
            items.append(CutPiece(idx=len(items) + 1, name=name, length=dims[0], width=dims[1], qty=qty))
            i = j
        else:
            i += 1
    return items


def _rows_from_ocr(data: dict) -> List[List[Tuple[int, str]]]:
    words: List[Tuple[int, int, str]] = []
    n = len(data.get("text", []))
    for i in range(n):
        text = (data["text"][i] or "").strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][i])
        except Exception:
            conf = 0.0
        if conf < 40:
            continue
        x = int(data["left"][i])
        y = int(data["top"][i])
        words.append((x, y, text))

    words.sort(key=lambda w: (w[1], w[0]))
    rows: List[List[Tuple[int, str]]] = []
    tol = 12
    for x, y, text in words:
        if not rows:
            rows.append([(x, text)])
            rows[-1].append((y, "__y__"))
            continue
        row = rows[-1]
        row_y = next((v for v in row if v[1] == "__y__"), (y, "__y__"))[0]
        if abs(y - row_y) <= tol:
            row.append((x, text))
        else:
            rows.append([(x, text), (y, "__y__")])

    cleaned: List[List[Tuple[int, str]]] = []
    for row in rows:
        row = [t for t in row if t[1] != "__y__"]
        row.sort(key=lambda v: v[0])
        cleaned.append(row)
    return cleaned


def _parse_cutlist_rows(rows: List[List[Tuple[int, str]]]) -> List[CutPiece]:
    items: List[CutPiece] = []
    header_idx = -1
    for i, row in enumerate(rows):
        joined = " ".join(t for _, t in row).upper()
        if "NOMBRE" in joined and "LARGO" in joined and "ANCHO" in joined:
            header_idx = i
            break

    data_rows = rows[header_idx + 1:] if header_idx >= 0 else rows
    for row in data_rows:
        tokens = [t for _, t in row]
        joined = " ".join(tokens).strip()
        if not joined:
            continue
        if "ACCESORIOS" in joined.upper():
            continue
        numbers: List[int] = []
        for token in tokens:
            cleaned = re.sub(r"\D", "", token)
            if cleaned.isdigit():
                numbers.append(int(cleaned))
        dims = [n for n in numbers if 100 <= n <= 4000]
        if len(dims) < 2:
            continue
        qty = next((n for n in numbers if 1 <= n <= 50 and n not in dims), 1)
        first_num_idx = next((i for i, t in enumerate(tokens) if re.search(r"\d", t)), len(tokens))
        name = " ".join(tokens[:first_num_idx]).strip() or "PIEZA"
        items.append(CutPiece(idx=len(items) + 1, name=name, length=dims[0], width=dims[1], qty=qty))
    return items


def _extract_dims_from_text(text: str) -> Tuple[int, int, int] | None:
    pattern = re.compile(r"(\d{2,4})\s*[x×]\s*(\d{2,4})\s*[x×]\s*(\d{2,4})")
    match = pattern.search(text)
    if match:
        w, h, d = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        return (w, h, d)
    # Fallback: take the first 3 large numbers before the header
    lines = [l.strip() for l in text.splitlines()]
    nums: List[int] = []
    for line in lines:
        if "NOMBRE" in line.upper():
            break
        for n in re.findall(r"\b\d{2,4}\b", line):
            val = int(n)
            if val >= 100:
                nums.append(val)
    if len(nums) >= 3:
        return (nums[0], nums[1], nums[2])
    return None


def _ocr_pdf_dims(pdf_bytes: bytes, dpi: int, lang: str) -> Tuple[Tuple[int, int, int] | None, List[str]]:
    notes: List[str] = []
    try:
        import fitz  # PyMuPDF
    except Exception as exc:
        raise ValueError("PyMuPDF no esta instalado para leer PDFs.") from exc

    try:
        import pytesseract
    except Exception as exc:
        raise ValueError("pytesseract no esta instalado para OCR.") from exc

    _configure_tesseract(pytesseract)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc.load_page(0)
        raw_text = page.get_text("text") or ""
        dims = _extract_dims_from_text(raw_text)
        if dims:
            notes.append("Dimensiones detectadas por texto PDF.")
            return dims, notes

        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
        from PIL import Image
        img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        try:
            text = pytesseract.image_to_string(img, lang=lang)
        except Exception as exc:
            notes.append(f"OCR no disponible: {exc}")
            return None, notes
    finally:
        doc.close()

    dims = _extract_dims_from_text(text)
    if dims:
        notes.append("Dimensiones detectadas por OCR.")
        return dims, notes

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    label_nums: List[int] = []
    for line in lines:
        if line.isdigit() and 2 <= len(line) <= 4:
            label_nums.append(int(line))

    unique = sorted(set(n for n in label_nums if 100 <= n <= 3000), reverse=True)
    if len(unique) >= 3:
        width, height, depth = unique[0], unique[1], unique[2]
        notes.append(f"OCR dims detectadas: {width} x {height} x {depth}")
        return (width, height, depth), notes

    notes.append("No se detectaron cotas claras en OCR.")
    return None, notes


def _ocr_cutlist(pdf_bytes: bytes, dpi: int, lang: str) -> Tuple[List[CutPiece], List[str]]:
    notes: List[str] = []
    try:
        import pytesseract
    except Exception as exc:
        raise ValueError("pytesseract no esta instalado para OCR.") from exc

    _configure_tesseract(pytesseract)
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            page = doc.load_page(0)
            raw_text = page.get_text("text") or ""
        finally:
            doc.close()
    except Exception:
        raw_text = ""

    if raw_text:
        items = _parse_cutlist_text(raw_text)
        if items:
            notes.append("Lista de corte detectada por texto PDF.")
            return items, notes

    gray = _render_pdf_gray(pdf_bytes, dpi)
    roi = _roi_from_keyword(gray, "NOMBRE")
    if roi is None:
        roi = _find_table_roi(gray)
    else:
        notes.append("ROI basado en encabezado de tabla.")

    rois = [roi, _fallback_table_roi(gray)]
    items: List[CutPiece] = []
    for candidate in rois:
        scale = 2.0
        view = cv2.resize(candidate, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        view = cv2.GaussianBlur(view, (3, 3), 0)
        thr = cv2.adaptiveThreshold(view, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY, 31, 4)
        for psm in ("6", "11"):
            try:
                from pytesseract import Output
                data = pytesseract.image_to_data(thr, lang=lang, config=f"--psm {psm}", output_type=Output.DICT)
                rows = _rows_from_ocr(data)
                items = _parse_cutlist_rows(rows)
            except Exception:
                text = pytesseract.image_to_string(thr, lang=lang, config=f"--psm {psm}")
                items = _parse_cutlist_text(text)
            if items:
                break
        if items:
            break
    if not items:
        notes.append("No se pudo leer la tabla de piezas.")
    return items, notes


def _project_iso(x: float, y: float, z: float) -> Tuple[float, float]:
    return x - y * 0.55, z + y * 0.45


def _svg_preview(width: float, height: float, depth: float, t: float,
                 boxes: List[Tuple[float, float, float, float, float, float]] | None = None) -> str:
    if boxes is None:
        boxes = _build_boxes(width, height, depth, t)
    edges = [
        (0, 1), (1, 3), (3, 2), (2, 0),
        (4, 5), (5, 7), (7, 6), (6, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]

    segs = []
    pts_all: List[Tuple[float, float]] = []
    for x0, y0, z0, x1, y1, z1 in boxes:
        verts = [
            (x0, y0, z0), (x1, y0, z0), (x0, y1, z0), (x1, y1, z0),
            (x0, y0, z1), (x1, y0, z1), (x0, y1, z1), (x1, y1, z1),
        ]
        proj = [_project_iso(x, y, z) for x, y, z in verts]
        for a, b in edges:
            p1 = proj[a]
            p2 = proj[b]
            segs.append((p1, p2))
            pts_all.extend([p1, p2])

    xs = [p[0] for p in pts_all]
    ys = [p[1] for p in pts_all]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    pad = max(width, height, depth) * 0.05
    vb = (min_x - pad, min_y - pad, (max_x - min_x) + 2 * pad, (max_y - min_y) + 2 * pad)

    lines = "\n".join(
        f'<line x1="{p1[0]:.2f}" y1="{p1[1]:.2f}" x2="{p2[0]:.2f}" y2="{p2[1]:.2f}" />'
        for p1, p2 in segs
    )

    return (
        f'<svg viewBox="{vb[0]:.2f} {vb[1]:.2f} {vb[2]:.2f} {vb[3]:.2f}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<g fill="none" stroke="#58a6ff" stroke-width="2">{lines}</g></svg>'
    )


class Mueble3DGenerator:

    def generate(self, p: Mueble3DParams) -> Mueble3DResult:
        notes: List[str] = []
        ocr_dims: Tuple[int, int, int] | None = None
        boxes_from_cutlist: List[Tuple[float, float, float, float, float, float]] | None = None
        if p.use_ocr:
            ocr_dims, ocr_notes = _ocr_pdf_dims(p.pdf_bytes, p.pdf_dpi, p.ocr_lang)
            notes.extend(ocr_notes)

        cutlist_items: List[CutPiece] = []
        try:
            cutlist_items, cut_notes = _ocr_cutlist(p.pdf_bytes, p.pdf_dpi, p.ocr_lang)
            if cutlist_items:
                notes.extend(cut_notes)
        except Exception:
            cutlist_items = []

        width = p.width
        height = p.height
        depth = p.depth
        if (width <= 0 or height <= 0 or depth <= 0) and ocr_dims:
            width = width if width > 0 else float(ocr_dims[0])
            height = height if height > 0 else float(ocr_dims[1])
            depth = depth if depth > 0 else float(ocr_dims[2])

        if width <= 0 or height <= 0 or depth <= 0:
            if cutlist_items:
                boxes_from_cutlist, width, height, depth, cut_notes = _derive_from_cutlist(
                    cutlist_items, width, height, depth, p.thickness, p.back_thickness
                )
                notes.extend(cut_notes)
            else:
                raise ValueError("Faltan dimensiones. Proporciona width/height/depth o usa OCR valido.")

        t = p.thickness
        if t <= 0 or t >= min(width, height, depth):
            raise ValueError("Espesor invalido para las dimensiones dadas.")

        # Documento DXF
        doc = ezdxf.new("R2010")
        doc.header["$INSUNITS"] = 4
        doc.header["$MEASUREMENT"] = 1
        msp = doc.modelspace()
        layer = "MUEBLE-3D"
        if layer not in doc.layers:
            doc.layers.add(layer, color=2)

        if cutlist_items and (width > 0 and height > 0 and depth > 0):
            boxes = boxes_from_cutlist
            if boxes is None:
                boxes, width, height, depth, cut_notes = _derive_from_cutlist(
                    cutlist_items, width, height, depth, p.thickness, p.back_thickness
                )
                notes.extend([n for n in cut_notes if n not in notes])
        else:
            boxes = _build_boxes(width, height, depth, t)

        for x0, y0, z0, x1, y1, z1 in boxes:
            _add_box_faces(msp, x0, y0, z0, x1, y1, z1, layer)

        buf = StringIO()
        doc.write(buf)
        dxf_bytes = buf.getvalue().encode("utf-8")

        return Mueble3DResult(
            dxf_bytes=dxf_bytes,
            width=width,
            height=height,
            depth=depth,
            thickness=t,
            ocr_dims=ocr_dims,
            notes=notes,
        )

    def preview_svg(self, p: Mueble3DParams) -> Tuple[str, Mueble3DResult]:
        result = self.generate(p)
        try:
            cutlist_items, _ = _ocr_cutlist(p.pdf_bytes, p.pdf_dpi, p.ocr_lang)
        except Exception:
            cutlist_items = []

        if cutlist_items:
            boxes, _, _, _, _ = _derive_from_cutlist(
                cutlist_items, result.width, result.height, result.depth, result.thickness, p.back_thickness
            )
            svg = _svg_preview(result.width, result.height, result.depth, result.thickness, boxes=boxes)
        else:
            svg = _svg_preview(result.width, result.height, result.depth, result.thickness)
        return svg, result

    def cutlist(self, p: Mueble3DParams) -> Tuple[List[CutPiece], List[str]]:
        return _ocr_cutlist(p.pdf_bytes, p.pdf_dpi, p.ocr_lang)
