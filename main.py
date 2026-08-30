import trimesh
import numpy as np
import svgwrite
from shapely.geometry import LineString, MultiLineString
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import shutil
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D


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
        self.fig_3d = None
        self.ax_3d = None
        self.view_angle = [30, 45]  # Initial elevation, azimuth
        self.cancel_flag = False
        self.setup_ui()
        self.update_visualization()

    def setup_ui(self):
        left_frame = ttk.Frame(self.root)
        left_frame.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")
        left_frame.grid_columnconfigure(0, weight=1)
        left_frame.grid_rowconfigure(1, weight=1)

        input_frame = ttk.LabelFrame(left_frame, text="Input and Parameters")
        input_frame.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        input_frame.grid_columnconfigure(1, weight=1)

        tk.Label(input_frame, text="STL File:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.stl_entry = tk.Entry(input_frame, width=30)
        self.stl_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        browse_button = ttk.Button(input_frame, text="Browse", command=self.browse_file)
        browse_button.grid(row=0, column=2, padx=5, pady=5)

        tk.Label(input_frame, text="Number of Slices:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.num_slices_entry = tk.Entry(input_frame, width=10)
        self.num_slices_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        self.num_slices_entry.insert(0, "10")

        tk.Label(input_frame, text="Slice Direction:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.direction_var = tk.StringVar(value="horizontal")
        tk.Radiobutton(input_frame, text="Horizontal (Z-axis)", variable=self.direction_var, value="horizontal",
                       command=self.update_visualization).grid(row=2, column=1, padx=5, pady=2, sticky="w")
        tk.Radiobutton(input_frame, text="Vertical (X-axis)", variable=self.direction_var, value="vertical",
                       command=self.update_visualization).grid(row=3, column=1, padx=5, pady=2, sticky="w")

        tk.Label(input_frame, text="Slice Offset (units):").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.offset_entry = tk.Entry(input_frame, width=10)
        self.offset_entry.grid(row=4, column=1, padx=5, pady=5, sticky="w")
        self.offset_entry.insert(0, "0")

        tk.Label(input_frame, text="Tilt Angle (degrees):").grid(row=5, column=0, padx=5, pady=5, sticky="w")
        self.angle_entry = tk.Entry(input_frame, width=10)
        self.angle_entry.grid(row=5, column=1, padx=5, pady=5, sticky="w")
        self.angle_entry.insert(0, "0")

        tk.Label(input_frame, text="Output Folder Name:").grid(row=6, column=0, padx=5, pady=5, sticky="w")
        self.folder_entry = tk.Entry(input_frame, width=20)
        self.folder_entry.grid(row=6, column=1, padx=5, pady=5, sticky="w")
        self.folder_entry.insert(0, "3Dsliced")

        slider_frame = ttk.LabelFrame(left_frame, text="Slice Preview")
        slider_frame.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        slider_frame.grid_columnconfigure(1, weight=1)

        tk.Label(slider_frame, text="Slice Position:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.position_slider = ttk.Scale(slider_frame, from_=-10, to=10, orient="horizontal",
                                         command=self.update_slice_preview)
        self.position_slider.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        tk.Label(slider_frame, text="Offset:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.offset_slider = ttk.Scale(slider_frame, from_=0, to=5, orient="horizontal",
                                       command=self.update_slice_preview)
        self.offset_slider.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.offset_slider.set(0)

        tk.Label(slider_frame, text="Tilt Angle:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.angle_slider = ttk.Scale(slider_frame, from_=-90, to=90, orient="horizontal",
                                      command=self.update_slice_preview)
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
        self.ax_3d = self.fig_3d.add_subplot(111, projection='3d')
        self.canvas_3d = FigureCanvasTkAgg(self.fig_3d, master=vis_frame)
        self.canvas_3d.get_tk_widget().grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        self.fig_2d = Figure(figsize=(6, 2))
        self.ax_2d = self.fig_2d.add_subplot(111)
        self.canvas_2d = FigureCanvasTkAgg(self.fig_2d, master=vis_frame)
        self.canvas_2d.get_tk_widget().grid(row=1, column=0, padx=5, pady=5, sticky="nsew")

        # View angle control
        view_frame = ttk.Frame(vis_frame)
        view_frame.grid(row=2, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(view_frame, text="Rotate View", command=self.rotate_view).grid(row=0, column=0, padx=5)

        button_frame = ttk.Frame(left_frame)
        button_frame.grid(row=3, column=0, pady=10)
        self.start_button = ttk.Button(button_frame, text="Start Slicing", command=self.start_slicing)
        self.start_button.grid(row=0, column=0, padx=5)
        self.cancel_button = ttk.Button(button_frame, text="Cancel", command=self.cancel_slicing, state="disabled")
        self.cancel_button.grid(row=0, column=1, padx=5)

    def rotate_view(self):
        self.view_angle[1] += 45  # Increment azimuth by 45 degrees
        self.update_visualization()

    def browse_file(self):
        file_path = filedialog.askopenfilename(
            title="Select STL File",
            filetypes=[("STL files", "*.stl"), ("All files", "*.*")]
        )
        if file_path:
            self.stl_entry.delete(0, tk.END)
            self.stl_entry.insert(0, os.path.normpath(file_path))
            self.log_status(f"Selected STL file: {file_path}")
            input_filename = os.path.splitext(os.path.basename(file_path))[0]
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, f"{input_filename}_3dSliced")
            self.load_stl(file_path)

    def load_stl(self, file_path):
        try:
            self.mesh = trimesh.load(file_path)
            self.bounds = self.mesh.bounds
            self.log_status(f"Loaded STL file: {file_path}")
            self.log_status(f"Mesh bounds: min={self.bounds[0]}, max={self.bounds[1]}")
            trimesh.repair.fix_normals(self.mesh)
            if not self.mesh.is_watertight:
                self.log_status("Warning: Mesh is not watertight, slicing may produce errors.")
            self.update_visualization()
        except Exception as e:
            self.log_status(f"Error loading STL file: {e}")

    def update_visualization(self):
        self.ax_3d.clear()
        if self.mesh:
            # Plot STL wireframe
            for face in self.mesh.faces[:1000]:  # Limit faces for performance
                points = self.mesh.vertices[face]
                x, y, z = points[:, 0], points[:, 1], points[:, 2]
                self.ax_3d.plot3D(x[[0, 1, 2, 0]], y[[0, 1, 2, 0]], z[[0, 1, 2, 0]], 'b-', alpha=0.5)

            # Set axis limits based on bounds
            self.ax_3d.set_xlim(self.bounds[0][0], self.bounds[1][0])
            self.ax_3d.set_ylim(self.bounds[0][1], self.bounds[1][1])
            self.ax_3d.set_zlim(self.bounds[0][2], self.bounds[1][2])
            self.ax_3d.set_xlabel('X')
            self.ax_3d.set_ylabel('Y')
            self.ax_3d.set_zlabel('Z')
            self.ax_3d.set_title("3D Model with Slice Plane")
            self.ax_3d.view_init(elev=self.view_angle[0], azim=self.view_angle[1])
            self.log_status("Updated 3D visualization")
        self.canvas_3d.draw()
        self.update_slice_preview()

    def update_slice_preview(self, *args):
        if not self.mesh:
            return
        try:
            position = float(self.position_slider.get())
            offset = float(self.offset_slider.get())
            tilt_angle = float(self.angle_slider.get())
            self.offset_entry.delete(0, tk.END)
            self.offset_entry.insert(0, str(offset))
            self.angle_entry.delete(0, tk.END)
            self.angle_entry.insert(0, str(tilt_angle))

            # Update 3D slice plane
            self.ax_3d.clear()
            if self.mesh:
                for face in self.mesh.faces[:1000]:
                    points = self.mesh.vertices[face]
                    x, y, z = points[:, 0], points[:, 1], points[:, 2]
                    self.ax_3d.plot3D(x[[0, 1, 2, 0]], y[[0, 1, 2, 0]], z[[0, 1, 2, 0]], 'b-', alpha=0.5)

                if self.direction_var.get() == "horizontal":
                    axis = 2
                    plane_normal = [np.sin(np.radians(tilt_angle)), 0, np.cos(np.radians(tilt_angle))]
                    plane_origin = [0, 0, position]
                    x = np.linspace(self.bounds[0][0], self.bounds[1][0], 10)
                    y = np.linspace(self.bounds[0][1], self.bounds[1][1], 10)
                    X, Y = np.meshgrid(x, y)
                    Z = position * np.ones_like(X)
                    self.ax_3d.plot_surface(X, Y, Z, color='r', alpha=0.3)
                else:
                    axis = 0
                    plane_normal = [np.cos(np.radians(tilt_angle)), 0, np.sin(np.radians(tilt_angle))]
                    plane_origin = [position, 0, 0]
                    y = np.linspace(self.bounds[0][1], self.bounds[1][1], 10)
                    z = np.linspace(self.bounds[0][2], self.bounds[1][2], 10)
                    Y, Z = np.meshgrid(y, z)
                    X = position * np.ones_like(Y)
                    self.ax_3d.plot_surface(X, Y, Z, color='r', alpha=0.3)

                self.ax_3d.set_xlim(self.bounds[0][0], self.bounds[1][0])
                self.ax_3d.set_ylim(self.bounds[0][1], self.bounds[1][1])
                self.ax_3d.set_zlim(self.bounds[0][2], self.bounds[1][2])
                self.ax_3d.set_xlabel('X')
                self.ax_3d.set_ylabel('Y')
                self.ax_3d.set_zlabel('Z')
                self.ax_3d.set_title("3D Model with Slice Plane")
                self.ax_3d.view_init(elev=self.view_angle[0], azim=self.view_angle[1])
                self.log_status("Updated 3D slice plane")

            # Compute and display 2D slice
            plane_normal = np.array(plane_normal)
            plane_origin = np.array(plane_origin)
            slice_2d = self.mesh.section(plane_normal=plane_normal, plane_origin=plane_origin)
            self.ax_2d.clear()
            if slice_2d and slice_2d.vertices.size:
                result = slice_2d.to_2D(normal=plane_normal, check=False)
                paths = result[0] if isinstance(result, tuple) else result
                if hasattr(paths, 'entities'):
                    for entity in paths.entities:
                        points = paths.vertices[entity.points]
                        self.ax_2d.plot(points[:, 0], points[:, 1], 'b-')
                self.ax_2d.set_title("Slice Preview")
                self.ax_2d.set_aspect('equal')
                self.log_status("Updated 2D slice preview")
            self.canvas_2d.draw()
            self.canvas_3d.draw()
        except Exception as e:
            self.log_status(f"Error updating slice preview: {e}")

    def log_status(self, message):
        self.status_text.config(state="normal")
        self.status_text.insert("end", message + "\n")
        self.status_text.see("end")
        self.status_text.config(state="disabled")

    def confirm_overwrite_folder(self, folder_path):
        try:
            if os.path.exists(folder_path):
                return messagebox.askyesno(
                    title="Folder Exists",
                    message=f"The folder '{folder_path}' already exists. Continuing will erase its contents. Proceed?"
                )
            return True
        except Exception as e:
            self.log_status(f"Error checking folder '{folder_path}': {e}")
            return False

    def slice_3d_model(self):
        stl_path = self.stl_entry.get().strip()
        if not stl_path or not os.path.exists(stl_path):
            self.log_status("Error: Please select a valid STL file.")
            return False

        try:
            num_slices = int(self.num_slices_entry.get())
            if num_slices <= 0:
                messagebox.showerror("Invalid Input", "Number of slices must be positive.")
                return False
            offset = float(self.offset_entry.get())
            if offset < 0:
                messagebox.showerror("Invalid Input", "Offset must be non-negative.")
                return False
            tilt_angle = float(self.angle_entry.get())
            direction = self.direction_var.get()
            output_folder_name = self.folder_entry.get().strip()
            if not output_folder_name:
                output_folder_name = f"{os.path.splitext(os.path.basename(stl_path))[0]}_3dSliced"
            if not output_folder_name.replace(" ", "").replace("_", "").isalnum():
                self.log_status("Error: Output folder name must be alphanumeric (spaces and underscores allowed).")
                return False
            self.log_status(
                f"Parameters: num_slices={num_slices}, direction={direction}, offset={offset}, tilt_angle={tilt_angle}, output_folder={output_folder_name}")
        except ValueError as e:
            messagebox.showerror("Invalid Input", "Number of slices, offset, and tilt angle must be numeric.")
            return False

        try:
            input_filename = os.path.splitext(os.path.basename(stl_path))[0]
            input_dir = os.path.dirname(stl_path) or '.'
            output_folder = os.path.normpath(os.path.join(input_dir, output_folder_name))
            self.log_status(f"Output folder: {output_folder}")
        except Exception as e:
            self.log_status(f"Error processing file path: {e}")
            return False

        try:
            if not self.confirm_overwrite_folder(output_folder):
                self.log_status("Operation cancelled by user.")
                return False
            if os.path.exists(output_folder):
                shutil.rmtree(output_folder)
            os.makedirs(output_folder)
            self.log_status(f"Created output folder: {output_folder}")
        except Exception as e:
            self.log_status(f"Error managing output folder: {e}")
            return False

        try:
            if direction == 'horizontal':
                axis = 2
                slice_min, slice_max = self.bounds[0][2] + offset, self.bounds[1][2] - offset
                if slice_min >= slice_max:
                    messagebox.showerror("Invalid Input",
                                         "Offset too large, reduces slicing range to zero or negative.")
                    return False
                angle_rad = np.radians(tilt_angle)
                plane_normal = [np.sin(angle_rad), 0, np.cos(angle_rad)]
            else:
                axis = 0
                slice_min, slice_max = self.bounds[0][0] + offset, self.bounds[1][0] - offset
                if slice_min >= slice_max:
                    messagebox.showerror("Invalid Input",
                                         "Offset too large, reduces slicing range to zero or negative.")
                    return False
                angle_rad = np.radians(tilt_angle)
                plane_normal = [np.cos(angle_rad), 0, np.sin(angle_rad)]
            self.log_status(f"Slicing: axis={axis}, range=({slice_min}, {slice_max}), plane_normal={plane_normal}")
            if abs(slice_max - slice_min) < 1e-6:
                self.log_status(f"Error: No range to slice on axis {axis}.")
                return False
        except Exception as e:
            self.log_status(f"Error setting slice parameters: {e}")
            return False

        try:
            slice_positions = np.linspace(slice_min, slice_max, num_slices + 1)[:-1]
            self.log_status(f"Slice positions: {slice_positions}")
        except Exception as e:
            self.log_status(f"Error calculating slice positions: {e}")
            return False

        self.progress_bar["maximum"] = len(slice_positions)
        self.progress_bar["value"] = 0
        self.cancel_flag = False
        self.start_button.config(state="disabled")
        self.cancel_button.config(state="normal")

        for i, pos in enumerate(slice_positions):
            if self.cancel_flag:
                self.log_status("Slicing cancelled by user.")
                break
            try:
                plane_origin = [0, 0, 0]
                plane_origin[axis] = pos
                plane_origin = np.array(plane_origin)
                plane_normal = np.array(plane_normal)

                slice_2d = self.mesh.section(plane_normal=plane_normal, plane_origin=plane_origin)
                if slice_2d is None or not slice_2d.vertices.size:
                    self.log_status(f"No intersection at slice {i + 1} (position={pos})")
                    self.progress_bar["value"] += 1
                    self.root.update()
                    continue

                self.log_status(f"Slice {i + 1}: {len(slice_2d.vertices)} vertices")

                try:
                    result = slice_2d.to_2D(normal=plane_normal, check=False)
                    self.log_status(f"Slice {i + 1}: to_2D result type: {type(result)}")
                except Exception as e:
                    self.log_status(f"Slice {i + 1}: Error in to_2D: {e}")
                    self.progress_bar["value"] += 1
                    self.root.update()
                    continue

                if isinstance(result, tuple):
                    paths = result[0]
                else:
                    paths = result

                if not hasattr(paths, 'entities'):
                    self.log_status(f"Slice {i + 1}: No entities attribute in paths: {type(paths)}")
                    self.progress_bar["value"] += 1
                    self.root.update()
                    continue

                self.log_status(f"Slice {i + 1}: {len(paths.entities)} polylines")
                if len(paths.entities) == 0:
                    self.log_status(f"Slice {i + 1}: No valid entities")
                    self.progress_bar["value"] += 1
                    self.root.update()
                    continue

                if not hasattr(paths, 'vertices') or not isinstance(paths.vertices,
                                                                    np.ndarray) or paths.vertices.ndim != 2 or \
                        paths.vertices.shape[1] != 2:
                    self.log_status(
                        f"Slice {i + 1}: Invalid vertices: {type(paths.vertices) if hasattr(paths, 'vertices') else 'None'}")
                    self.progress_bar["value"] += 1
                    self.root.update()
                    continue

                self.log_status(f"Slice {i + 1}: {len(paths.vertices)} vertices in paths")

                output_filename = os.path.normpath(
                    os.path.join(output_folder, f'{input_filename}_slice{i + 1:03d}.svg'))
                dwg = svgwrite.Drawing(output_filename, profile='tiny')
                paths_added = False

                for entity in paths.entities:
                    try:
                        indices = entity.points
                        if not isinstance(indices, np.ndarray) or indices.ndim != 1 or indices.size < 2:
                            self.log_status(
                                f"Slice {i + 1}: Invalid indices for entity: shape={indices.shape if isinstance(indices, np.ndarray) else type(indices)}, value={indices}")
                            continue

                        points = paths.vertices[indices]
                        if not isinstance(points, np.ndarray) or points.ndim != 2 or points.size < 2 or points.shape[
                            1] != 2:
                            self.log_status(
                                f"Slice {i + 1}: Invalid coordinates for entity: shape={points.shape if isinstance(points, np.ndarray) else type(points)}, value={points}")
                            continue

                        self.log_status(
                            f"Slice {i + 1}: Valid coordinates for entity (closed={entity.closed}): {points[:5]}... ({len(points)} points)")

                        path_data = f"M{points[0][0]},{points[0][1]}"
                        for pt in points[1:]:
                            path_data += f" L{pt[0]},{pt[1]}"
                        if entity.closed:
                            path_data += " Z"
                        dwg.add(dwg.path(d=path_data, fill='none', stroke='black', stroke_width=1))
                        paths_added = True
                    except Exception as e:
                        self.log_status(f"Slice {i + 1}: Error processing entity: {e}")
                        continue

                if paths_added:
                    try:
                        dwg.save()
                        self.log_status(f"Saved slice {i + 1} as {output_filename}")
                    except Exception as e:
                        self.log_status(f"Error saving SVG for slice {i + 1}: {e}")
                else:
                    self.log_status(f"Slice {i + 1}: skipped: no valid paths to save")

                self.progress_bar["value"] += 1
                self.root.update()
            except Exception as e:
                self.log_status(f"Error processing slice {i + 1}: {e}")
                self.progress_bar["value"] += 1
                self.root.update()
                continue

        messagebox.showinfo("Slicing Complete", "Slicing process completed successfully!")
        self.log_status("Process finished.")
        self.start_button.config(state="normal")
        self.cancel_button.config(state="disabled")
        return True

    def start_slicing(self):
        self.cancel_flag = False
        success = self.slice_3d_model()
        if not success:
            self.log_status("Process aborted.")
            self.start_button.config(state="normal")
            self.cancel_button.config(state="disabled")

    def cancel_slicing(self):
        self.cancel_flag = True


if __name__ == "__main__":
    """
    Setup Instructions for Windows 11:
    1. Install dependencies:
       pip install trimesh numpy scipy svgwrite shapely matplotlib
    2. Verify Python version (3.8–3.10 recommended):
       python --version
    3. Run in PyCharm with the torus STL.
    """
    root = tk.Tk()
    app = SlicerApp(root)
    root.mainloop()