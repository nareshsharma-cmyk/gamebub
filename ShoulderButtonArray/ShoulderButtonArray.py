"""
╔══════════════════════════════════════════════════════════════════════╗
║   ShoulderButtonArray — Text File → build123d + OCP CAD Viewer     ║
╠══════════════════════════════════════════════════════════════════════╣
║  SETUP (one-time)                                                   ║
║    pip install build123d ocp-vscode                                 ║
║    VS Code extension → "OCP CAD Viewer" by bernhard-42             ║
║                                                                     ║
║  RUN                                                                ║
║    python ShoulderButtonArray_from_txt.py                           ║
║    python ShoulderButtonArray_from_txt.py  /path/to/other.txt      ║
║                                                                     ║
║  INPUT                                                              ║
║    .../component files/ShoulderButtonArray/                         ║
║    ShoulderButtonArray_vertices_triangles.txt                       ║
║                                                                     ║
║  OUTPUT                                                             ║
║    .../component files/ShoulderButtonArray/                         ║
║      ShoulderButtonArray_rebuilt.stl                               ║
║      ShoulderButtonArray_rebuilt.step                              ║
╠══════════════════════════════════════════════════════════════════════╣
║  PIPELINE                                                           ║
║    txt → parse → write binary STL → import_stl() → show()         ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import re
import sys
import struct
import math

from build123d import import_stl, export_step

try:
    from ocp_vscode import Camera, show
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
         "ShoulderButtonArray/ShoulderButtonArray_vertices_triangles.txt"
)

OUT_DIR  = ("/Users/softage/Desktop/gamebub_files/component files/"
            "ShoulderButtonArray")
STL_OUT  = os.path.join(OUT_DIR, "ShoulderButtonArray_rebuilt.stl")
STEP_OUT = os.path.join(OUT_DIR, "ShoulderButtonArray_rebuilt.step")


# ══════════════════════════════════════════════════════════════════════
#  STEP 1 — PARSE TEXT FILE
# ══════════════════════════════════════════════════════════════════════

def parse_txt(path: str):
    """
    Parse the custom vertices-and-triangles text file.

    Section 1 — vertex lines:
        <id>   <x>   <y>   <z>

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
      • Write 50-byte record: normal + 3 vertices + attribute word
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)

    records = []
    for i0, i1, i2 in triangles:
        ax, ay, az = vertices[i0]
        bx, by, bz = vertices[i1]
        cx, cy, cz = vertices[i2]

        ex, ey, ez = bx-ax, by-ay, bz-az
        fx, fy, fz = cx-ax, cy-ay, cz-az

        nx = ey*fz - ez*fy
        ny = ez*fx - ex*fz
        nz = ex*fy - ey*fx
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
        f.write(b"Rebuilt from ShoulderButtonArray_vertices_triangles.txt"
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
    print("│   ShoulderButtonArray  —  Text File → OCP CAD Viewer     │")
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

    # ── OCP CAD Viewer ────────────────────────────────────────────────
    print("Launching OCP CAD Viewer …")
    if OCP_AVAILABLE:
        try:
            show(
                mesh,
                names        = ["ShoulderButtonArray"],
                colors       = ["#27ae60"],
                alphas       = [1.0],
                axes         = True,
                axes0        = True,
                grid         = (True, True, True),
                reset_camera = Camera.RESET,
            )
            print("  ✅  Geometry visible in OCP CAD Viewer")
            print("      Check the VS Code side panel →")

        except TypeError:
            # Older ocp_vscode — fall back to bare show()
            try:
                show(mesh)
                print("  ✅  Geometry sent to OCP CAD Viewer (basic mode)")
            except Exception as e2:
                print(f"  ⚠  Viewer error: {e2}")

        except Exception as e:
            print(f"  ⚠  Viewer error: {e}")

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