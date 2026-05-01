"""
pdf_utils.py
------------
Genera PDF de planos a partir de un archivo DXF usando matplotlib
y el addon de renderizado de ezdxf.
"""
from __future__ import annotations

import io
from pathlib import Path

import ezdxf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend


def dxf_to_pdf_bytes(
    dxf_path: str | Path,
    title: str = "",
    paper: str = "A1",
) -> bytes:
    """
    Renderiza el model-space de un DXF como PDF y devuelve los bytes.

    Parameters
    ----------
    dxf_path : ruta al archivo DXF
    title    : título que aparece en el pie de página
    paper    : tamaño de hoja  ("A4" | "A3" | "A2" | "A1")
    """
    PAPER_SIZES = {   # (ancho, alto) en pulgadas
        "A4": (8.27,  11.69),
        "A3": (11.69, 16.54),
        "A2": (16.54, 23.39),
        "A1": (23.39, 33.11),
    }
    figsize = PAPER_SIZES.get(paper.upper(), PAPER_SIZES["A1"])

    doc = ezdxf.readfile(str(dxf_path))
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    backend = MatplotlibBackend(ax)
    Frontend(RenderContext(doc), backend).draw_layout(doc.modelspace())

    ax.set_aspect("equal")
    ax.autoscale()
    ax.tick_params(colors="#999999", labelsize=6)
    for spine in ax.spines.values():
        spine.set_edgecolor("#cccccc")

    if title:
        fig.text(
            0.5, 0.01, title,
            ha="center", fontsize=8, color="#555555",
            fontstyle="italic",
        )

    fig.tight_layout(pad=0.8)

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        pdf.savefig(fig, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()
