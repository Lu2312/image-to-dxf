# image-to-dxf=4.8.0

High-quality image-to-DXF converter optimised for AutoCAD.

## Features

| Feature | Detail |
|---|---|
| **3 conversion modes** | `trace`, `hatch`, `pixel` |
| **AutoCAD-ready DXF** | AC1015 (AutoCAD 2000+), mm units, named layers |
| **Contour tracing** | OpenCV `findContours` + optional Douglas-Peucker simplification |
| **Smooth curves** | Optional SPLINE entities (cubic B-spline) |
| **Solid fills** | HATCH entities with SOLID pattern |
| **Metadata block** | Title, source file, dimensions and date written to an INFO layer |
| **GUI** | Resizable Tkinter app with live image preview and DXF preview |
| **CLI** | Full command-line interface with stats output |

## Conversion modes

| Mode | What it produces | Best for |
|---|---|---|
| `trace` | LWPOLYLINE (or SPLINE) outlines | Line art, logos, signatures |
| `hatch` | Outlined + solid-filled HATCH shapes | Silhouettes, filled logos |
| `pixel` | One SOLID square per dark pixel | Pixel art, small rasters |

## Installation

```bash
pip install -r requirements.txt
```

### Requirements

| Package | Minimum version |
|---|---|
| `opencv-python` | 4.8.0 |
| `ezdxf` | 1.1.0 |
| `Pillow` | 10.0.0 |
| `numpy` | 1.24.0 |
| `matplotlib` | 3.7.0 |

## Quick start

### GUI

```bash
python gui.py
```

1. Click **Browse…** next to *Input image* and select a PNG / JPG / BMP / TIFF.
2. The thumbnail appears immediately in the **Original image** tab on the right.
3. Adjust options (mode, scale, threshold, …) as needed.
4. Optionally type a **Drawing title** – it will be embedded in the DXF INFO layer.
5. Click **⚙ Convert to DXF**.
6. After conversion the **DXF preview** tab shows a rendered view of all entities.
7. Conversion statistics (contours, entities, drawing size) appear in the left panel.

### CLI

```bash
python image_to_dxf.py input.png
python image_to_dxf.py input.png -o output.dxf -m hatch -s 0.25
```

Sample output:

```
DXF saved to: output.dxf
  Contours : 14
  Entities : 31
  Size     : 128.0 x 64.0 mm
```

### Python API

```python
from image_to_dxf import convert

result = convert(
    "logo.png",
    "logo.dxf",
    mode="hatch",       # "trace" | "hatch" | "pixel"
    scale=0.25,         # mm per pixel
    threshold=127,      # greyscale binarisation threshold (0-255)
    min_area=10.0,      # discard contours smaller than this (px²)
    approx_epsilon=0.5, # Douglas-Peucker simplification (px); 0 = off
    lineweight=25,      # 1/100 mm
    title="My Logo",    # written to the INFO layer
)

print(result.path)           # pathlib.Path to the saved DXF
print(result.contour_count)  # number of contours found
print(result.entity_count)   # number of DXF entities written
print(result.dxf_width)      # drawing width in mm
print(result.dxf_height)     # drawing height in mm
```

## CLI reference

```
usage: image_to_dxf.py [-h] [-o OUTPUT] [-m {trace,hatch,pixel}]
                        [-s SCALE] [-t THRESHOLD]
                        [--min-area MIN_AREA] [--epsilon EPSILON]
                        [--spline] [--lineweight LINEWEIGHT]
                        [--layer-contour LAYER_CONTOUR]
                        [--layer-hatch LAYER_HATCH]
                        input

positional arguments:
  input                      Source image path

options:
  -o, --output OUTPUT        Output DXF path (default: same dir/name as input)
  -m, --mode {trace,hatch,pixel}
                             Conversion mode (default: trace)
  -s, --scale SCALE          mm per pixel (default: 0.1)
  -t, --threshold THRESHOLD  Greyscale threshold 0-255 (default: 127)
  --min-area MIN_AREA        Minimum contour area in px² (default: 10)
  --epsilon EPSILON          Douglas-Peucker simplification in px (default: 0.5)
  --spline                   Use SPLINE entities instead of LWPOLYLINE
  --lineweight LINEWEIGHT    Lineweight in 1/100 mm (default: 25)
  --layer-contour NAME       Layer name for contour entities (default: CONTOURS)
  --layer-hatch NAME         Layer name for hatch entities (default: HATCHES)
```

## DXF layer structure

| Layer | Content | Default ACI colour |
|---|---|---|
| `CONTOURS` | Traced polylines / splines | 7 (white/black) |
| `HATCHES` | Solid hatch fills | 2 (yellow) |
| `PIXELS` | Pixel-mode SOLID squares | 3 (green) |
| `INFO` | Title block text and separator line | 8 (dark grey) |

## Running the tests

```bash
pip install pytest
pytest test_image_to_dxf.py -v
```

## Project structure

```
image-to-dxf/
├── image_to_dxf.py      # Core converter library + CLI entry-point
├── gui.py               # Tkinter GUI with image & DXF preview
├── test_image_to_dxf.py # pytest test suite
├── requirements.txt     # Python dependencies
└── README.md
```


## GUI usage

```bash
python gui.py
```

1. Click **Browse…** to select your image (PNG, JPG, BMP, TIFF, …).
2. Choose an output path (auto-filled from the input name).
3. Adjust options if needed.
4. Click **Convert**.

## CLI usage

```bash
python image_to_dxf.py input.png
python image_to_dxf.py input.png -o output.dxf -m hatch -s 0.2
python image_to_dxf.py logo.png --spline --epsilon 1.0
```

### All CLI flags

| Flag | Default | Description |
|---|---|---|
| `-o / --output` | same name as input | Output `.dxf` path |
| `-m / --mode` | `trace` | `trace` / `hatch` / `pixel` |
| `-s / --scale` | `0.1` | mm per pixel |
| `-t / --threshold` | `127` | Greyscale threshold (0-255) |
| `--min-area` | `10` | Minimum contour area (px²) |
| `--epsilon` | `0.5` | Douglas-Peucker simplification (px); `0` = off |
| `--spline` | off | Use SPLINE entities (trace mode) |
| `--lineweight` | `25` | Lineweight in 1/100 mm |
| `--layer-contour` | `CONTOURS` | Layer name for outlines |
| `--layer-hatch` | `HATCHES` | Layer name for fills |

## Tips for AutoCAD

* Open the `.dxf` with **File → Open** or drag it into AutoCAD.
* Use `ZOOM E` to fit the drawing in the viewport.
* The geometry is on separate layers (`CONTOURS`, `HATCHES`) — toggle visibility as needed.
* Scale (`-s`) controls real-world size: `0.1` mm/px means a 1000 px wide image becomes 100 mm (10 cm) wide.
* Increase `--epsilon` (e.g. `2.0`) to reduce node count and file size for complex images.

## Dependencies

* [OpenCV](https://opencv.org/) — contour detection
* [ezdxf](https://ezdxf.readthedocs.io/) — DXF writing
* [Pillow](https://python-pillow.org/) — image loading
* [NumPy](https://numpy.org/) — array operations
