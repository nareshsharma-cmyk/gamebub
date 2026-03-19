# DPad
It is a part of this setup which contains a component named as DpadButton
The DPad button is a plus-shaped (+) solid built procedurally from three stacked feature groups. First, the main body is constructed by combining five non-overlapping axis-aligned boxes — one square central hub (6×6 mm)
and four arms extending 9 mm outward from the hub centre in the ±X and ±Z directions, each 6 mm wide and 3 mm tall. Second, a circular disk of radius 6.5 mm and height 1 mm is placed concentrically on top of the body to form the thumb-contact surface. 
Third, four cylindrical alignment posts (radius 1 mm, height 1.2 mm, top-edge fillet 0.25 mm) are positioned below the bottom face, one per arm, each offset 7 mm along the arm's longitudinal axis from the hub centre and 2.45 mm inward from the arm's outer edge.
Each curved feature is tessellated with 48 radial segments. The assembled mesh totals 1,020 triangles and is exported as a binary STL file with outward-facing CCW winding normals, ready for import into MeshLab, Blender or any slicer tool.

# ExtButtonArray

Import required libraries (build123d, ocp_vscode, os) and set up a fallback viewer in case visualization is not available

Load STL file by checking its existence, importing it using import_stl(), and using an OCP-based fallback method if needed

Read G-code file from the directory, validate its presence, and store its content as a string

Parse G-code by removing comments, identifying G0 and G1 commands, tracking tool position, and separating travel moves from cutting paths

Group continuous cutting moves into paths, clean duplicate points, and convert them into Polyline objects

Reconstruct geometry by iterating over toolpaths, defining a plane using path direction, sketching a circular profile, and sweeping it along the path

Collect all generated swept solids and combine them into a single compound geometry

Define export location, create directory if needed, and export the combined geometry as an STL file

Prepare objects for visualization by including STL geometry and generated toolpaths with proper naming

Display all objects in VS Code viewer using show() and handle errors using try-except for stability
