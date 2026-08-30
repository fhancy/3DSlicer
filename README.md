# 3D Slicer

A user-friendly Python tool that slices 3D mesh files (STL and other formats supported by `trimesh`) into numbered 2D vector files (SVG).

Perfect for laser cutting, CNC, paper models, or any workflow that needs sequential 2D cross-sections of a 3D object.

---

## Features

- **Simple graphical interface** (Tkinter)
- Load STL files (and other formats supported by `trimesh`)
- Choose number of slices
- Horizontal (Z-axis) or Vertical (X-axis) slicing
- **Slice Offset** – avoid empty or degenerate slices near the extremities
- **Tilt Angle** – cut the model at an arbitrary angle
- Automatically creates an output folder named `<filename>_3dSliced`
- Sequential numbering of slices (`*_slice001.svg`, `*_slice002.svg`, …)
- Handles complex geometry:
  - Internal holes
  - Multiple disconnected contours in a single slice (e.g. a torus)
- Progress bar + detailed log window
- Confirmation dialog when the output folder already exists
- Resizable interface

---

## Requirements

- Python 3.8 or higher
- Windows / macOS / Linux

---

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/3DSlicer.git
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
requirements.txt:

trimesh>=4.0.0
numpy>=1.24.0
scipy>=1.10.0
svgwrite>=1.4.3
shapely>=2.0.0

## How to Use

1) Run the script
```bash
python main.py
```

2) Click Browse and select your .stl file.

3) Set the parameters:
- Number of Slices
- Slice Direction (Horizontal / Vertical)
- Slice Offset (in model units) – recommended 0.5–2.0 to avoid empty edge slices
- Tilt Angle (degrees)
- Output folder name (defaults to <filename>_3dSliced)

4) Click Start Slicing.
5) Find the generated SVG files in the folder next to your original 3D file.

## Example Output Structure

MyModel.stl
└── MyModel_3dSliced/
    ├── MyModel_slice001.svg
    ├── MyModel_slice002.svg    
    ├── MyModel_slice003.svg    
    └── ...


## Tips

Start with a small number of slices (5–10) when testing a new model.
Use a small Offset (e.g. 0.5–1.0) to avoid empty slices at the top and bottom.
For models with internal cavities or holes, the tool correctly generates multiple closed paths in the same SVG.
The log window shows detailed information about each slice (number of vertices, polylines, etc.).

## Known Limitations

Very large / high-poly meshes can be slow.
Currently only exports SVG (DXF support can be added later).
Visualization of the 3D model is not yet available in the stable version.

## License

MIT License – feel free to use, modify and distribute.
    
