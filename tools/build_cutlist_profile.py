"""
Build a cutlist parsing profile from PDF samples.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import fitz

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


def extract_names(text: str) -> list[str]:
    tokens = re.findall(r"[A-ZÁÉÍÓÚÑ/]+|\d{1,4}", text.upper())
    header = set(DEFAULT_PROFILE["header_tokens"])
    ignore = set(DEFAULT_PROFILE["ignore_tokens"])
    names: list[str] = []
    if "NOMBRE" not in tokens:
        return names

    i = tokens.index("NOMBRE") + 1
    while i < len(tokens):
        if tokens[i].isdigit():
            i += 1
            continue
        if tokens[i] in header or tokens[i] in ignore or len(tokens[i]) <= 2:
            i += 1
            continue
        name_tokens: list[str] = []
        while i < len(tokens) and not tokens[i].isdigit():
            if tokens[i] not in header and tokens[i] not in ignore and len(tokens[i]) > 2:
                name_tokens.append(tokens[i])
            i += 1
        if name_tokens:
            names.append(" ".join(name_tokens).replace(" / ", "/"))
        while i < len(tokens) and tokens[i].isdigit():
            i += 1
    return names


def build_profile(pdf_paths: list[Path]) -> dict:
    names: set[str] = set()
    name_tokens: set[str] = set()

    for path in pdf_paths:
        doc = fitz.open(path)
        try:
            page = doc.load_page(0)
            text = page.get_text("text") or ""
        finally:
            doc.close()
        for name in extract_names(text):
            names.add(name)
            for token in re.findall(r"[A-ZÁÉÍÓÚÑ]+", name.upper()):
                if len(token) > 2:
                    name_tokens.add(token)

    profile = DEFAULT_PROFILE.copy()
    profile["name_keywords"] = sorted(names)
    profile["name_tokens"] = sorted(name_tokens)

    if any(t.startswith("ENTREP") for t in name_tokens):
        profile["shelf_keywords"].append("ENTREP")
    if any(t.startswith("FONDO") for t in name_tokens):
        profile["back_keywords"].append("FONDO")
    if any(t.startswith("ZOCAL") for t in name_tokens):
        profile["zocalo_keywords"].append("ZOCAL")

    return profile


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    samples = repo_root / "ENTRENAMIENTO"
    pdf_paths = sorted(samples.glob("*.pdf"))
    if not pdf_paths:
        raise SystemExit("No PDF files found in ENTRENAMIENTO.")

    profile = build_profile(pdf_paths)
    out_path = repo_root / "cutlist_profile.json"
    out_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Profile saved to: {out_path}")
    print(f"PDFs processed: {len(pdf_paths)}")
    print(f"Names: {len(profile.get('name_keywords', []))}")


if __name__ == "__main__":
    main()
