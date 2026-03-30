from build123d import *
from ocp_vscode import *
set_port(3939)
# =========================
# PARAMETERS (ALL IN mm)
# =========================
L = 4350
W = 800
T = 20

# Hole diameters (corrected)
D_L = 110     # large holes (diameter)
D_M = 50    # medium holes
D_S = 16      # small holes

bolt_radius = 16   # bolt circle radius

# -------------------------
# LARGE HOLE GEOMETRY (FROM STL)
# -------------------------
row_y = 222            # corrected Y position
edge_offset = 240     # distance from edge to first hole center
spacing = 230       # center-to-center spacing
num_large = 8

# Compute exact X positions
x_start = -L/2 + edge_offset
x_positions = [x_start + i * spacing for i in range(num_large)]

# -------------------------
# MEDIUM HOLES (approx region)
# -------------------------
medium_origin_1 = (95,-212)
medium_origin_2=(1476,-260)
medium_spacing_x = 138
medium_spacing_y = 138

# =========================
# BUILD PART
# =========================
with BuildPart() as panel:

    # -------------------------
    # BASE PLATE
    # -------------------------
    Box(L, W, T)

    # Edge fillet
    fillet(panel.edges().filter_by(Axis.Z), 5)

    # -------------------------
    # LARGE HOLES + BOLT PATTERN
    # -------------------------
    for y in (-row_y, row_y):
        for x in x_positions:
            with Locations((x, y)):

                # Main large hole
                Hole(D_L)

                # Bolt pattern (4 holes around)
                with PolarLocations(bolt_radius, 4):
                    Hole(D_S)

    # -------------------------
    # MEDIUM HOLES 
    # -------------------------
    with Locations(medium_origin_1):
        with GridLocations(medium_spacing_x, medium_spacing_y, 4, 2):
            Hole(D_M)
    with Locations(medium_origin_2):
        with GridLocations(medium_spacing_x, medium_spacing_y, 4, 1):
            Hole(D_M)
    # -------------------------
    # SMALL HOLES (edge distribution - approx)
    # -------------------------
    # edge_y = 300
    # with Locations((0, edge_y), (0, -edge_y)):
    #     with GridLocations(300, 0, 10, 1):
    #         Hole(D_S)

    # -------------------------
    # RIGHT SIDE CUTOUTS
    # -------------------------
    top_face = Plane(origin=(0, 0, T/2), z_dir=(0, 0, 1))

    with BuildSketch(top_face):

        # Rectangular slots
        with Locations((695, -300), (836, -300), (977, -300), (1118, -300)):
            Rectangle(104, 103)

        #rectangular cutout
        with Locations((505.5, -300)):
            Rectangle(224, 105)
        
        # Rectangular slots
        with Locations((1544.5, 0)):
            Rectangle(121, 110)

        # Rectangular slots
        with Locations((1986.5, 265)):
            Rectangle(194, 130)


    extrude(amount=-T, mode=Mode.SUBTRACT)

export_step(panel.part, "panel_corrected.step")
show(panel.part)