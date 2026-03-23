"""
╔══════════════════════════════════════════════════════════════════════╗
║   Front — Text File → build123d + OCP CAD Viewer                   ║
╠══════════════════════════════════════════════════════════════════════╣
║  SETUP (one-time)                                                   ║
║    pip install build123d ocp-vscode                                 ║
║    VS Code extension → "OCP CAD Viewer" by bernhard-42             ║
║                                                                     ║
║  RUN                                                                ║
║    python Front_from_txt.py                                         ║
║    python Front_from_txt.py  /path/to/other.txt                    ║
║                                                                     ║
║  INPUT                                                              ║
║    /Users/softage/Desktop/gamebub_files/component files/           ║
║    front /Front_vertices_triangles.txt                              ║
║                                                                     ║
║  OUTPUT                                                             ║
║    /Users/softage/Desktop/gamebub_files/component files/front/     ║
║      Front_rebuilt.stl                                             ║
║      Front_rebuilt.step                                            ║
╠══════════════════════════════════════════════════════════════════════╣
║  HOW IT WORKS                                                       ║
║                                                                     ║
║  OCP CAD Viewer only reliably renders objects loaded via            ║
║  build123d's import_stl() — not raw BRep/sewing compounds.         ║
║  Pipeline:                                                          ║
║    txt → parse → write binary STL → import_stl() → show()          ║
║                                                                     ║
║  STEP export uses build123d's export_step() on the imported mesh.  ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import re
import sys
import struct
import math

# ── build123d ────────────────────────────────────────────────────────
from build123d import import_stl, export_step

try:
    from ocp_vscode import Camera, show
    OCP_AVAILABLE = True
except ImportError:
    print("⚠  ocp_vscode not installed — viewer disabled.")
    print("   Run:  pip install ocp-vscode")
    OCP_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════════
#  PATHS
# ══════════════════════════════════════════════════════════════════════

# Input text file
TXT_FILE = (
    sys.argv[1] if len(sys.argv) > 1
    else "/Users/softage/Desktop/gamebub_files/component files/"
         "front /Front_vertices_triangles.txt"
)

# Output directory and files
OUT_DIR   = "/Users/softage/Desktop/gamebub_files/component files/front"
STL_OUT   = os.path.join(OUT_DIR, "Front_rebuilt.stl")
STEP_OUT  = os.path.join(OUT_DIR, "Front_rebuilt.step")


# ══════════════════════════════════════════════════════════════════════
#  STEP 1 — PARSE TEXT FILE
# ══════════════════════════════════════════════════════════════════════

def parse_txt(path: str):
    """
    Parse the custom vertices-and-triangles text file.

    Section 1 — vertex lines:
        <id>   <x>   <y>   <z>
        e.g.:  0   45.049999   -3.300000   124.246666

    Section 2 — triangle header lines:
        <tri_id>  <v0_id>  <v1_id>  <v2_id>  (+nx, +ny, +nz)

    Returns
    -------
    vertices  : dict  { id (int) : (x, y, z) }
    triangles : list  [ (v0_id, v1_id, v2_id), ... ]
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"\n  Text file not found:\n  {path}\n\n"
            f"  Make sure Front_vertices_triangles.txt is at:\n  {path}"
        )

    vertices  = {}
    triangles = []
    in_sec1   = False
    in_sec2   = False

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        s = line.strip()

        # ── Section markers ───────────────────────────────────────────
        if "SECTION 1" in s:
            in_sec1, in_sec2 = True, False
            continue
        if "SECTION 2" in s:
            in_sec2, in_sec1 = True, False
            continue

        # ── Skip blank / decorative lines ─────────────────────────────
        if (not s
                or s.startswith("=")
                or s.startswith("-")
                or s.upper().startswith("ID")
                or s.upper().startswith("TRI")
                or s.upper().startswith("V0")
                or s.upper().startswith("END")):
            continue

        # ── Section 1 : vertex line ───────────────────────────────────
        if in_sec1:
            parts = s.split()
            if len(parts) == 4:
                try:
                    vertices[int(parts[0])] = (
                        float(parts[1]),
                        float(parts[2]),
                        float(parts[3]),
                    )
                except ValueError:
                    pass

        # ── Section 2 : triangle header line ─────────────────────────
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
    Write a valid binary STL directly from parsed mesh data.

    For every triangle:
      • Compute unit face normal: n = normalise((v1-v0) × (v2-v0))
      • Skip degenerate (zero-area) triangles silently
      • Write the 50-byte binary record:
            12 bytes  normal   (3 × float32)
            12 bytes  vertex 0 (3 × float32)
            12 bytes  vertex 1 (3 × float32)
            12 bytes  vertex 2 (3 × float32)
             2 bytes  attribute count (uint16 = 0)

    Returns number of triangles written.
    """
    # Ensure output directory exists
    os.makedirs(os.path.dirname(path), exist_ok=True)

    records = []

    for i0, i1, i2 in triangles:
        ax, ay, az = vertices[i0]
        bx, by, bz = vertices[i1]
        cx, cy, cz = vertices[i2]

        # Edge vectors
        ex, ey, ez = bx - ax, by - ay, bz - az
        fx, fy, fz = cx - ax, cy - ay, cz - az

        # Cross product → face normal
        nx = ey * fz - ez * fy
        ny = ez * fx - ex * fz
        nz = ex * fy - ey * fx
        length = math.sqrt(nx * nx + ny * ny + nz * nz)

        if length < 1e-10:          # degenerate — skip
            continue

        nx /= length
        ny /= length
        nz /= length

        records.append((
            nx,  ny,  nz,
            ax,  ay,  az,
            bx,  by,  bz,
            cx,  cy,  cz,
        ))

    with open(path, "wb") as f:
        header = b"Rebuilt from Front_vertices_triangles.txt"
        f.write(header.ljust(80, b"\x00"))
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
    print("┌" + "─" * 64 + "┐")
    print("│   Front  —  Text File → build123d + OCP CAD Viewer        │")
    print("└" + "─" * 64 + "┘")
    print(f"  Input   : {TXT_FILE}")
    print(f"  STL out : {STL_OUT}")
    print(f"  STEP out: {STEP_OUT}")
    print()

    # ── 1. Parse text file ────────────────────────────────────────────
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
    size_kb   = os.path.getsize(STL_OUT) / 1024

    print(f"  Triangles written : {n_written:,}")
    if skipped:
        print(f"  Skipped (degen.)  : {skipped:,}")
    print(f"  File size         : {size_kb:.1f} KB")
    print(f"  ✓  {STL_OUT}")
    print()

    # ── 3. Load into build123d → show + export STEP ───────────────────
    print("[ 3 / 4 ]  Loading into build123d via import_stl() …")

    # import_stl() is the ONLY reliable way to get visible geometry
    # in OCP CAD Viewer — it produces a fully tessellated build123d
    # Shape with correct normals and display metadata.
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

    # Export STEP
    print("[ 4 / 4 ]  Exporting STEP …")
    os.makedirs(OUT_DIR, exist_ok=True)
    export_step(mesh, STEP_OUT)
    print(f"  ✓  {STEP_OUT}")
    print(f"     {os.path.getsize(STEP_OUT) / 1024:.1f} KB")
    print()

    # ── OCP CAD Viewer ────────────────────────────────────────────────
    print("Launching OCP CAD Viewer …")
    if OCP_AVAILABLE:
        try:
            # show() directly — no set_defaults to avoid version mismatch
            show(
                mesh,
                names        = ["Front"],
                colors       = ["#5b9bd5"],
                alphas       = [1.0],
                axes         = True,
                axes0        = True,
                grid         = (True, True, True),
                reset_camera = Camera.RESET,
            )
            print("  ✅  Geometry visible in OCP CAD Viewer")
            print("      Check the VS Code side panel →")
        except TypeError:
            # Older ocp_vscode versions use positional args only
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
    print("┌" + "─" * 64 + "┐")
    print(f"│  {n_written:,} triangles  |  {n_v:,} vertices"
          + " " * max(0, 63 - len(f"  {n_written:,} triangles  |  {n_v:,} vertices"))
          + "│")
    print(f"│  STL  → {os.path.basename(STL_OUT)}"
          + " " * max(0, 63 - len(f"  STL  → {os.path.basename(STL_OUT)}"))
          + "│")
    print(f"│  STEP → {os.path.basename(STEP_OUT)}"
          + " " * max(0, 63 - len(f"  STEP → {os.path.basename(STEP_OUT)}"))
          + "│")
    print("└" + "─" * 64 + "┘")


if __name__ == "__main__":
    main()