#!/usr/bin/env python3
"""
calibration_swatch.py
Generate calibration swatch dots for RGB6 or CMYK palettes.

- Uses pickup_brush, paint_dot, and return_brush
- Dots arranged starting at --origin-x, --origin-y
- Spacing (rows & columns) = --dot-pitch-mm
"""

import argparse
from dataclasses import dataclass
from typing import Dict

# -------------------------------
# CONSTANTS (shared with generator)
# -------------------------------

# Station grid layout
STATION_X0 = 0.0     # X of first station
STATION_Y0 = 400.0   # Y of first station
STATION_DX = 100.0   # ΔX between stations
STATION_DY = 0.0     # ΔY between stations

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
Z_PAINT = -1.0

# Motion
FEED_TRAVEL = 2000
FEED_Z = 600

# Time scaling (RichAuto B58 uses ms for G4 P)
TIME_SCALE = 1000.0

# Dwell progression
DAB_DWELL_BASE = 0.05
DAB_DWELL_STEP = 0.05

DOTS_PER_COLOR = 5

COLOR_ORDER_RGB6 = ["black","blue","red","green","yellow","white"]
COLOR_ORDER_CMYK = ["yellow","magenta","cyan","black"]

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
# Calibration swatch generator
# -------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--palette", choices=["rgb6","cmyk"], default="rgb6")
    parser.add_argument("--output", required=True)
    parser.add_argument("--origin-x", type=float, default=0.0, help="X origin of first swatch dot")
    parser.add_argument("--origin-y", type=float, default=0.0, help="Y origin of first swatch dot")
    parser.add_argument("--dot-pitch-mm", type=float, default=20.0, help="Spacing between dots (both row and column)")
    args = parser.parse_args()

    stations = make_stations(args.palette)
    colors = PALETTES[args.palette]

    lines = []
    g = lines.append
    g(f"(Calibration swatch for {args.palette})")
    g("G21 G90 G94")
    g(f"G0 Z{Z_TRAVEL:.1f}")

    # helpers
    def move_xy(x,y): g(f"G0 X{x:.3f} Y{y:.3f} F{FEED_TRAVEL}")
    def move_z(z,feed=FEED_Z): g(f"G1 Z{z:.3f} F{feed}")
    def dwell(s): g(f"G4 P{s*TIME_SCALE:.0f}")

    def pickup_brush(color):
        st=stations[color]
        g(f"(Pickup {color})")
        move_xy(st.x,st.y); move_z(st.z_safe); move_z(st.z_pick); dwell(0.3); move_z(st.z_safe)

    def return_brush(color):
        st=stations[color]
        g(f"(Return {color})")
        move_xy(st.x,st.y); move_z(st.z_safe); move_z(st.z_pick); dwell(0.3); move_z(st.z_safe)

    def dip_brush(color):
        st=stations[color]
        g(f"(Dip {color})")
        move_xy(st.dip_x,st.dip_y); move_z(st.z_safe); move_z(st.dip_z); dwell(st.dip_dwell_s); move_z(st.z_safe)
        move_xy(st.blot_x,st.blot_y); move_z(st.z_safe); move_z(st.blot_z); dwell(st.blot_dwell_s); move_z(st.z_safe)

    def paint_dot(x,y,dwell_time):
        move_xy(x,y)
        move_z(Z_PREPAINT)
        move_z(Z_PAINT)
        dwell(dwell_time)
        move_z(Z_TRAVEL)

    # loop over colors
    for ci, color in enumerate(colors):
        pickup_brush(color)
        dip_brush(color)
        for j in range(DOTS_PER_COLOR):
            x = args.origin_x + ci * args.dot_pitch_mm
            y = args.origin_y + j * args.dot_pitch_mm
            dwell_time = DAB_DWELL_BASE + j * DAB_DWELL_STEP
            g(f"(Color {color}, dot {j+1}, dwell {dwell_time:.2f}s)")
            paint_dot(x,y,dwell_time)
        return_brush(color)

    g("G0 Z{:.3f}".format(Z_TRAVEL))
    g("G0 X0 Y0")
    g("M2")
    with open(args.output,"w") as f:
        f.write("\n".join(lines))
    print("Wrote", args.output)

if __name__=="__main__":
    main()
