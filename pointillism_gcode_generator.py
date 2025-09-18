#!/usr/bin/env python3
"""
pointillism_gcode_generator.py
Pointillism-style painting with RGB6 or CMYK palette.
"""

import argparse, os, math
from dataclasses import dataclass
from typing import Dict, Tuple, List
from PIL import Image

# -------------------------------
# CONSTANTS (EDIT TO MATCH MACHINE)
# -------------------------------

# Station grid layout
STATION_X0 = 0.0     # X of first station
STATION_Y0 = 400.0   # Y of first station
STATION_DX = 100.0   # ΔX between stations
STATION_DY = 0.0     # ΔY between stations

# Dip & blot offsets relative to each station
DIP_OFFSET_X  = 0.0
DIP_OFFSET_Y  = 0.0
DIP_OFFSET_Z  = -3.0

BLOT_OFFSET_X = 0.0
BLOT_OFFSET_Y = 60.0
BLOT_OFFSET_Z = -2.0

# Z levels
Z_PICK = -5.0
Z_SAFE = 15.0
Z_TRAVEL = 10.0
Z_PREPAINT = 2.0
Z_PAINT = -1.0

# Motion / paint
FEED_TRAVEL = 2500
FEED_Z = 600
DAB_DWELL_S = 0.05
RE_DIP_EVERY_N_DOTS = 120
RE_DIP_AFTER_TRAVEL_MM = 180.0
CLEAN_AT_END = True

# Time scaling (RichAuto B58 uses ms for G4 P)
TIME_SCALE = 1000.0   # multiply dwell seconds by this factor

WHITE_THRESHOLD = 240

COLOR_ORDER_RGB6 = ["black", "blue", "red", "green", "yellow", "white"]
COLOR_ORDER_CMYK = ["yellow", "magenta", "cyan", "black"]

PALETTES = {
    "rgb6": COLOR_ORDER_RGB6,
    "cmyk": COLOR_ORDER_CMYK
}

PALETTE_RGB = {
    "red":    (220, 20, 60),
    "green":  (34, 139, 34),
    "blue":   (30, 144, 255),
    "yellow": (255, 215, 0),
    "black":  (0, 0, 0),
    "white":  (255, 255, 255),
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
    """Auto-generate stations for the selected palette."""
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
# Color conversion & dithering
# -------------------------------

def nearest_palette_color(rgb: Tuple[int,int,int]) -> str:
    r,g,b = rgb
    best, best_d2 = None, 1e18
    for name,(R,G,B) in PALETTE_RGB.items():
        d2 = (r-R)**2 + (g-G)**2 + (b-B)**2
        if d2 < best_d2:
            best, best_d2 = name, d2
    return best

def rgb_to_cmyk(r,g,b):
    R,G,B = [x/255.0 for x in (r,g,b)]
    K = 1 - max(R,G,B)
    if K >= 1.0:
        return (0,0,0,1)
    C = (1-R-K)/(1-K)
    M = (1-G-K)/(1-K)
    Y = (1-B-K)/(1-K)
    return (C,M,Y,K)

def floyd_steinberg_dither_channel(img_chan, w,h):
    arr = [[img_chan[y][x] for x in range(w)] for y in range(h)]
    out = [[0]*w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            old = arr[y][x]
            new = 1 if old >= 0.5 else 0
            out[y][x] = new
            err = old - new
            if x+1<w: arr[y][x+1]+=err*7/16
            if y+1<h and x>0: arr[y+1][x-1]+=err*3/16
            if y+1<h: arr[y+1][x]+=err*5/16
            if y+1<h and x+1<w: arr[y+1][x+1]+=err*1/16
    return out

def serpentine_indices(w,h):
    order=[]
    for j in range(h):
        row=[(i,j) for i in range(w)]
        if j%2==1: row.reverse()
        order.extend(row)
    return order

# -------------------------------
# G-code generation
# -------------------------------

def gen_gcode(color_points, color_order, grid_cols, grid_rows, stations, args):
    lines=[]; g=lines.append
    g("(Pointillism painting)")
    g(f"(Grid {grid_cols}x{grid_rows}, pitch {args.dot_pitch_mm} mm)")
    g("G21"); g("G90"); g("G94")
    g(f"G0 Z{Z_TRAVEL:.3f}")

    origin_x=args.origin_x+args.margin_mm
    origin_y=args.origin_y+args.margin_mm

    def xy_of_pixel(px,py):
        return (origin_x+px*args.dot_pitch_mm,
                origin_y+py*args.dot_pitch_mm)
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

    serp=serpentine_indices(grid_cols,grid_rows)
    for color in color_order:
        pts=color_points[color]
        if not pts: continue
        g(f"(=== {color} {len(pts)} dots ===)")
        pickup_brush(color); dip_brush(color)
        dots_since=0; travel_since=0.0
        last=None
        for (px,py) in serp:
            if (px,py) not in pts: continue
            x_mm,y_mm=xy_of_pixel(px,py)
            if last is not None:
                travel_since+=math.hypot(x_mm-last[0], y_mm-last[1])
            if dots_since>=RE_DIP_EVERY_N_DOTS or (RE_DIP_AFTER_TRAVEL_MM>0 and travel_since>=RE_DIP_AFTER_TRAVEL_MM):
                dip_brush(color); dots_since=0; travel_since=0.0
            paint_dot(x_mm,y_mm,DAB_DWELL_S)
            dots_since+=1; last=(x_mm,y_mm)
        if CLEAN_AT_END:
            st=stations[color]; move_xy(st.blot_x,st.blot_y); move_z(st.z_safe); move_z(st.blot_z); dwell(0.3); move_z(st.z_safe)
        return_brush(color)

    g("G0 Z{:.3f}".format(Z_TRAVEL))
    g("G0 X0 Y0")
    g("M2")
    return "\n".join(lines)

# -------------------------------
# Main
# -------------------------------

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--width-mm",type=float,required=True)
    parser.add_argument("--height-mm",type=float,required=True)
    parser.add_argument("--dot-pitch-mm",type=float,default=3.0)
    parser.add_argument("--origin-x",type=float,default=0.0)
    parser.add_argument("--origin-y",type=float,default=0.0)
    parser.add_argument("--margin-mm",type=float,default=0.0)
    parser.add_argument("--palette",choices=["rgb6","cmyk"],default="rgb6")
    args=parser.parse_args()

    im=Image.open(args.input).convert("RGB")
    usable_w=max(0.0,args.width_mm-2*args.margin_mm)
    usable_h=max(0.0,args.height_mm-2*args.margin_mm)
    grid_cols=max(1,int(round(usable_w/args.dot_pitch_mm)))
    grid_rows=max(1,int(round(usable_h/args.dot_pitch_mm)))
    im_resized=im.resize((grid_cols,grid_rows),Image.LANCZOS)

    stations=make_stations(args.palette)
    color_points={}

    if args.palette=="rgb6":
        for c in PALETTE_RGB.keys():
            color_points[c]=[]
        for y in range(grid_rows):
            for x in range(grid_cols):
                rgb=im_resized.getpixel((x,y))
                if rgb[0]>=WHITE_THRESHOLD and rgb[1]>=WHITE_THRESHOLD and rgb[2]>=WHITE_THRESHOLD:
                    continue
                col=nearest_palette_color(rgb)
                color_points[col].append((x,y))
        gcode=gen_gcode(color_points,COLOR_ORDER_RGB6,grid_cols,grid_rows,stations,args)

    else: # cmyk
        Cchan=[[0]*grid_cols for _ in range(grid_rows)]
        Mchan=[[0]*grid_cols for _ in range(grid_rows)]
        Ychan=[[0]*grid_cols for _ in range(grid_rows)]
        Kchan=[[0]*grid_cols for _ in range(grid_rows)]
        for y in range(grid_rows):
            for x in range(grid_cols):
                r,g,b=im_resized.getpixel((x,y))
                C,M,Y,K=rgb_to_cmyk(r,g,b)
                Cchan[y][x]=C; Mchan[y][x]=M; Ychan[y][x]=Y; Kchan[y][x]=K
        Cd=floyd_steinberg_dither_channel(Cchan,grid_cols,grid_rows)
        Md=floyd_steinberg_dither_channel(Mchan,grid_cols,grid_rows)
        Yd=floyd_steinberg_dither_channel(Ychan,grid_cols,grid_rows)
        Kd=floyd_steinberg_dither_channel(Kchan,grid_cols,grid_rows)
        color_points={"cyan":[], "magenta":[], "yellow":[], "black":[]}
        for y in range(grid_rows):
            for x in range(grid_cols):
                if Cd[y][x]==1: color_points["cyan"].append((x,y))
                if Md[y][x]==1: color_points["magenta"].append((x,y))
                if Yd[y][x]==1: color_points["yellow"].append((x,y))
                if Kd[y][x]==1: color_points["black"].append((x,y))
        gcode=gen_gcode(color_points,COLOR_ORDER_CMYK,grid_cols,grid_rows,stations,args)

    with open(args.output,"w",encoding="utf-8") as f:
        f.write(gcode)
    print("Wrote",args.output)

if __name__=="__main__":
    main()
