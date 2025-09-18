#!/usr/bin/env python3
"""
paint_mixing_grid.py
Systematically generate a grid of paint-mixing test clusters.

- Palette "rgb6": red, yellow, blue, white
- Palette "cmyk": cyan, magenta, yellow, black
- Each cluster = 3 vertices + 1 center dot
- Values sweep across grid (two colors vary with X/Y, two fixed)
- Z depth for each dot is proportional to color value
"""

import argparse
from dataclasses import dataclass
from typing import Dict

# -------------------------------
# CONSTANTS
# -------------------------------

# Station grid layout
STATION_X0 = 400.0
STATION_Y0 = 40.0
STATION_DX = 0.0
STATION_DY = 40.0

# Dip & blot offsets
DIP_OFFSET_X  = 0.0
DIP_OFFSET_Y  = 0.0
DIP_OFFSET_Z  = -3.0
BLOT_OFFSET_X = 60.0
BLOT_OFFSET_Y = 0.0
BLOT_OFFSET_Z = -2.0

# Z levels
Z_PICK = -5.0
Z_SAFE = 15.0
Z_TRAVEL = 10.0
Z_PREPAINT = 2.0

# Motion
FEED_TRAVEL = 2000
FEED_Z = 600

# Time scaling (RichAuto B58 uses ms for G4 P)
TIME_SCALE = 1000.0

# Dot placement (triangle + center)
VERTEX_RADIUS = 8.0  # mm
TRIANGLE_OFFSETS = [
    (0, -VERTEX_RADIUS),                        # top
    (-VERTEX_RADIUS*0.866, VERTEX_RADIUS/2),    # bottom-left
    (VERTEX_RADIUS*0.866, VERTEX_RADIUS/2),     # bottom-right
]
CENTER_OFFSET = (0, 0)

# Z ranges per color
Z_RANGES_RGB = {
    "red":    (-0.5, -2.0),
    "yellow": (-0.5, -2.0),
    "blue":   (-0.5, -2.0),
    "white":  (-0.5, -2.0),
}
Z_RANGES_CMYK = {
    "cyan":    (-0.5, -2.0),
    "magenta": (-0.5, -2.0),
    "yellow":  (-0.5, -2.0),
    "black":   (-0.5, -2.0),
}

COLOR_ORDER_RGB6 = ["red","yellow","blue","white"]
COLOR_ORDER_CMYK = ["cyan","magenta","yellow","black"]

PALETTES = {
    "rgb6": COLOR_ORDER_RGB6,
    "cmyk": COLOR_ORDER_CMYK
}

@dataclass
class Station:
    name: str
    x: float; y: float
    z_pick: float; z_safe: float
    dip_x: float; dip_y: float; dip_z: float
    blot_x: float; blot_y: float; blot_z: float
    dip_dwell_s: float; blot_dwell_s: float

def make_stations(palette: str) -> Dict[str, Station]:
    colors = PALETTES[palette]
    stations = {}
    for i, color in enumerate(colors):
        x = STATION_X0 + i * STATION_DX
        y = STATION_Y0 + i * STATION_DY
        stations[color] = Station(
            name=color,
            x=x, y=y,
            z_pick=Z_PICK, z_safe=Z_SAFE,
            dip_x=x + DIP_OFFSET_X, dip_y=y + DIP_OFFSET_Y, dip_z=DIP_OFFSET_Z,
            blot_x=x + BLOT_OFFSET_X, blot_y=y + BLOT_OFFSET_Y, blot_z=BLOT_OFFSET_Z,
            dip_dwell_s=1.0, blot_dwell_s=0.5
        )
    return stations

# -------------------------------
# Helpers
# -------------------------------

def lerp(a,b,t): return a + (b-a)*t

def value_to_z(color,value,z_ranges):
    if value <= 0.0: return None
    zmin,zmax = z_ranges[color]
    return lerp(zmin,zmax,value)

# -------------------------------
# Main
# -------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--palette", choices=["rgb6","cmyk"], default="rgb6")
    parser.add_argument("--output", required=True)
    parser.add_argument("--origin-x", type=float, default=0.0)
    parser.add_argument("--origin-y", type=float, default=0.0)
    parser.add_argument("--dot-pitch-mm", type=float, default=30.0,
                        help="Spacing between clusters in X and Y")
    parser.add_argument("--grid-cols", type=int, default=5)
    parser.add_argument("--grid-rows", type=int, default=5)
    args = parser.parse_args()

    stations = make_stations(args.palette)
    colors = PALETTES[args.palette]

    if args.palette=="rgb6":
        z_ranges = Z_RANGES_RGB
    else:
        z_ranges = Z_RANGES_CMYK

    lines=[]; g=lines.append
    g(f"(Paint mixing grid for {args.palette})")
    g("G21 G90 G94")
    g(f"G0 Z{Z_TRAVEL:.1f}")

    def move_xy(x,y): g(f"G0 X{x:.3f} Y{y:.3f} F{FEED_TRAVEL}")
    def move_z(z,feed=FEED_Z): g(f"G1 Z{z:.3f} F{feed}")
    def dwell(s): g(f"G4 P{s*TIME_SCALE:.0f}")

    def pickup_brush(st: Station):
        g(f"(Pickup {st.name})")
        move_xy(st.x,st.y); move_z(st.z_safe); move_z(st.z_pick); dwell(0.3); move_z(st.z_safe)

    def return_brush(st: Station):
        g(f"(Return {st.name})")
        move_xy(st.x,st.y); move_z(st.z_safe); move_z(st.z_pick); dwell(0.3); move_z(st.z_safe)

    def dip_brush(st: Station):
        g(f"(Dip {st.name})")
        move_xy(st.dip_x,st.dip_y); move_z(st.z_safe); move_z(st.dip_z); dwell(st.dip_dwell_s); move_z(st.z_safe)
        move_xy(st.blot_x,st.blot_y); move_z(st.z_safe); move_z(st.blot_z); dwell(st.blot_dwell_s); move_z(st.z_safe)

    def paint_dot(x,y,z):
        move_xy(x,y)
        move_z(Z_PREPAINT)
        move_z(z)
        dwell(0.1)
        move_z(Z_TRAVEL)

    # generate clusters
    for row in range(args.grid_rows):
        for col in range(args.grid_cols):
            base_x = args.origin_x + col * args.dot_pitch_mm
            base_y = args.origin_y + row * args.dot_pitch_mm

            # assign values systematically
            t_x = col/(args.grid_cols-1) if args.grid_cols>1 else 0
            t_y = row/(args.grid_rows-1) if args.grid_rows>1 else 0

            if args.palette=="rgb6":
                values = {
                    "red": t_x,
                    "yellow": t_y,
                    "blue": 0.5,
                    "white": 1.0
                }
            else: # cmyk
                values = {
                    "cyan": t_x,
                    "magenta": t_y,
                    "yellow": 0.5,
                    "black": 0.0
                }

            g(f"(Cluster row {row} col {col})")

            # 3 vertices
            for (color,offset) in zip(colors[:3],TRIANGLE_OFFSETS):
                st=stations[color]
                val=values[color]
                z=value_to_z(color,val,z_ranges)
                if z is None: continue
                pickup_brush(st); dip_brush(st)
                x=base_x+offset[0]; y=base_y+offset[1]
                g(f"( {color} value={val:.2f} z={z:.2f} )")
                paint_dot(x,y,z)
                return_brush(st)

            # center
            center_color=colors[3]
            st=stations[center_color]
            val=values[center_color]
            z=value_to_z(center_color,val,z_ranges)
            if z is not None:
                pickup_brush(st); dip_brush(st)
                cx,cy=CENTER_OFFSET
                g(f"( {center_color} value={val:.2f} z={z:.2f} )")
                paint_dot(base_x+cx,base_y+cy,z)
                return_brush(st)

    # end safely
    g(f"G0 Z{Z_TRAVEL:.1f}")
    g("G0 X0 Y0")
    g("M2")

    with open(args.output,"w") as f:
        f.write("\n".join(lines))
    print("Wrote",args.output)

if __name__=="__main__":
    main()
