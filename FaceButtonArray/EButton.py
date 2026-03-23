"""
╔══════════════════════════════════════════════════════════════════════╗
║   TEXT FILE → build123d GEOMETRY                                    ║
║   Reads ExtButtonArray_vertices_triangles.txt, rebuilds every       ║
║   triangle as a BRep face, sews them into a Shell, and exports      ║
║   STL + STEP — all via the build123d / OCP pipeline.                ║
╠══════════════════════════════════════════════════════════════════════╣
║  SETUP (one-time)                                                   ║
║    pip install build123d ocp-vscode                                 ║
║    VS Code extension → "OCP CAD Viewer"  by bernhard-42            ║
║                                                                     ║
║  RUN                                                                ║
║    python geometry_from_txt.py                                      ║
║    python geometry_from_txt.py  /path/to/other_file.txt            ║
║                                                                     ║
║  OUTPUT  (saved next to this script)                                ║
║    geometry_from_txt.stl                                            ║
║    geometry_from_txt.step                                           ║
╠══════════════════════════════════════════════════════════════════════╣
║  TEXT FILE FORMAT EXPECTED                                          ║
║                                                                     ║
║  SECTION 1 - UNIQUE VERTICES                                        ║
║    <id>   <x>   <y>   <z>                                           ║
║    0      3.000000   -1.896472   31.613630                          ║
║    ...                                                              ║
║                                                                     ║
║  SECTION 2 - TRIANGLES                                              ║
║    <tri_id>  <v0_id>  <v1_id>  <v2_id>  (+nx, +ny, +nz)           ║
║    (+v0_x, +v0_y, +v0_z)                                           ║
║    (+v1_x, +v1_y, +v1_z)                                           ║
║    (+v2_x, +v2_y, +v2_z)                                           ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import re
import sys
import numpy as np

# ── build123d / OCP ──────────────────────────────────────────────────
from build123d import Shape, export_stl, export_step, import_stl, Compound
from build123d import Mesher

from OCP.gp                  import gp_Pnt
from OCP.BRep                import BRep_Builder
from OCP.BRepBuilderAPI      import (BRepBuilderAPI_MakePolygon,
                                     BRepBuilderAPI_MakeFace,
                                     BRepBuilderAPI_Sewing)
from OCP.TopoDS              import TopoDS_Compound

try:
    from ocp_vscode import Camera, set_defaults, show
    OCP_AVAILABLE = True
except ImportError:
    print("⚠  ocp_vscode not installed — viewer disabled.")
    print("   Run:  pip install ocp-vscode")
    OCP_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════════
#  PATHS
# ══════════════════════════════════════════════════════════════════════

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

TXT_FILE = (sys.argv[1] if len(sys.argv) > 1
            else os.path.join(SCRIPT_DIR,
                              "ExtButtonArray_vertices_triangles.txt"))

STL_OUT  = os.path.join(SCRIPT_DIR, "geometry_from_txt.stl")
STEP_OUT = os.path.join(SCRIPT_DIR, "geometry_from_txt.step")


# ══════════════════════════════════════════════════════════════════════
#  STEP 1 — PARSE TEXT FILE
# ══════════════════════════════════════════════════════════════════════

def parse_txt(path: str):
    """
    Parse the custom text file into:
        vertices  : dict  { id (int) : (x, y, z) }
        triangles : list  [ (v0_id, v1_id, v2_id), ... ]

    Section 1 vertex line format:
        <id>   <x>   <y>   <z>
        e.g.:  0   3.000000   -1.896472   31.613630

    Section 2 triangle block format:
        <tri_id>  <v0_id>  <v1_id>  <v2_id>  (+nx, +ny, +nz)
        (+v0x, +v0y, +v0z)
        (+v1x, +v1y, +v1z)
        (+v2x, +v2y, +v2z)
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Text file not found:\n  {path}")

    vertices  = {}
    triangles = []
    in_sec1   = False
    in_sec2   = False

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # ── Section markers ───────────────────────────────────────────
        if "SECTION 1" in line:
            in_sec1, in_sec2 = True, False
            i += 1; continue

        if "SECTION 2" in line:
            in_sec2, in_sec1 = True, False
            i += 1; continue

        # ── Skip blank / decorative lines ─────────────────────────────
        if (not line
                or line.startswith("=")
                or line.startswith("-")
                or line.upper().startswith("ID")
                or line.upper().startswith("TRI")
                or line.upper().startswith("V0")
                or line.upper().startswith("END")):
            i += 1; continue

        # ── Section 1 — vertex line ───────────────────────────────────
        if in_sec1:
            parts = line.split()
            if len(parts) == 4:
                try:
                    vid = int(parts[0])
                    vertices[vid] = (float(parts[1]),
                                     float(parts[2]),
                                     float(parts[3]))
                except ValueError:
                    pass

        # ── Section 2 — triangle block ────────────────────────────────
        elif in_sec2:
            # Line pattern:  <tri_id>  <v0>  <v1>  <v2>  (+nx,+ny,+nz)
            m = re.match(
                r'^(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+\([^)]+\)', line)
            if m:
                triangles.append((int(m.group(2)),
                                  int(m.group(3)),
                                  int(m.group(4))))

        i += 1

    return vertices, triangles


# ══════════════════════════════════════════════════════════════════════
#  STEP 2 — BUILD OCP SHELL
# ══════════════════════════════════════════════════════════════════════

def build_shell(vertices: dict, triangles: list) -> Shape:
    """
    Convert the triangle soup into a sewn OCP Shell.

    For each triangle:
      1. Create three gp_Pnt points.
      2. Build a closed triangular wire with BRepBuilderAPI_MakePolygon.
      3. Build a planar BRep Face from that wire.
      4. Add the face to BRepBuilderAPI_Sewing.

    After all faces are added, Sewing.Perform() stitches shared edges
    into a proper Shell topology.  The result is wrapped in a
    build123d Shape so export_stl / export_step / show work directly.

    Parameters
    ----------
    vertices  : {id: (x, y, z)}
    triangles : [(v0_id, v1_id, v2_id), ...]

    Returns
    -------
    build123d Shape
    """
    sewing = BRepBuilderAPI_Sewing(1e-3)    # 0.001 mm tolerance
    skipped = 0

    for idx, (i0, i1, i2) in enumerate(triangles):

        try:
            p0 = gp_Pnt(*vertices[i0])
            p1 = gp_Pnt(*vertices[i1])
            p2 = gp_Pnt(*vertices[i2])

            # Skip zero-area (degenerate) triangles
            v0 = np.array(vertices[i0])
            v1 = np.array(vertices[i1])
            v2 = np.array(vertices[i2])
            if np.linalg.norm(np.cross(v1 - v0, v2 - v0)) < 1e-10:
                skipped += 1
                continue

            # Build closed triangular wire
            poly = BRepBuilderAPI_MakePolygon()
            poly.Add(p0)
            poly.Add(p1)
            poly.Add(p2)
            poly.Close()

            if not poly.IsDone():
                skipped += 1
                continue

            # Build planar face from wire
            face_mk = BRepBuilderAPI_MakeFace(poly.Wire())
            if not face_mk.IsDone():
                skipped += 1
                continue

            sewing.Add(face_mk.Face())

        except Exception:
            skipped += 1
            continue

        # Progress
        if (idx + 1) % 1000 == 0:
            pct = (idx + 1) / len(triangles) * 100
            print(f"    {idx+1:>6,} / {len(triangles):,}  ({pct:.1f}%)")

    if skipped:
        print(f"  ⚠  Skipped {skipped:,} degenerate / invalid triangles")

    # Sew all faces into a shell
    print("  Sewing faces …")
    sewing.Perform()
    sewn_shape = sewing.SewedShape()

    # Wrap in a TopoDS_Compound so build123d Shape handles it cleanly
    # regardless of whether sewing produced a Shell, Compound, or Solid
    builder  = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    builder.Add(compound, sewn_shape)

    return Shape(compound)


# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    print()
    print("┌" + "─" * 60 + "┐")
    print("│   TEXT FILE  →  build123d GEOMETRY                      │")
    print("└" + "─" * 60 + "┘")
    print(f"  Input  : {TXT_FILE}")
    print(f"  STL    : {STL_OUT}")
    print(f"  STEP   : {STEP_OUT}")
    print()

    # ── 1. Parse text file ────────────────────────────────────────────
    print("[ 1 / 4 ]  Parsing text file …")
    vertices, triangles = parse_txt(TXT_FILE)
    print(f"  Vertices  : {len(vertices):,}")
    print(f"  Triangles : {len(triangles):,}")

    xs = [v[0] for v in vertices.values()]
    ys = [v[1] for v in vertices.values()]
    zs = [v[2] for v in vertices.values()]
    print(f"  Bbox X : {min(xs):.4f}  →  {max(xs):.4f}  (span {max(xs)-min(xs):.4f})")
    print(f"  Bbox Y : {min(ys):.4f}  →  {max(ys):.4f}  (span {max(ys)-min(ys):.4f})")
    print(f"  Bbox Z : {min(zs):.4f}  →  {max(zs):.4f}  (span {max(zs)-min(zs):.4f})")
    print()

    # ── 2. Build geometry ─────────────────────────────────────────────
    print("[ 2 / 4 ]  Building BRep shell from triangles …")
    shape = build_shell(vertices, triangles)
    bb = shape.bounding_box()
    print(f"  ✓  Shell built")
    print(f"  Bounding box:")
    print(f"    X : {bb.min.X:+.4f}  →  {bb.max.X:+.4f}   span = {bb.max.X - bb.min.X:.4f}")
    print(f"    Y : {bb.min.Y:+.4f}  →  {bb.max.Y:+.4f}   span = {bb.max.Y - bb.min.Y:.4f}")
    print(f"    Z : {bb.min.Z:+.4f}  →  {bb.max.Z:+.4f}   span = {bb.max.Z - bb.min.Z:.4f}")
    print()

    # ── 3. Export STL + STEP ──────────────────────────────────────────
    print("[ 3 / 4 ]  Exporting …")
    export_stl(shape, STL_OUT,  tolerance=0.01, angular_tolerance=0.3)
    export_step(shape, STEP_OUT)
    print(f"  ✓  {os.path.basename(STL_OUT):<42} "
          f"{os.path.getsize(STL_OUT) / 1024:6.1f} KB")
    print(f"  ✓  {os.path.basename(STEP_OUT):<42} "
          f"{os.path.getsize(STEP_OUT) / 1024:6.1f} KB")
    print()

    # ── 4. OCP CAD Viewer ─────────────────────────────────────────────
    print("[ 4 / 4 ]  Launching OCP CAD Viewer …")
    if OCP_AVAILABLE:
        try:
            # Re-import the exported STL as a proper build123d mesh object.
            # This is the most reliable way to display mesh-based geometry
            # in OCP CAD Viewer — raw Shape(sewn_shape) wraps a bare OCP
            # TopoDS which the viewer may not render correctly.
            print("  Re-importing STL for viewer …")
            mesh = import_stl(STL_OUT)

            set_defaults(
                theme        = "dark",
                ortho        = False,
                default_color= "#4a8fa8",
            )
            show(
                mesh,
                names         = ["ExtButtonArray"],
                colors        = ["#4a8fa8"],
                alphas        = [1.0],
                axes          = True,
                axes0         = True,
                grid          = (True, True, True),
                measure_tools = True,
                reset_camera  = Camera.RESET,
            )
            print("  ✅  Showing in OCP CAD Viewer — check VS Code side panel")
        except Exception as e:
            print(f"  ⚠  Viewer error: {e}")
            # Fallback: try showing the raw shape directly
            try:
                print("  Trying fallback display …")
                show(shape, names=["ExtButtonArray"], reset_camera=Camera.RESET)
                print("  ✅  Fallback display sent")
            except Exception as e2:
                print(f"  ⚠  Fallback also failed: {e2}")
    else:
        print("  Skipped — install with:  pip install ocp-vscode")

    print()
    print("┌" + "─" * 60 + "┐")
    print(f"│  Done!  Open geometry_from_txt.stl to inspect the mesh  │")
    print("└" + "─" * 60 + "┘")


if __name__ == "__main__":
    main()