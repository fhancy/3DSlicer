#!/usr/bin/env python3
"""3D Slicer: slice a mesh into numbered SVG cross-sections."""

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
import svgwrite
import trimesh
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

MAX_PREVIEW_FACES = 4000
PREVIEW_DEBOUNCE_MS = 80
MESH_FILETYPES = [
    ("3D meshes", "*.stl *.obj *.ply *.off *.glb *.gltf *.3mf"),
    ("STL files", "*.stl"),
    ("OBJ files", "*.obj"),
    ("PLY files", "*.ply"),
    ("All files", "*.*"),
]


def as_trimesh(loaded):
    """Return a single Trimesh from a load() result (mesh or scene)."""
    if isinstance(loaded, trimesh.Trimesh):
        return loaded
    if isinstance(loaded, trimesh.Scene):
        geoms = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not geoms:
            raise ValueError("No triangular mesh geometry found in the file.")
        if len(geoms) == 1:
            return geoms[0]
        return trimesh.util.concatenate(geoms)
    raise ValueError(f"Unsupported geometry type: {type(loaded).__name__}")


def plane_normal(direction, tilt_deg):
    """Unit plane normal. Horizontal defaults to +Z, vertical to +X; tilt is around Y."""
    angle = np.radians(float(tilt_deg))
    if direction == "horizontal":
        normal = np.array([np.sin(angle), 0.0, np.cos(angle)], dtype=np.float64)
    else:
        normal = np.array([np.cos(angle), 0.0, np.sin(angle)], dtype=np.float64)
    norm = np.linalg.norm(normal)
    if norm < 1e-15:
        raise ValueError("Degenerate plane normal.")
    return normal / norm


def plane_basis(normal):
    """Two orthonormal vectors spanning the plane with the given unit normal."""
    n = np.asarray(normal, dtype=np.float64)
    helper = np.array([0.0, 1.0, 0.0]) if abs(n[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(n, helper)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    v /= np.linalg.norm(v)
    return u, v


def compute_plane(mesh, direction, tilt_deg, offset=0.0):
    """
    Shared slice geometry.

    Heights are signed distances along the normal from the mesh centroid.
    Projection range is vertex · n in world units.
    """
    normal = plane_normal(direction, tilt_deg)
    origin = np.asarray(mesh.centroid, dtype=np.float64)
    projections = mesh.vertices @ normal
    proj_min = float(projections.min())
    proj_max = float(projections.max())
    origin_proj = float(np.dot(origin, normal))
    offset = max(float(offset), 0.0)
    # Tiny inset so planes do not sit exactly on AABB faces (those sections are often empty).
    span = max(proj_max - proj_min, 0.0)
    numeric_inset = max(span * 1e-4, 1e-9)
    height_min = (proj_min + offset + numeric_inset) - origin_proj
    height_max = (proj_max - offset - numeric_inset) - origin_proj
    return {
        "normal": normal,
        "origin": origin,
        "proj_min": proj_min,
        "proj_max": proj_max,
        "origin_proj": origin_proj,
        "height_min": height_min,
        "height_max": height_max,
        "extent": proj_max - proj_min,
    }


def slice_heights(height_min, height_max, num_slices):
    """Evenly spaced heights along the normal, including both ends (midpoint if n=1)."""
    num_slices = int(num_slices)
    if num_slices <= 0:
        raise ValueError("Number of slices must be positive.")
    if num_slices == 1:
        return np.array([(height_min + height_max) / 2.0], dtype=np.float64)
    return np.linspace(height_min, height_max, num_slices)


def point_on_plane(origin, normal, height):
    return np.asarray(origin, dtype=np.float64) + np.asarray(normal, dtype=np.float64) * float(height)


def entity_polyline(entity, vertices):
    """Vertex array for a path entity (works if .points is a list or ndarray)."""
    if hasattr(entity, "discrete"):
        points = np.asarray(entity.discrete(vertices), dtype=np.float64)
    else:
        indices = np.asarray(entity.points).ravel()
        if indices.size < 2:
            return None
        points = np.asarray(vertices, dtype=np.float64)[indices]
    if points.ndim != 2 or points.shape[0] < 2 or points.shape[1] < 2:
        return None
    return points[:, :2]


def iter_polylines(path2d):
    if path2d is None or not hasattr(path2d, "entities") or not hasattr(path2d, "vertices"):
        return
    vertices = np.asarray(path2d.vertices)
    for entity in path2d.entities:
        points = entity_polyline(entity, vertices)
        if points is None:
            continue
        closed = bool(getattr(entity, "closed", False))
        yield points, closed


def write_slice_svg(filepath, path2d, flip_y=True):
    """Write a Path2D as SVG with viewBox, Y flipped to match matplotlib, relative stroke."""
    polylines = list(iter_polylines(path2d))
    if not polylines:
        return False

    prepared = []
    all_pts = []
    for points, closed in polylines:
        pts = points.copy()
        if flip_y:
            pts[:, 1] = -pts[:, 1]
        prepared.append((pts, closed))
        all_pts.append(pts)

    stacked = np.vstack(all_pts)
    minx, miny = stacked.min(axis=0)
    maxx, maxy = stacked.max(axis=0)
    width = float(max(maxx - minx, 1e-9))
    height = float(max(maxy - miny, 1e-9))
    pad = 0.05 * max(width, height)
    vb_x = minx - pad
    vb_y = miny - pad
    vb_w = width + 2 * pad
    vb_h = height + 2 * pad
    stroke = max(width, height) * 0.003

    drawing = svgwrite.Drawing(
        filepath,
        profile="tiny",
        size=(f"{vb_w}", f"{vb_h}"),
    )
    drawing.viewbox(vb_x, vb_y, vb_w, vb_h)

    for pts, closed in prepared:
        commands = [f"M{pts[0, 0]},{pts[0, 1]}"]
        commands.extend(f"L{x},{y}" for x, y in pts[1:])
        if closed:
            commands.append("Z")
        drawing.add(
            drawing.path(
                d=" ".join(commands),
                fill="none",
                stroke="black",
                stroke_width=stroke,
            )
        )
    drawing.save()
    return True


def is_valid_folder_name(name):
    if not name or name in (".", ".."):
        return False
    if os.path.sep in name or (os.path.altsep and os.path.altsep in name):
        return False
    return True


def existing_slice_svgs(folder, stem):
    if not os.path.isdir(folder):
        return []
    prefix = f"{stem}_slice"
    return sorted(
        os.path.join(folder, name)
        for name in os.listdir(folder)
        if name.startswith(prefix) and name.endswith(".svg")
    )


def remove_slice_svgs(folder, stem):
    for path in existing_slice_svgs(folder, stem):
        os.remove(path)


def cleanup_partial_svgs(folder, stem):
    if not os.path.isdir(folder):
        return
    prefix = f"{stem}_slice"
    for name in os.listdir(folder):
        if name.startswith(prefix) and name.endswith(".svg.partial"):
            os.remove(os.path.join(folder, name))


class SlicerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("3D Slicer")
        self.root.geometry("1200x700")
        self.root.minsize(800, 600)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=2)
        self.root.grid_rowconfigure(0, weight=1)

        self.mesh = None
        self.bounds = None
        self.view_angle = [30, 45]
        self._mesh_poly_verts = None
        self._preview_after_id = None
        self._syncing_ui = False
        self._cancel_event = threading.Event()
        self._worker = None
        self._slicing = False
        self._ui_queue = queue.Queue()

        self.setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._draw_empty_views()

    def setup_ui(self):
        left_frame = ttk.Frame(self.root)
        left_frame.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")
        left_frame.grid_columnconfigure(0, weight=1)
        left_frame.grid_rowconfigure(2, weight=1)

        input_frame = ttk.LabelFrame(left_frame, text="Input and Parameters")
        input_frame.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        input_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(input_frame, text="Mesh File:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.stl_entry = tk.Entry(input_frame, width=30)
        self.stl_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Button(input_frame, text="Browse", command=self.browse_file).grid(
            row=0, column=2, padx=5, pady=5
        )

        ttk.Label(input_frame, text="Number of Slices:").grid(
            row=1, column=0, padx=5, pady=5, sticky="w"
        )
        self.num_slices_entry = tk.Entry(input_frame, width=10)
        self.num_slices_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        self.num_slices_entry.insert(0, "10")

        ttk.Label(input_frame, text="Slice Direction:").grid(
            row=2, column=0, padx=5, pady=5, sticky="w"
        )
        self.direction_var = tk.StringVar(value="horizontal")
        ttk.Radiobutton(
            input_frame,
            text="Horizontal (Z-axis)",
            variable=self.direction_var,
            value="horizontal",
            command=self._on_direction_change,
        ).grid(row=2, column=1, padx=5, pady=2, sticky="w")
        ttk.Radiobutton(
            input_frame,
            text="Vertical (X-axis)",
            variable=self.direction_var,
            value="vertical",
            command=self._on_direction_change,
        ).grid(row=3, column=1, padx=5, pady=2, sticky="w")

        ttk.Label(input_frame, text="Slice Offset (units):").grid(
            row=4, column=0, padx=5, pady=5, sticky="w"
        )
        self.offset_entry = tk.Entry(input_frame, width=10)
        self.offset_entry.grid(row=4, column=1, padx=5, pady=5, sticky="w")
        self.offset_entry.insert(0, "0")
        self.offset_entry.bind("<FocusOut>", self._on_offset_entry)
        self.offset_entry.bind("<Return>", self._on_offset_entry)

        ttk.Label(input_frame, text="Tilt Angle (degrees):").grid(
            row=5, column=0, padx=5, pady=5, sticky="w"
        )
        self.angle_entry = tk.Entry(input_frame, width=10)
        self.angle_entry.grid(row=5, column=1, padx=5, pady=5, sticky="w")
        self.angle_entry.insert(0, "0")
        self.angle_entry.bind("<FocusOut>", self._on_angle_entry)
        self.angle_entry.bind("<Return>", self._on_angle_entry)

        ttk.Label(input_frame, text="Output Folder Name:").grid(
            row=6, column=0, padx=5, pady=5, sticky="w"
        )
        self.folder_entry = tk.Entry(input_frame, width=20)
        self.folder_entry.grid(row=6, column=1, padx=5, pady=5, sticky="w")
        self.folder_entry.insert(0, "3Dsliced")

        slider_frame = ttk.LabelFrame(left_frame, text="Slice Preview")
        slider_frame.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        slider_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(slider_frame, text="Slice Position:").grid(
            row=0, column=0, padx=5, pady=5, sticky="w"
        )
        self.position_slider = ttk.Scale(
            slider_frame,
            from_=-10,
            to=10,
            orient="horizontal",
            command=self._on_slider_change,
        )
        self.position_slider.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(slider_frame, text="Offset:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.offset_slider = ttk.Scale(
            slider_frame, from_=0, to=5, orient="horizontal", command=self._on_offset_slider
        )
        self.offset_slider.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.offset_slider.set(0)

        ttk.Label(slider_frame, text="Tilt Angle:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.angle_slider = ttk.Scale(
            slider_frame, from_=-90, to=90, orient="horizontal", command=self._on_angle_slider
        )
        self.angle_slider.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        self.angle_slider.set(0)

        progress_frame = ttk.LabelFrame(left_frame, text="Progress")
        progress_frame.grid(row=2, column=0, padx=5, pady=5, sticky="nsew")
        progress_frame.grid_columnconfigure(0, weight=1)
        progress_frame.grid_rowconfigure(1, weight=1)

        self.progress_bar = ttk.Progressbar(progress_frame, orient="horizontal", mode="determinate")
        self.progress_bar.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        self.status_text = tk.Text(progress_frame, height=15, width=40, state="disabled")
        self.status_text.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")
        scrollbar = ttk.Scrollbar(progress_frame, orient="vertical", command=self.status_text.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.status_text.configure(yscrollcommand=scrollbar.set)

        vis_frame = ttk.LabelFrame(self.root, text="3D Visualization")
        vis_frame.grid(row=0, column=1, padx=10, pady=5, sticky="nsew")
        vis_frame.grid_columnconfigure(0, weight=1)
        vis_frame.grid_rowconfigure(0, weight=3)
        vis_frame.grid_rowconfigure(1, weight=1)
        vis_frame.grid_rowconfigure(2, weight=0)

        self.fig_3d = Figure(figsize=(6, 4))
        self.ax_3d = self.fig_3d.add_subplot(111, projection="3d")
        self.canvas_3d = FigureCanvasTkAgg(self.fig_3d, master=vis_frame)
        self.canvas_3d.get_tk_widget().grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        self.fig_2d = Figure(figsize=(6, 2))
        self.ax_2d = self.fig_2d.add_subplot(111)
        self.canvas_2d = FigureCanvasTkAgg(self.fig_2d, master=vis_frame)
        self.canvas_2d.get_tk_widget().grid(row=1, column=0, padx=5, pady=5, sticky="nsew")

        view_frame = ttk.Frame(vis_frame)
        view_frame.grid(row=2, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(view_frame, text="Rotate View", command=self.rotate_view).grid(
            row=0, column=0, padx=5
        )

        button_frame = ttk.Frame(left_frame)
        button_frame.grid(row=3, column=0, pady=10)
        self.start_button = ttk.Button(button_frame, text="Start Slicing", command=self.start_slicing)
        self.start_button.grid(row=0, column=0, padx=5)
        self.cancel_button = ttk.Button(
            button_frame, text="Cancel", command=self.cancel_slicing, state="disabled"
        )
        self.cancel_button.grid(row=0, column=1, padx=5)

    def _on_close(self):
        self._cancel_event.set()
        self.root.destroy()

    def rotate_view(self):
        self.view_angle[1] = (self.view_angle[1] + 45) % 360
        self.ax_3d.view_init(elev=self.view_angle[0], azim=self.view_angle[1])
        self.canvas_3d.draw_idle()

    def browse_file(self):
        file_path = filedialog.askopenfilename(
            title="Select mesh file",
            filetypes=MESH_FILETYPES,
        )
        if not file_path:
            return
        self.stl_entry.delete(0, tk.END)
        self.stl_entry.insert(0, os.path.normpath(file_path))
        self.log_status(f"Selected file: {file_path}")
        input_filename = os.path.splitext(os.path.basename(file_path))[0]
        self.folder_entry.delete(0, tk.END)
        self.folder_entry.insert(0, f"{input_filename}_3dSliced")
        self.load_mesh(file_path)

    def load_mesh(self, file_path):
        try:
            loaded = trimesh.load(file_path, force="mesh")
            self.mesh = as_trimesh(loaded)
            self.bounds = np.asarray(self.mesh.bounds, dtype=np.float64)
            self._prepare_mesh_viz()
            self.log_status(f"Loaded mesh: {file_path}")
            self.log_status(f"Mesh bounds: min={self.bounds[0]}, max={self.bounds[1]}")
            try:
                trimesh.repair.fix_normals(self.mesh)
            except Exception as exc:
                self.log_status(f"Could not fix normals: {exc}")
            if not self.mesh.is_watertight:
                self.log_status("Warning: Mesh is not watertight, slicing may produce gaps.")
            self._refresh_slider_ranges(reset_position=True)
            self.update_slice_preview()
        except Exception as exc:
            self.mesh = None
            self.bounds = None
            self._mesh_poly_verts = None
            self.log_status(f"Error loading mesh: {exc}")

    def _prepare_mesh_viz(self):
        faces = self.mesh.faces
        if len(faces) > MAX_PREVIEW_FACES:
            rng = np.random.default_rng(0)
            faces = faces[rng.choice(len(faces), MAX_PREVIEW_FACES, replace=False)]
        self._mesh_poly_verts = self.mesh.vertices[faces]

    def _on_direction_change(self):
        if not self.mesh:
            return
        self._refresh_slider_ranges(reset_position=True)
        self.update_slice_preview()

    def _on_slider_change(self, *_args):
        if self._syncing_ui:
            return
        self._schedule_preview()

    def _on_offset_slider(self, *_args):
        if self._syncing_ui:
            return
        self._set_entry(self.offset_entry, self._fmt_num(self.offset_slider.get()))
        self._refresh_slider_ranges(reset_position=False)
        self._schedule_preview()

    def _on_angle_slider(self, *_args):
        if self._syncing_ui:
            return
        self._set_entry(self.angle_entry, self._fmt_num(self.angle_slider.get()))
        self._refresh_slider_ranges(reset_position=True)
        self._schedule_preview()

    def _on_offset_entry(self, *_args):
        try:
            offset = max(float(self.offset_entry.get()), 0.0)
        except ValueError:
            return
        self._syncing_ui = True
        try:
            slider_max = float(self.offset_slider.cget("to"))
            self.offset_slider.set(min(offset, slider_max))
        finally:
            self._syncing_ui = False
        if self.mesh:
            self._refresh_slider_ranges(reset_position=False)
            self.update_slice_preview()

    def _on_angle_entry(self, *_args):
        try:
            angle = float(self.angle_entry.get())
        except ValueError:
            return
        self._syncing_ui = True
        try:
            self.angle_slider.set(max(-90.0, min(90.0, angle)))
        finally:
            self._syncing_ui = False
        if self.mesh:
            self._refresh_slider_ranges(reset_position=True)
            self.update_slice_preview()

    def _schedule_preview(self):
        if self._preview_after_id is not None:
            self.root.after_cancel(self._preview_after_id)
        self._preview_after_id = self.root.after(PREVIEW_DEBOUNCE_MS, self.update_slice_preview)

    def _plane_from_ui(self, offset=None, tilt_deg=None):
        if offset is None:
            offset = float(self.offset_entry.get() or 0)
        if tilt_deg is None:
            tilt_deg = float(self.angle_entry.get() or 0)
        return compute_plane(self.mesh, self.direction_var.get(), tilt_deg, offset)

    def _refresh_slider_ranges(self, reset_position=False):
        if not self.mesh:
            return
        try:
            offset = max(float(self.offset_entry.get() or 0), 0.0)
            tilt_deg = float(self.angle_entry.get() or 0)
            plane = compute_plane(self.mesh, self.direction_var.get(), tilt_deg, offset)
        except (ValueError, TypeError):
            return

        usable_min = plane["origin_proj"] + plane["height_min"]
        usable_max = plane["origin_proj"] + plane["height_max"]
        if usable_min >= usable_max:
            mid = (plane["proj_min"] + plane["proj_max"]) / 2.0
            usable_min = usable_max = mid

        self._syncing_ui = True
        try:
            current = plane["origin_proj"] if reset_position else float(self.position_slider.get())
            current = min(max(current, usable_min), usable_max)
            self.position_slider.configure(from_=usable_min, to=usable_max)
            self.position_slider.set(current)
            extent = max(plane["extent"] * 0.49, 1e-9)
            self.offset_slider.configure(from_=0, to=extent)
            self.offset_slider.set(min(offset, extent))
        finally:
            self._syncing_ui = False

    def _draw_empty_views(self):
        self.ax_3d.clear()
        self.ax_3d.set_title("3D Model with Slice Plane")
        self.ax_3d.set_xlabel("X")
        self.ax_3d.set_ylabel("Y")
        self.ax_3d.set_zlabel("Z")
        self.canvas_3d.draw_idle()
        self.ax_2d.clear()
        self.ax_2d.set_title("Slice Preview")
        self.canvas_2d.draw_idle()

    def _set_3d_limits(self):
        spans = self.bounds[1] - self.bounds[0]
        max_span = float(np.max(spans))
        if max_span <= 0:
            max_span = 1.0
        centers = (self.bounds[0] + self.bounds[1]) / 2.0
        half = max_span / 2.0
        self.ax_3d.set_xlim(centers[0] - half, centers[0] + half)
        self.ax_3d.set_ylim(centers[1] - half, centers[1] + half)
        self.ax_3d.set_zlim(centers[2] - half, centers[2] + half)
        try:
            self.ax_3d.set_box_aspect((1, 1, 1))
        except Exception:
            pass

    def _draw_mesh_and_plane(self, plane_point, normal):
        self.ax_3d.clear()
        if self._mesh_poly_verts is not None:
            collection = Poly3DCollection(
                self._mesh_poly_verts,
                alpha=0.18,
                facecolor="cornflowerblue",
                edgecolor="navy",
                linewidths=0.08,
            )
            self.ax_3d.add_collection3d(collection)

        u, v = plane_basis(normal)
        extent = float(np.linalg.norm(self.bounds[1] - self.bounds[0])) * 0.55
        samples = np.linspace(-extent, extent, 8)
        s_grid, t_grid = np.meshgrid(samples, samples)
        x = plane_point[0] + u[0] * s_grid + v[0] * t_grid
        y = plane_point[1] + u[1] * s_grid + v[1] * t_grid
        z = plane_point[2] + u[2] * s_grid + v[2] * t_grid
        self.ax_3d.plot_surface(x, y, z, color="r", alpha=0.35, linewidth=0, antialiased=True)

        self._set_3d_limits()
        self.ax_3d.set_xlabel("X")
        self.ax_3d.set_ylabel("Y")
        self.ax_3d.set_zlabel("Z")
        self.ax_3d.set_title("3D Model with Slice Plane")
        self.ax_3d.view_init(elev=self.view_angle[0], azim=self.view_angle[1])

    def update_slice_preview(self, *_args):
        self._preview_after_id = None
        if not self.mesh:
            return
        try:
            plane = self._plane_from_ui()
            position = float(self.position_slider.get())
            height = position - plane["origin_proj"]
            plane_point = point_on_plane(plane["origin"], plane["normal"], height)
            self._draw_mesh_and_plane(plane_point, plane["normal"])

            sections = self.mesh.section_multiplane(
                plane_origin=plane["origin"],
                plane_normal=plane["normal"],
                heights=[height],
            )
            self.ax_2d.clear()
            self.ax_2d.set_title("Slice Preview")
            path2d = sections[0] if sections else None
            if path2d is not None:
                for points, _closed in iter_polylines(path2d):
                    self.ax_2d.plot(points[:, 0], points[:, 1], "b-")
                self.ax_2d.set_aspect("equal")
            self.canvas_2d.draw_idle()
            self.canvas_3d.draw_idle()
        except Exception as exc:
            self.log_status(f"Error updating slice preview: {exc}")

    def log_status(self, message):
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        self.status_text.config(state="normal")
        self.status_text.insert("end", message + "\n")
        self.status_text.see("end")
        self.status_text.config(state="disabled")

    @staticmethod
    def _fmt_num(value):
        text = f"{float(value):.4f}".rstrip("0").rstrip(".")
        return text if text else "0"

    def _set_entry(self, entry, text):
        entry.delete(0, tk.END)
        entry.insert(0, text)

    def _ui(self, func):
        """Schedule a callable on the Tk thread (safe from the worker)."""
        self._ui_queue.put(func)

    def _drain_ui_queue(self):
        try:
            while True:
                func = self._ui_queue.get_nowait()
                try:
                    func()
                except tk.TclError:
                    return
        except queue.Empty:
            pass
        if self._slicing or not self._ui_queue.empty():
            self.root.after(50, self._drain_ui_queue)

    def start_slicing(self):
        if self._slicing:
            return
        params = self._collect_slice_params()
        if params is None:
            return

        output_folder = params["output_folder"]
        stem = params["stem"]
        existing = existing_slice_svgs(output_folder, stem)
        if existing:
            if not messagebox.askyesno(
                title="Slice files exist",
                message=(
                    f"The folder '{output_folder}' already contains {len(existing)} slice SVG file(s). "
                    "They will be replaced. Other files in the folder will be left untouched. Proceed?"
                ),
            ):
                self.log_status("Operation cancelled by user.")
                return

        self._cancel_event.clear()
        self._slicing = True
        while True:
            try:
                self._ui_queue.get_nowait()
            except queue.Empty:
                break
        self.start_button.config(state="disabled")
        self.cancel_button.config(state="normal")
        self.progress_bar["maximum"] = params["num_slices"]
        self.progress_bar["value"] = 0
        self.root.after(50, self._drain_ui_queue)
        self._worker = threading.Thread(target=self._slice_worker, args=(params,), daemon=True)
        self._worker.start()

    def _collect_slice_params(self):
        mesh_path = self.stl_entry.get().strip()
        if not mesh_path or not os.path.exists(mesh_path):
            self.log_status("Error: Please select a valid mesh file.")
            return None
        if self.mesh is None:
            self.log_status("Error: No mesh loaded.")
            return None

        try:
            num_slices = int(self.num_slices_entry.get())
            if num_slices <= 0:
                messagebox.showerror("Invalid Input", "Number of slices must be positive.")
                return None
            offset = float(self.offset_entry.get())
            if offset < 0:
                messagebox.showerror("Invalid Input", "Offset must be non-negative.")
                return None
            tilt_angle = float(self.angle_entry.get())
        except ValueError:
            messagebox.showerror(
                "Invalid Input", "Number of slices, offset, and tilt angle must be numeric."
            )
            return None

        direction = self.direction_var.get()
        output_folder_name = self.folder_entry.get().strip()
        if not output_folder_name:
            output_folder_name = f"{os.path.splitext(os.path.basename(mesh_path))[0]}_3dSliced"
        if not is_valid_folder_name(output_folder_name):
            self.log_status("Error: Output folder name cannot contain path separators.")
            return None

        try:
            plane = self._plane_from_ui(offset=offset, tilt_deg=tilt_angle)
        except Exception as exc:
            self.log_status(f"Error setting slice parameters: {exc}")
            return None

        if plane["height_min"] >= plane["height_max"] - 1e-12:
            messagebox.showerror(
                "Invalid Input",
                "Offset too large, reduces slicing range to zero or negative.",
            )
            return None

        heights = slice_heights(plane["height_min"], plane["height_max"], num_slices)
        stem = os.path.splitext(os.path.basename(mesh_path))[0]
        input_dir = os.path.dirname(mesh_path) or "."
        output_folder = os.path.normpath(os.path.join(input_dir, output_folder_name))

        self.log_status(
            f"Parameters: num_slices={num_slices}, direction={direction}, "
            f"offset={offset}, tilt_angle={tilt_angle}, output_folder={output_folder_name}"
        )
        self.log_status(f"Output folder: {output_folder}")
        self.log_status(
            f"Slicing along normal={plane['normal']}, "
            f"height range=({plane['height_min']}, {plane['height_max']})"
        )
        return {
            "mesh": self.mesh,
            "plane": plane,
            "heights": heights,
            "num_slices": num_slices,
            "output_folder": output_folder,
            "stem": stem,
        }

    def _slice_worker(self, params):
        output_folder = params["output_folder"]
        stem = params["stem"]
        plane = params["plane"]
        heights = params["heights"]
        mesh = params["mesh"]
        saved = 0
        skipped = 0
        errors = 0

        try:
            os.makedirs(output_folder, exist_ok=True)
            cleanup_partial_svgs(output_folder, stem)
            self._ui(lambda: self.log_status(f"Computing {len(heights)} parallel slices..."))

            sections = mesh.section_multiplane(
                plane_origin=plane["origin"],
                plane_normal=plane["normal"],
                heights=heights,
            )

            if self._cancel_event.is_set():
                cleanup_partial_svgs(output_folder, stem)
                self._ui(lambda: self._finish_slicing("cancelled", saved, skipped, errors))
                return

            total = len(sections)
            partials = []
            for index, path2d in enumerate(sections):
                if self._cancel_event.is_set():
                    cleanup_partial_svgs(output_folder, stem)
                    self._ui(lambda: self._finish_slicing("cancelled", saved, skipped, errors))
                    return

                slice_num = index + 1
                output_filename = os.path.join(output_folder, f"{stem}_slice{slice_num:03d}.svg")
                partial_filename = output_filename + ".partial"

                if path2d is None or not hasattr(path2d, "entities") or len(path2d.entities) == 0:
                    skipped += 1
                    msg = f"No intersection at slice {slice_num}"
                    self._ui(lambda s=slice_num, m=msg, t=total: self._report_progress(s, t, m))
                    continue

                try:
                    wrote = write_slice_svg(partial_filename, path2d, flip_y=True)
                except Exception as exc:
                    errors += 1
                    msg = f"Error saving SVG for slice {slice_num}: {exc}"
                    self._ui(lambda s=slice_num, m=msg, t=total: self._report_progress(s, t, m))
                    continue

                if wrote:
                    saved += 1
                    partials.append((partial_filename, output_filename))
                    msg = f"Saved slice {slice_num} as {output_filename} ({len(path2d.entities)} polylines)"
                else:
                    skipped += 1
                    msg = f"Slice {slice_num}: skipped, no valid paths"
                self._ui(lambda s=slice_num, m=msg, t=total: self._report_progress(s, t, m))

            if self._cancel_event.is_set():
                cleanup_partial_svgs(output_folder, stem)
                self._ui(lambda: self._finish_slicing("cancelled", saved, skipped, errors))
                return

            if errors and saved == 0:
                cleanup_partial_svgs(output_folder, stem)
                self._ui(lambda: self._finish_slicing("error", saved, skipped, errors))
                return

            remove_slice_svgs(output_folder, stem)
            for partial_filename, output_filename in partials:
                os.replace(partial_filename, output_filename)
            self._ui(lambda: self._finish_slicing("success", saved, skipped, errors))
        except Exception as exc:
            cleanup_partial_svgs(output_folder, stem)
            self._ui(lambda: self._finish_slicing("error", saved, skipped, errors, str(exc)))

    def _report_progress(self, current, total, message):
        self.progress_bar["maximum"] = total
        self.progress_bar["value"] = current
        self.log_status(message)

    def _finish_slicing(self, status, saved, skipped, errors, error_message=None):
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        self._slicing = False
        self.start_button.config(state="normal")
        self.cancel_button.config(state="disabled")
        summary = f"Saved {saved} slice(s), skipped {skipped}, errors {errors}."
        if status == "cancelled":
            self.log_status("Slicing cancelled by user. " + summary)
            messagebox.showinfo("Slicing Cancelled", "Slicing was cancelled.\n" + summary)
        elif status == "error":
            detail = error_message or "See the log for details."
            self.log_status("Slicing failed. " + summary + f" {detail}")
            messagebox.showerror("Slicing Failed", f"{detail}\n{summary}")
        else:
            self.log_status("Process finished. " + summary)
            messagebox.showinfo("Slicing Complete", "Slicing process completed.\n" + summary)

    def cancel_slicing(self):
        self._cancel_event.set()
        self.log_status("Cancel requested...")


def main():
    root = tk.Tk()
    SlicerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
