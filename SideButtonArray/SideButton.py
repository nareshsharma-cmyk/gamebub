"""
╔══════════════════════════════════════════════════════════════════════╗
║   SideButtonArray — Text File → build123d + OCP CAD Viewer         ║
╠══════════════════════════════════════════════════════════════════════╣
║  SETUP (one-time)                                                   ║
║    pip install build123d ocp-vscode                                 ║
║    VS Code extension → "OCP CAD Viewer" by bernhard-42             ║
║                                                                     ║
║  RUN                                                                ║
║    python SideButtonArray_from_txt.py                               ║
║    python SideButtonArray_from_txt.py  /path/to/other.txt          ║
║                                                                     ║
║  INPUT                                                              ║
║    .../component files/SideButtonArray/                             ║
║    SideButtonArray_vertices_triangles.txt                           ║
║                                                                     ║
║  OUTPUT                                                             ║
║    .../component files/SideButtonArray/                             ║
║      SideButtonArray_rebuilt.stl                                   ║
║      SideButtonArray_rebuilt.step                                  ║
╠══════════════════════════════════════════════════════════════════════╣
║  PIPELINE                                                           ║
║    txt → parse → write binary STL → import_stl() → show()         ║
║                                                                     ║
║  import_stl() is the only reliable path to visible geometry        ║
║  in OCP CAD Viewer. Raw BRep/sewing compounds do not render.       ║
║                                                                     ║
║  VIEWER — 3-strategy fallback for all ocp_vscode versions:         ║
║    1. show_object()  (most compatible, recommended)                 ║
║    2. show() with kwargs  (ocp_vscode >= 2.x)                      ║
║    3. show(mesh)  (bare minimum, works everywhere)                  ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import re
import sys
import struct
import math

# ── build123d ────────────────────────────────────────────────────────
from build123d import import_stl, export_step

# ── OCP CAD Viewer — import with fallback ────────────────────────────
try:
    from ocp_vscode import show, show_object, Camera
    OCP_AVAILABLE = True
except ImportError:
    try:
        from ocp_vscode import show_object as show, Camera
        OCP_AVAILABLE = True
    except ImportError:
        print("⚠  ocp_vscode not installed — run:  pip install ocp-vscode")
        OCP_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════════
#  PATHS
# ══════════════════════════════════════════════════════════════════════

TXT_FILE = (
    sys.argv[1] if len(sys.argv) > 1
    else "/Users/softage/Desktop/gamebub_files/component files/"
         "SideButtonArray/SideButtonArray_vertices_triangles.txt"
)

OUT_DIR  = ("/Users/softage/Desktop/gamebub_files/component files/"
            "SideButtonArray")
STL_OUT  = os.path.join(OUT_DIR, "SideButtonArray_rebuilt.stl")
STEP_OUT = os.path.join(OUT_DIR, "SideButtonArray_rebuilt.step")


# ══════════════════════════════════════════════════════════════════════
#  STEP 1 — PARSE TEXT FILE
# ══════════════════════════════════════════════════════════════════════

def parse_txt(path: str):
    """
    Parse the custom vertices-and-triangles text file.

    Section 1 — vertex lines:
        <id>   <x>   <y>   <z>
        e.g.:  0   -44.526962   -0.307584   116.375763

    Section 2 — triangle header lines:
        <tri_id>  <v0_id>  <v1_id>  <v2_id>  (+nx, +ny, +nz)

    Returns
    -------
    vertices  : dict  { id (int) : (x, y, z) }
    triangles : list  [ (v0_id, v1_id, v2_id), ... ]
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"\n  Text file not found:\n  {path}"
        )

    vertices  = {}
    triangles = []
    in_sec1   = False
    in_sec2   = False

    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()

            if "SECTION 1" in s:
                in_sec1, in_sec2 = True, False;  continue
            if "SECTION 2" in s:
                in_sec2, in_sec1 = True, False;  continue

            if (not s
                    or s.startswith("=")
                    or s.startswith("-")
                    or s.upper().startswith("ID")
                    or s.upper().startswith("TRI")
                    or s.upper().startswith("V0")
                    or s.upper().startswith("END")):
                continue

            if in_sec1:
                p = s.split()
                if len(p) == 4:
                    try:
                        vertices[int(p[0])] = (
                            float(p[1]), float(p[2]), float(p[3]))
                    except ValueError:
                        pass

            elif in_sec2:
                m = re.match(
                    r'^(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+\([^)]+\)', s)
                if m:
                    triangles.append((
                        int(m.group(2)),
                        int(m.group(3)),
                        int(m.group(4)),
                    ))

    return vertices, triangles


# ══════════════════════════════════════════════════════════════════════
#  STEP 2 — WRITE BINARY STL
# ══════════════════════════════════════════════════════════════════════

def write_binary_stl(vertices: dict, triangles: list, path: str) -> int:
    """
    Write a byte-perfect binary STL from parsed mesh data.

    Per triangle:
      • Compute unit normal: n = normalise((v1−v0) × (v2−v0))
      • Skip degenerate (zero-area) triangles
      • Write 50-byte record:
            12 bytes  normal   (3 × float32)
            12 bytes  vertex 0 (3 × float32)
            12 bytes  vertex 1 (3 × float32)
            12 bytes  vertex 2 (3 × float32)
             2 bytes  attribute count (uint16 = 0)

    Returns number of triangles written.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)

    records = []
    for i0, i1, i2 in triangles:
        ax, ay, az = vertices[i0]
        bx, by, bz = vertices[i1]
        cx, cy, cz = vertices[i2]

        ex, ey, ez = bx - ax, by - ay, bz - az
        fx, fy, fz = cx - ax, cy - ay, cz - az

        nx = ey * fz - ez * fy
        ny = ez * fx - ex * fz
        nz = ex * fy - ey * fx
        L  = math.sqrt(nx*nx + ny*ny + nz*nz)

        if L < 1e-10:
            continue

        records.append((
            nx/L, ny/L, nz/L,
            ax, ay, az,
            bx, by, bz,
            cx, cy, cz,
        ))

    with open(path, "wb") as f:
        f.write(b"Rebuilt from SideButtonArray_vertices_triangles.txt"
                .ljust(80, b"\x00"))
        f.write(struct.pack("<I", len(records)))
        for rec in records:
            f.write(struct.pack("<12f", *rec))
            f.write(struct.pack("<H", 0))

    return len(records)


# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    print()
    print("┌" + "─" * 62 + "┐")
    print("│   SideButtonArray  —  Text File → OCP CAD Viewer         │")
    print("└" + "─" * 62 + "┘")
    print(f"  Input   : {TXT_FILE}")
    print(f"  STL out : {STL_OUT}")
    print(f"  STEP out: {STEP_OUT}")
    print()

    # ── 1. Parse ──────────────────────────────────────────────────────
    print("[ 1 / 4 ]  Parsing text file …")
    vertices, triangles = parse_txt(TXT_FILE)

    n_v = len(vertices)
    n_t = len(triangles)
    xs  = [v[0] for v in vertices.values()]
    ys  = [v[1] for v in vertices.values()]
    zs  = [v[2] for v in vertices.values()]

    print(f"  Vertices  : {n_v:,}")
    print(f"  Triangles : {n_t:,}")
    print(f"  Bbox X    : {min(xs):.4f}  →  {max(xs):.4f}"
          f"   span {max(xs)-min(xs):.4f}")
    print(f"  Bbox Y    : {min(ys):.4f}  →  {max(ys):.4f}"
          f"   span {max(ys)-min(ys):.4f}")
    print(f"  Bbox Z    : {min(zs):.4f}  →  {max(zs):.4f}"
          f"   span {max(zs)-min(zs):.4f}")
    print()

    # ── 2. Write binary STL ───────────────────────────────────────────
    print("[ 2 / 4 ]  Writing binary STL …")
    n_written = write_binary_stl(vertices, triangles, STL_OUT)
    skipped   = n_t - n_written

    print(f"  Triangles written : {n_written:,}")
    if skipped:
        print(f"  Skipped (degen.)  : {skipped:,}")
    print(f"  File size         : {os.path.getsize(STL_OUT)/1024:.1f} KB")
    print(f"  ✓  {STL_OUT}")
    print()

    # ── 3. Load into build123d + export STEP ─────────────────────────
    print("[ 3 / 4 ]  Loading into build123d …")
    mesh = import_stl(STL_OUT)

    bb = mesh.bounding_box()
    print(f"  ✓  Mesh loaded")
    print(f"  Bounding box:")
    print(f"    X : {bb.min.X:+.4f}  →  {bb.max.X:+.4f}"
          f"   span = {bb.max.X - bb.min.X:.4f}")
    print(f"    Y : {bb.min.Y:+.4f}  →  {bb.max.Y:+.4f}"
          f"   span = {bb.max.Y - bb.min.Y:.4f}")
    print(f"    Z : {bb.min.Z:+.4f}  →  {bb.max.Z:+.4f}"
          f"   span = {bb.max.Z - bb.min.Z:.4f}")
    print()

    print("[ 4 / 4 ]  Exporting STEP …")
    os.makedirs(OUT_DIR, exist_ok=True)
    export_step(mesh, STEP_OUT)
    print(f"  ✓  {STEP_OUT}")
    print(f"     {os.path.getsize(STEP_OUT)/1024:.1f} KB")
    print()

    # ── OCP CAD Viewer — 3-strategy fallback ─────────────────────────
    print("Launching OCP CAD Viewer …")
    if OCP_AVAILABLE:
        displayed = False

        # Strategy 1 — show_object() — most compatible across all
        #              ocp_vscode versions, recommended by the extension
        if not displayed:
            try:
                show_object(mesh,
                            name    = "SideButtonArray",
                            options = {"color": "#e67e22", "alpha": 1.0})
                print("  ✅  Geometry visible in OCP CAD Viewer  (show_object)")
                print("      Check the VS Code side panel →")
                displayed = True
            except Exception:
                pass

        # Strategy 2 — show() with full keyword args (ocp_vscode >= 2.x)
        if not displayed:
            try:
                show(mesh,
                     names        = ["SideButtonArray"],
                     colors       = ["#e67e22"],
                     alphas       = [1.0],
                     axes         = True,
                     axes0        = True,
                     grid         = (True, True, True),
                     reset_camera = Camera.RESET)
                print("  ✅  Geometry visible in OCP CAD Viewer  (show + kwargs)")
                displayed = True
            except Exception:
                pass

        # Strategy 3 — bare show() — works in all versions
        if not displayed:
            try:
                show(mesh)
                print("  ✅  Geometry sent to OCP CAD Viewer  (bare show)")
                displayed = True
            except Exception as e:
                print(f"  ⚠  All viewer strategies failed: {e}")

    else:
        print("  Skipped — run:  pip install ocp-vscode")

    print()
    print("┌" + "─" * 62 + "┐")
    pad = lambda s: s + " " * max(0, 61 - len(s))
    print(f"│  {pad(f'{n_written:,} triangles  |  {n_v:,} vertices')}│")
    print(f"│  {pad(f'STL  → {os.path.basename(STL_OUT)}')}│")
    print(f"│  {pad(f'STEP → {os.path.basename(STEP_OUT)}')}│")
    print("└" + "─" * 62 + "┘")


if __name__ == "__main__":
    main()