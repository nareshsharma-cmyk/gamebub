import os
import traceback
from build123d import *
try:
    from ocp_vscode import show
except ImportError:
    print("ocp_vscode is not installed.")
    show = lambda *args, **kwargs: print("VS Code viewer not available.")

def load_stl(filename):
    print(f"Loading STL: {filename}")
    if not os.path.exists(filename):
        print(f"STL file '{filename}' not found.")
        return None
    try:
        return import_stl(filename)
    except Exception:
        try:
            from OCP.StlAPI import StlAPI_Reader
            from OCP.TopoDS import TopoDS_Shape
            from build123d import Shape
            reader = StlAPI_Reader()
            shape = TopoDS_Shape()
            reader.Read(shape, filename)
            return Shape(shape)
        except Exception as e:
            print(f"Could not load STL: {e}")
            return None

def parse_gcode_string(gcode_str):
    print("Parsing G-Code from provided string...")
    if not gcode_str or not gcode_str.strip(): return []
    lines = gcode_str.strip().split("\n")
    paths, current_path, current_pos = [], [], [0.0, 0.0, 0.0]
    is_traveling = True

    for line in lines:
        command = line.split(";")[0].split("(")[0].strip()
        if not command: continue
        parts = command.split()
        cmd = parts[0]
        
        if cmd in ["G0", "G1"]:
            new_pos = list(current_pos)
            has_xy = False
            for p in parts[1:]:
                if p.startswith("X"): 
                    new_pos[0] = float(p[1:])
                    has_xy = True
                elif p.startswith("Y"): 
                    new_pos[1] = float(p[1:])
                    has_xy = True
                elif p.startswith("Z"): 
                    new_pos[2] = float(p[1:])
            
            if cmd == "G0":
                is_traveling = True
            elif cmd == "G1":
                if not has_xy:
                    is_traveling = True
                else:
                    if is_traveling:
                        if len(current_path) > 1: paths.append(current_path)
                        current_path = [(new_pos[0], new_pos[1], new_pos[2])]
                        is_traveling = False
                    else:
                        if not current_path:
                            current_path.append((current_pos[0], current_pos[1], current_pos[2]))
                        current_path.append((new_pos[0], new_pos[1], new_pos[2]))
            
            current_pos = new_pos

    if len(current_path) > 1: paths.append(current_path)
    
    gcode_wires = []
    for p in paths:
        clean_p = []
        for pt in p:
            if not clean_p or clean_p[-1] != pt: clean_p.append(pt)
        if len(clean_p) > 1:
            gcode_wires.append(Polyline(*clean_p))
    return gcode_wires

if __name__ == "__main__":
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    gcode_filename = os.path.join(script_dir, "Custom_ExtButtonArray.gcode")
    
    if not os.path.exists(gcode_filename):
        print(f"ERROR: {gcode_filename} is missing! Please create it and paste your GCode inside.")
        exit(1)
        
    with open(gcode_filename, "r") as f:
        gcode_data = f.read()

    local_stl_filename = os.path.join(script_dir, "ExtButtonArray.stl")
    stl_obj = load_stl(local_stl_filename)

    gcode_obj = parse_gcode_string(gcode_data)
    print(f"Extracted {len(gcode_obj)} toolpath segments.")
    
    try:
        export_dir = "/Users/softage/Desktop/new"
        if not os.path.exists(export_dir): os.makedirs(export_dir)
        export_path = os.path.join(export_dir, "ExtButtonArray.stl")
        
        print(f"Converting paths to 3D tubes for STL export...")
        solid_parts = []
        for w in gcode_obj:
            try:
                pt = w.edges()[0].start_point
                if callable(pt): pt = pt()
                tan = w.edges()[0].tangent_at(0)
                
                o_xyz = (float(pt.X), float(pt.Y), float(pt.Z))
                z_xyz = (float(tan.X), float(tan.Y), float(tan.Z))
                
                start_plane = Plane(origin=o_xyz, z_dir=z_xyz)
                with BuildPart() as tube:
                    with BuildSketch(start_plane):
                        Circle(radius=0.4)
                    sweep(path=w)
                solid_parts.append(tube.part)
            except Exception as e:
                continue
                
        if solid_parts:
            combined_shape = Compound(children=solid_parts)
            export_stl(combined_shape, export_path)
            print(f"SUCCESS: Geometry automatically saved to -> {export_path}")
        else:
            print("Notice: No solid paths generated for STL export.")
    except Exception as e:
        print(f"Failed to export STL: {e}")

    objects_to_show = []
    names = []
    if stl_obj:
        objects_to_show.append(stl_obj)
        names.append("ExtButtonArray_STL")
    if gcode_obj:
        objects_to_show.extend(gcode_obj)
        names.extend([f"Path_{i}" for i in range(len(gcode_obj))])
        
    if objects_to_show:
        try:
            show(*objects_to_show, names=names)
            print("Sent completely to VS Code viewer!")
        except Exception: pass
