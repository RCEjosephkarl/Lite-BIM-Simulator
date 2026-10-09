"""Shared wall framing and logical-run panel layout in millimetres.

Fabrication joins are geometric intent, not verified bracing/connection design.
Joint end studs are adjacent physical pieces, rather than coincident duplicates.
"""
import hashlib
import math

import nzs3604 as nz


def panel_layout(spec, breadth):
    length = math.hypot(spec.end_x_mm-spec.start_x_mm, spec.end_z_mm-spec.start_z_mm)
    limit = 6000 if spec.wall_height_mm <= 3000 else 3000
    if not spec.panelize:
        return [(0., length)]
    if spec.wall_height_mm > 6000:
        raise ValueError("panel height exceeds the 6 m x 3 m interchangeable envelope")
    clearance = 3 * breadth
    protected = [(o.start_offset_mm-clearance, o.start_offset_mm+o.width_mm+clearance)
                 for o in sorted(spec.openings, key=lambda item: item.start_offset_mm)]
    panels, start = [], 0.
    while length-start > limit + .001:
        cut = min(start+limit, length-300)
        for left, right in reversed(protected):
            if left < cut < right:
                cut = left
        if cut-start < 300:
            raise ValueError("No panel joint fits outside the opening/jamb zone within the 6 m x 3 m envelope; provide an engineered panel layout")
        panels.append((start, cut))
        start = cut
    panels.append((start, length))
    return panels


def frame(spec, source, sid, make, section, warnings):
    segment_id = spec.segment_id or sid
    dx, dy = spec.end_x_mm-spec.start_x_mm, spec.end_z_mm-spec.start_z_mm
    length = math.hypot(dx, dy)
    ux, uy, yaw = dx/length, dy/length, math.atan2(dy, dx)
    base = (spec.level-1)*nz.STOREY_RISE
    stud_depth, breadth = section(spec.stud_size)
    intrinsic = int(spec.stud_size.split('/')[0]) if '/' in spec.stud_size else 1
    stud_width = breadth * intrinsic
    bottom_h = section(spec.bottom_plate_size)[1] * (int(spec.bottom_plate_size.split('/')[0]) if '/' in spec.bottom_plate_size else 1)
    top_h = section(spec.top_plate_size)[1] * (int(spec.top_plate_size.split('/')[0]) if '/' in spec.top_plate_size else 1)
    clear_top = spec.wall_height_mm-2*top_h
    panels = panel_layout(spec, breadth*intrinsic)
    warnings = list(warnings)
    if len(panels) > 1:
        warnings.append(f"{segment_id}: {len(panels)} panels within the 6 m x 3 m envelope; plate joins, connections and bracing require qualified design")
    if spec.wall_height_mm > 3000:
        warnings.append("tall-wall height requires specific review; the interchangeable panel envelope is not a stud-sizing rule")
    if not math.isclose(stud_depth, spec.wall_thickness_mm, abs_tol=.01):
        warnings.append("stud section governs member depth; declared wall thickness differs and requires review")
    elements, verticals, seen_verticals = [], [], {}

    def panel_id(index): return f"{segment_id}:P{index+1:03d}"

    def add(code, size, material, a, b, z1, z2, panel, opening="", joint="", vertical=False):
        if (z2-z1 if vertical else b-a) <= 1:
            return
        station = a if vertical else (a+b)/2
        depth, width = section(size)
        intrinsic = int(size.split('/')[0]) if '/' in size else 1
        key = (round(station, 6), round(z1, 6), round(z2, 6))
        if vertical and key in seen_verticals:
            existing = seen_verticals[key]
            if opening:
                existing["opening_id"] = opening
                if code == "trimmer_stud": existing["type_code"] = code
            if joint: existing["joint_id"] = joint
            return
        physical = hashlib.sha256(f"{sid}:{spec.level}:{segment_id}:{code}:{a:.6f}:{b:.6f}:{z1:.6f}:{z2:.6f}".encode()).hexdigest()[:24]
        cross = depth if vertical or code != "lintel" else width * intrinsic
        item = make(code, spec.level, size, material, spec.treatment,
                    z2-z1 if vertical else b-a, cross*spec.plies,
                    stud_width if vertical else z2-z1,
                    spec.start_x_mm+ux*station, spec.start_z_mm+uy*station,
                    base+(z1+z2)/2, yaw, math.pi/2 if vertical else 0,
                    source, sid, "; ".join(warnings), plies=spec.plies,
                    segment_id=segment_id, segment_label=spec.segment_label,
                    stud_spacing_mm=spec.stud_spacing_mm, warnings=warnings,
                    panel_id=panel_id(panel), joint_id=joint, opening_id=opening,
                    physical_member_id=physical, exterior=spec.exterior,
                    load_bearing=spec.load_bearing, engineering_status="unchecked")
        elements.append(item)
        if vertical:
            seen_verticals[key] = item
            verticals.append((station,z1,z2))

    def horizontal(code, size, a,b,z1,z2, opening=""):
        for index,(left,right) in enumerate(panels):
            start,end = max(left,a),min(right,b)
            if end > start:
                add(code,size,spec.lintel_material if code=="lintel" else spec.plate_material,
                    start,end,z1,z2,index,opening)

    def vertical(code, station,z1,z2, index=None, opening="", joint=""):
        if index is None:
            index = next((i for i,(_,right) in enumerate(panels) if station < right+.001),len(panels)-1)
        add(code,spec.stud_size,spec.stud_material,station,station,z1,z2,index,opening,joint,True)

    openings = sorted(spec.openings,key=lambda opening: opening.start_offset_mm)
    doors = [(opening.start_offset_mm,opening.start_offset_mm+opening.width_mm)
             for opening in openings if opening.sill_height_mm == 0]
    cursor = 0.
    for start,end in doors:
        horizontal("plate_bottom",spec.bottom_plate_size,cursor,start,0,bottom_h)
        cursor = end
    horizontal("plate_bottom",spec.bottom_plate_size,cursor,length,0,bottom_h)
    horizontal("plate_top",spec.top_plate_size,0,length,clear_top,clear_top+top_h)
    horizontal("plate_top",spec.top_plate_size,0,length,clear_top+top_h,spec.wall_height_mm)

    excluded = [(opening.start_offset_mm-2*stud_width,opening.start_offset_mm+opening.width_mm+2*stud_width)
                for opening in openings]
    station = spec.stud_spacing_mm
    grid = []
    while station < length-stud_width/2:
        grid.append(station)
        station += spec.stud_spacing_mm
    # Each fabrication panel owns its own non-overlapping end studs.
    ends = []
    for index,(left,right) in enumerate(panels):
        for station, boundary in [(left+stud_width/2,left),(right-stud_width/2,right)]:
            joint = f"{segment_id}:J{boundary:.6f}" if 0 < boundary < length else ""
            vertical("stud",station,bottom_h,clear_top,index,joint=joint)
            ends.append(station)
    for station in grid:
        if not any(a-stud_width < station < a+stud_width for a in ends) and not any(a <= station <= b for a,b in excluded):
            vertical("stud",station,bottom_h,clear_top)

    blocking = []
    for index,opening in enumerate(openings):
        a,b = opening.start_offset_mm,opening.start_offset_mm+opening.width_mm
        sill = opening.sill_height_mm
        head = opening.head_height_mm or sill+opening.height_mm
        identifier = opening.opening_id or f"O{index+1:03d}"
        for station in (a-1.5*stud_width,b+1.5*stud_width):
            vertical("trimmer_stud",station,bottom_h,clear_top,opening=identifier)
        for station in (a-stud_width/2,b+stud_width/2):
            vertical("jack_stud",station,bottom_h,head,opening=identifier)
        size = opening.lintel_size or nz.lintel_for_span(opening.width_mm)[0]
        lintel_top = head+section(size)[0]
        horizontal("lintel",size,a-stud_width,b+stud_width,head,lintel_top,identifier)
        if sill > 0:
            horizontal("sill_trimmer",spec.stud_size,a,b,sill-stud_width,sill,identifier)
        for station in grid:
            if a+stud_width/2 <= station <= b-stud_width/2:
                if sill > 0:
                    vertical("jack_stud",station,bottom_h,sill-stud_width,opening=identifier)
                vertical("jack_stud",station,lintel_top,clear_top,opening=identifier)
        blocking.append((a,b,max(0,sill-stud_width),lintel_top))

    if spec.nog_spacing_mm:
        heights, height = [],bottom_h+spec.nog_spacing_mm
        while height < clear_top:
            heights.append(height)
            height += spec.nog_spacing_mm
    else:
        heights = [bottom_h+(clear_top-bottom_h)*row/(spec.nog_count+1) for row in range(1,spec.nog_count+1)]
    for height in heights:
        stations = sorted({station for station,z1,z2 in verticals if z1 <= height-stud_width/2 and z2 >= height+stud_width/2})
        for a,b in zip(stations,stations[1:]):
            left,right = a+stud_width/2,b-stud_width/2
            if right-left <= 1 or any(x1 < right and x2 > left and z1 < height+stud_width/2 and z2 > height-stud_width/2 for x1,x2,z1,z2 in blocking):
                continue
            horizontal("nog",spec.stud_size,left,right,height-stud_width/2,height+stud_width/2)
    return elements,warnings
