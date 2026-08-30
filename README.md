# 3D Slicer

A user-friendly Python tool that slices 3D mesh files (STL and other formats supported by `trimesh`) into numbered 2D vector files (SVG).

Perfect for laser cutting, CNC, paper models, or any workflow that needs sequential 2D cross-sections of a 3D object.

---

## Features

- **Simple graphical interface** (Tkinter)
- Load STL, OBJ, PLY, and other formats supported by `trimesh`
- Choose number of slices
- Horizontal (Z-axis) or Vertical (X-axis) slicing
- **Slice Offset** – shrink the range along the slice normal to avoid empty or degenerate slices near the extremities
- **Tilt Angle** – rotate the cutting plane around the Y-axis, about the **model centroid** (not the world origin)
- 3D preview of the mesh with the real (possibly tilted) slice plane, plus a 2D contour preview
- Preview sliders stay in sync with the offset / tilt fields used for export
- Automatically creates an output folder named `<filename>_3dSliced` next to the mesh
- Sequential numbering of slices (`*_slice001.svg`, `*_slice002.svg`, …)
- SVG files include a `viewBox`, a Y-axis flip matching the on-screen preview, and a stroke width relative to the slice size
- Handles complex geometry:
  - Internal holes (exported as extra closed paths, unfilled)
  - Multiple disconnected contours in a single slice (e.g. a torus)
- Progress bar + log window; slicing runs off the UI thread so Cancel stays responsive
- Confirmation dialog replaces existing `*_slice*.svg` files only (the folder itself is not deleted)
- Resizable interface

---

## Requirements

- Python 3.8 or higher
- Windows / macOS / Linux
- Tkinter (included with most Python installers; on Debian/Ubuntu: `sudo apt install python3-tk`)

---

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/fhancy/3DSlicer.git
cd 3DSlicer
```

### 2. Create a virtual environment (recommended)
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install the required packages

```bash
pip install -r requirements.txt
```

Dependencies: `trimesh`, `numpy`, `scipy`, `svgwrite`, `matplotlib`. (`scipy` is required by trimesh for mesh sectioning.)

## How to Use

1) Run the script
```bash
python main.py
```

2) Click Browse and select a mesh file (`.stl`, `.obj`, `.ply`, …).

3) Set the parameters:
- Number of Slices
- Slice Direction (Horizontal / Vertical)
- Slice Offset (in model units) – recommended 0.5–2.0 to avoid empty edge slices
- Tilt Angle (degrees, around Y, pivoted at the mesh centroid)
- Output folder name (defaults to `<filename>_3dSliced`)

4) Drag **Slice Position** to preview a cut. Offset and tilt sliders update the same values used when exporting.

5) Click Start Slicing.
6) Find the generated SVG files in the folder next to your original 3D file.

## Example Output Structure
```bash
MyModel.stl
MyModel_3dSliced/
    MyModel_slice001.svg
    MyModel_slice002.svg
    MyModel_slice003.svg
    ...
```

SVG coordinates are in **mesh units**. The cutter / CAM tool must be told the same unit as the original model (often millimetres).

## Tips

Start with a small number of slices (5–10) when testing a new model.
Use a small Offset (e.g. 0.5–1.0) to avoid empty slices at the ends of the range.
Tilt is applied around the model centroid along the slice normal, so a non-zero angle stays centered on the part even if the STL is not at the world origin.
For models with internal cavities or holes, the tool writes multiple closed paths in the same SVG (`fill="none"`).
The log window reports how many polylines were saved per slice.

## Known Limitations

- Very large / high-poly meshes are slower to preview (the 3D view shows a subsample of faces) and to slice.
- Currently only exports SVG (DXF can be added later).
- There is no Y-axis slicing direction (only Z / X, plus tilt around Y).
- Interior holes are extra unfilled contours, not even-odd filled shapes.
- There is no conversion from mesh units to physical millimetres.
- The 3D camera is rotated in 45° azimuth steps (Rotate View), not a free orbit.

## License

MIT License – feel free to use, modify and distribute.
