"""Versioned home geometry in millimetres: east/north plan, elevation up.

Definitions describe geometry and intent; they are not a structural approval.
Manual/CSV assemblies continue to use their existing contracts and generators.
"""
from __future__ import annotations

import math
import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

import geometry as g
import materials
import nzs3604 as nz
from geometry_checks import advance, bounded_count, finite, midpoint
from manual_inputs import (MAX_MEMBERS, ManualOpening, ManualWallFrameInput,
                          ManualTrussInput, estimated_member_count,
                          generate_wall, generate_truss)

Point = tuple[float, float]


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Level(Entity):
    id: str = Field(min_length=1, max_length=120)
    label: str = "Level"
    number: int = Field(ge=1, le=20)
    elevation_mm: float = 0
    wall_height_mm: float = Field(default=2535, gt=300)


class HomeOpening(ManualOpening):
    model_config = ConfigDict(extra="forbid",allow_inf_nan=False)


class HomeWallSpec(ManualWallFrameInput):
    model_config = ConfigDict(extra="forbid",allow_inf_nan=False)
    openings: list[HomeOpening] = Field(default_factory=list,max_length=1024)


class WallRun(Entity):
    id: str = Field(min_length=1, max_length=120)
    level_id: str
    inherit_design_settings: bool = True
    spec: HomeWallSpec


class Support(Entity):
    id: str = Field(min_length=1, max_length=120)
    start_mm: Point
    end_mm: Point

    @model_validator(mode="after")
    def valid_segment(self):
        length = math.dist(self.start_mm, self.end_mm)
        finite("support length", length)
        if length <= 1:
            raise ValueError("support segment must be longer than 1 mm")
        return self


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def on_segment(p, a, b, tolerance=0.01):
    length = math.dist(a, b)
    if length <= 0:
        return math.dist(p, a) <= tolerance
    return (abs(cross(a, b, p))/length <= tolerance
            and min(a[0], b[0])-tolerance <= p[0] <= max(a[0], b[0])+tolerance
            and min(a[1], b[1])-tolerance <= p[1] <= max(a[1], b[1])+tolerance)


def intersects(a, b, c, d):
    if any((on_segment(c, a, b), on_segment(d, a, b),
            on_segment(a, c, d), on_segment(b, c, d))):
        return True
    return cross(a,b,c)*cross(a,b,d) < 0 and cross(c,d,a)*cross(c,d,b) < 0


def edges(poly):
    return list(zip(poly, poly[1:]+poly[:1]))


def inside(p, poly):
    hits = 0
    for a,b in edges(poly):
        if on_segment(p,a,b):
            return True
        if (a[1] > p[1]) != (b[1] > p[1]):
            x = a[0]+(p[1]-a[1])*(b[0]-a[0])/(b[1]-a[1])
            hits += x > p[0]
    return bool(hits % 2)


def validate_polygon(poly):
    if len(set(poly)) != len(poly):
        raise ValueError("polygon vertices must be unique; do not repeat the closing vertex")
    segments = edges(poly)
    origin = poly[0]
    area = abs(sum((a[0]-origin[0])*(b[1]-origin[1])-(b[0]-origin[0])*(a[1]-origin[1]) for a,b in segments))/2
    if not math.isfinite(area) or area <= 1:
        raise ValueError("polygon must enclose a finite positive area")
    for i,(a,b) in enumerate(segments):
        if math.dist(a,b) <= 1:
            raise ValueError("polygon edges must be longer than 1 mm")
        previous=poly[(i-1)%len(poly)]
        if on_segment(b,previous,a) or on_segment(previous,a,b):
            raise ValueError("adjacent polygon edges must not reverse or overlap")
        for j,(c,d) in enumerate(segments):
            if j <= i or j == i+1 or (i == 0 and j == len(segments)-1):
                continue
            if intersects(a,b,c,d):
                raise ValueError("polygon edges must not intersect")


class Floor(Entity):
    id: str = Field(min_length=1, max_length=120)
    level_id: str
    purpose: Literal["floor", "ceiling"] = "floor"
    boundary_mm: list[Point] = Field(min_length=3, max_length=512)
    holes_mm: list[list[Point]] = Field(default_factory=list, max_length=64)
    joist_direction_deg: float = 0
    spacing_mm: float = Field(default=450, ge=100)
    first_offset_mm: float = Field(default=225, ge=0)
    elevation_offset_mm: float | None = None
    supports: list[Support] = Field(default_factory=list, max_length=1024)

    @model_validator(mode="after")
    def valid_boundary(self):
        validate_polygon(self.boundary_mm)
        for i,hole in enumerate(self.holes_mm):
            if not 3 <= len(hole) <= 512:
                raise ValueError("floor holes need 3–512 vertices")
            validate_polygon(hole)
            if not all(inside(p,self.boundary_mm) for p in hole):
                raise ValueError("floor hole must lie inside its boundary")
            others = [self.boundary_mm]+self.holes_mm[:i]
            if any(intersects(a,b,c,d) for a,b in edges(hole)
                   for other in others for c,d in edges(other)):
                raise ValueError("floor holes must not touch a boundary or another hole")
            if any(inside(hole[0],h) or inside(h[0],hole) for h in self.holes_mm[:i]):
                raise ValueError("floor holes must not overlap or nest")
        ids = [s.id for s in self.supports]
        if len(set(ids)) != len(ids):
            raise ValueError("support IDs must be unique within each floor")
        return self


class RoofZone(Entity):
    id: str = Field(min_length=1, max_length=120)
    level_id: str
    minimum_mm: Point
    maximum_mm: Point
    ridge_axis: Literal["x", "y"] = "x"
    shape: Literal["gable", "hip"] = "gable"
    system: Literal["rafter", "truss"] = "rafter"
    inherit_shape: bool = False
    pitch_deg: float = Field(default=25, ge=1, le=80)
    spacing_mm: float = Field(default=900, ge=100)
    overhang_mm: float = Field(default=450, ge=0)
    heel_height_mm: float = Field(default=100, ge=0)
    gable_end_inset_mm: float = Field(default=0,ge=0)
    first_offset_mm: float = Field(default=0, ge=0)
    last_offset_mm: float | None = Field(default=None, ge=0)
    bearing_wall_ids: tuple[str, str] | None = None
    truss_type: Literal["common", "girder", "mono", "scissor", "attic"] = "common"
    top_chord_size: str = "140x45"
    bottom_chord_size: str = "90x45"
    web_size: str = "90x45"
    material: str = "SG8"
    treatment: Literal["H1.2", "H3.1", "H3.2", "H4", "H5"] = "H1.2"

    @model_validator(mode="after")
    def valid_roof(self):
        finite("roof extents", *(b-a for a,b in zip(self.minimum_mm,self.maximum_mm)))
        if any(b-a <= 500 for a,b in zip(self.minimum_mm,self.maximum_mm)):
            raise ValueError("roof zone needs positive extents greater than 500 mm")
        ridge_length = self.maximum_mm[0 if self.ridge_axis == "x" else 1]-self.minimum_mm[0 if self.ridge_axis == "x" else 1]
        last = ridge_length if self.last_offset_mm is None else self.last_offset_mm
        if not self.first_offset_mm <= last <= ridge_length:
            raise ValueError("roof first/last placement must lie in order within the ridge extent")
        if self.gable_end_inset_mm*2>=ridge_length:
            raise ValueError("gable end inset must leave a positive ridge extent")
        if self.system == "truss" and (self.shape != "gable" or self.inherit_shape):
            raise ValueError("automatic truss zones require an explicit gable shape; hip transitions need a reviewed layout")
        ManualTrussInput(top_chord_size=self.top_chord_size,
                         bottom_chord_size=self.bottom_chord_size, web_size=self.web_size)
        if (ridge_length+self.maximum_mm[1]-self.minimum_mm[1]+self.maximum_mm[0]-self.minimum_mm[0]
                +2*self.overhang_mm)/min(300,self.spacing_mm) > MAX_MEMBERS/20:
            raise ValueError("roof extents exceed the member generation budget")
        return self


class Slab(Entity):
    id: str = Field(min_length=1, max_length=120)
    label: str = "Floor slab"
    level_id: str
    minimum_mm: Point
    maximum_mm: Point
    thickness_mm: float = Field(default=100, gt=0)

    @model_validator(mode="after")
    def positive(self):
        if any(b <= a for a,b in zip(self.minimum_mm,self.maximum_mm)):
            raise ValueError("slab extents must be positive")
        finite("slab extents", *(b-a for a,b in zip(self.minimum_mm,self.maximum_mm)))
        return self


class Porch(Entity):
    id: str = Field(min_length=1, max_length=120)
    level_id: str
    post_xs_mm: list[float] = Field(min_length=2, max_length=500)
    front_y_mm: float
    back_y_mm: float
    minimum_x_mm: float
    maximum_x_mm: float
    beam_base_mm: float = Field(default=2300, gt=0)
    wall_bearing_mm: float = Field(default=2700, gt=0)
    spacing_mm: float = Field(default=900, ge=100)

    @model_validator(mode="after")
    def positive(self):
        if self.maximum_x_mm <= self.minimum_x_mm or self.back_y_mm <= self.front_y_mm:
            raise ValueError("porch extents must be positive")
        width = self.maximum_x_mm - self.minimum_x_mm
        finite("porch extents", width, self.back_y_mm-self.front_y_mm)
        bounded_count(width-250, self.spacing_mm, MAX_MEMBERS, "porch rafter layout")
        rafters = math.floor((width-250)/self.spacing_mm)+1 if width>=250 else 0
        beams = bounded_count(width, 6000, MAX_MEMBERS, "porch beam layout") if width>1 else 0
        if rafters + beams + len(self.post_xs_mm) > MAX_MEMBERS:
            raise ValueError("porch exceeds the member generation budget")
        if any(not self.minimum_x_mm <= x <= self.maximum_x_mm for x in self.post_xs_mm):
            raise ValueError("porch posts must lie within the beam extent")
        return self


class HomeDefinition(Entity):
    schema_version: Literal[1] = 1
    units: Literal["mm"] = "mm"
    name: str = Field(default="Home", min_length=1, max_length=200)
    template: Literal["sample", "custom"] = "custom"
    rule_profile: Literal["NZS3604:2011-conceptual"] = "NZS3604:2011-conceptual"
    levels: list[Level] = Field(min_length=1, max_length=20)
    walls: list[WallRun] = Field(default_factory=list, max_length=1000)
    floors: list[Floor] = Field(default_factory=list, max_length=100)
    roofs: list[RoofZone] = Field(default_factory=list, max_length=100)
    slabs: list[Slab] = Field(default_factory=list, max_length=100)
    porches: list[Porch] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def references(self):
        ids = [x.id for x in self.levels]
        numbers = [x.number for x in self.levels]
        if len(set(ids)) != len(ids) or len(set(numbers)) != len(numbers):
            raise ValueError("level IDs and numbers must be unique")
        elevations = [x.elevation_mm for x in sorted(self.levels,key=lambda l:l.number)]
        if any(b <= a for a,b in zip(elevations,elevations[1:])):
            raise ValueError("level elevations must increase with level numbers")
        entities = self.walls+self.floors+self.roofs+self.slabs+self.porches
        entity_ids = [x.id for x in entities]
        if len(set(entity_ids)) != len(entity_ids):
            raise ValueError("home entity IDs must be unique across categories")
        if not entities:
            raise ValueError("home definition must contain geometry")
        if any(x.level_id not in ids for x in entities):
            raise ValueError("entity references an unknown level ID")
        level_map={l.id:l for l in self.levels}
        for wall in self.walls:
            if "wall_height_mm" not in wall.spec.model_fields_set:
                wall.spec.wall_height_mm=level_map[wall.level_id].wall_height_mm
                wall.spec=HomeWallSpec.model_validate(wall.spec.model_dump())
            opening_ids=[]
            for opening in wall.spec.openings:
                if not opening.opening_id:
                    data=(wall.id,opening.opening_type,opening.start_offset_mm,opening.width_mm,opening.height_mm,opening.sill_height_mm)
                    opening.opening_id=wall.id+":opening:"+hashlib.sha256(repr(data).encode()).hexdigest()[:12]
                opening_ids.append(opening.opening_id)
            if len(set(opening_ids))!=len(opening_ids):
                raise ValueError("opening IDs must be unique within each wall")
        wall_map = {w.id:w for w in self.walls}
        for r in self.roofs:
            if r.bearing_wall_ids:
                if len(set(r.bearing_wall_ids)) != 2 or any(w not in wall_map for w in r.bearing_wall_ids):
                    raise ValueError("roof bearing walls must reference two distinct wall IDs")
                if any(wall_map[w].level_id != r.level_id for w in r.bearing_wall_ids):
                    raise ValueError("roof bearing walls must belong to its level")
        if sum(estimated_member_count(w.spec) for w in self.walls) > MAX_MEMBERS:
            raise ValueError("home walls exceed the member generation budget")
        return self


def sample_definition(cfg) -> HomeDefinition:
    """Extract the existing house into explicit entities without changing options."""
    import framing
    levels=[]; walls=[]; floors=[]; roofs=[]
    for s in range(1,cfg.storeys+1):
        lid=f"L{s}"
        levels.append(Level(id=lid,label=f"Level {s}",number=s,
                            elevation_mm=(s-1)*nz.STOREY_RISE))
        source = ((g.ground_exterior_walls()+g.ground_interior_walls()) if s == 1
                  else (g.upper_exterior_walls()+g.upper_interior_walls()))
        counters={True:0,False:0}
        for w in source:
            counters[w.exterior]+=1
            ident=f"{'G' if s == 1 else lid}-{'EXT' if w.exterior else 'INT'}-{counters[w.exterior]:03d}"
            label=f"L{s} {'Exterior' if w.exterior else 'Interior'} Wall {counters[w.exterior]:02d}"
            walls.append(WallRun(id=ident,level_id=lid,spec=HomeWallSpec(
                level=s,segment_id=ident,segment_label=label,start_x_mm=w.x1,start_z_mm=w.y1,
                end_x_mm=w.x2,end_z_mm=w.y2,panelize=True,exterior=w.exterior,
                openings=[HomeOpening(opening_id=f"{ident}:O{i+1:03d}",
                    opening_type=o.kind if o.kind in {"door","window","garage"} else "custom",
                    start_offset_mm=o.offset,width_mm=o.width,height_mm=o.head-o.sill,
                    sill_height_mm=o.sill,head_height_mm=o.head) for i,o in enumerate(w.openings)])))
        poly=g.UPPER_POLY_FT if s < cfg.storeys or cfg.storeys > 1 else g.EXTERIOR_POLY_FT
        boundary=[(g.ft(x),g.ft(y)) for x,y in poly]
        # Explicit extents reproduce the legacy sample's support assumptions.
        supports=[Support(id=f"support-{i+1}",start_mm=(x,min(y for _,y in boundary)),
                          end_mm=(x,max(y for _,y in boundary))) for i,x in enumerate(g.JOIST_SUPPORT_XS)]
        floors.append(Floor(id=f"{lid}-{'platform' if s < cfg.storeys else 'ceiling'}",level_id=lid,
            purpose="floor" if s < cfg.storeys else "ceiling",boundary_mm=boundary,supports=supports,
            spacing_mm=nz.JOIST_SPACING if s < cfg.storeys else nz.CEILING_JOIST_SPACING,
            first_offset_mm=225 if s < cfg.storeys else 300))
    for i,(x1,y1,x2,y2,axis) in enumerate(g.MAIN_ROOF_FT+[g.GARAGE_ROOF_FT]):
        roofs.append(RoofZone(id=f"roof-{i+1}",level_id=f"L{cfg.storeys if i < len(g.MAIN_ROOF_FT) else 1}",
            minimum_mm=(g.ft(x1),g.ft(y1)),maximum_mm=(g.ft(x2),g.ft(y2)),ridge_axis=axis,
            inherit_shape=True,shape=cfg.roof,spacing_mm=nz.rafter_spacing(cfg.snow_zone),gable_end_inset_mm=g.ft(1)))
    slabs=[Slab(id=f"slab-{i+1}",label=label,level_id="L1",minimum_mm=(g.ft(x1),g.ft(y1)),
                maximum_mm=(g.ft(x2),g.ft(y2))) for i,(label,x1,y1,x2,y2) in enumerate(g.SLAB_RECTS_FT)]
    porch=Porch(id="porch",level_id="L1",post_xs_mm=[g.ft(x) for x in g.PORCH_POST_XS_FT],
                front_y_mm=g.ft(g.PORCH_POST_Y_FT),back_y_mm=g.ft(g.PORCH_BACK_Y_FT),
                minimum_x_mm=g.ft(g.PORCH_X1_FT),maximum_x_mm=g.ft(g.PORCH_X2_FT),spacing_mm=nz.RAFTER_SPACING)
    return HomeDefinition(name="Sample home",template="sample",levels=levels,walls=walls,
                          floors=floors,roofs=roofs,slabs=slabs,porches=[porch])


def scan_intervals(poly, y):
    """Half-open scanline works for simple polygons, including sloped edges."""
    xs=[]
    for a,b in edges(poly):
        if (a[1] <= y < b[1]) or (b[1] <= y < a[1]):
            xs.append(a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1]))
    xs.sort()
    return list(zip(xs[::2],xs[1::2]))


def _floor(elements, floor, level, note):
    import framing
    angle=math.radians(floor.joist_direction_deg)
    c,s=math.cos(angle),math.sin(angle)
    origin=floor.boundary_mm[0]
    def local(p):
        x,y=p[0]-origin[0],p[1]-origin[1]
        result=(x*c+y*s,-x*s+y*c)
        finite("floor local coordinates", *result)
        return result
    def world(u,v):return (origin[0]+u*c-v*s,origin[1]+u*s+v*c)
    poly=[local(p) for p in floor.boundary_mm]
    holes=[[local(p) for p in h] for h in floor.holes_mm]
    supports=[(local(s.start_mm),local(s.end_mm)) for s in floor.supports]
    ys=[p[1] for p in poly]
    y=min(ys)+floor.first_offset_mm
    rows=[]
    depth,breadth=nz.JOIST_SIZE if floor.purpose == "floor" else nz.CEILING_JOIST_SIZE
    size="190x45" if floor.purpose == "floor" else "90x45"
    code="joist" if floor.purpose == "floor" else "ceiling_joist"
    z=level.elevation_mm+(level.wall_height_mm if floor.elevation_offset_mm is None else floor.elevation_offset_mm)
    count=bounded_count(max(ys)-y,floor.spacing_mm,MAX_MEMBERS,"floor scan rows")
    first_y=y
    for row in range(count):
        y=first_y+row*floor.spacing_mm
        if y>=max(ys):break
        intervals=scan_intervals(poly,y)
        for h in holes:
            intervals=[piece for a,b in intervals for piece in framing._complement(a,b,scan_intervals(h,y))]
        crossings=[]
        for a,b in supports:
            if min(a[1],b[1]) <= y <= max(a[1],b[1]) and abs(b[1]-a[1]) > 0.001:
                crossings.append(a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1]))
        for a,b in intervals:
            cuts=sorted(set(x for x in crossings if a+300 < x < b-300))
            for aa,bb in zip([a]+cuts,cuts+[b]):
                n=note
                if floor.purpose == "floor" and bb-aa > nz.JOIST_MAX_SPAN:
                    n=f"span {(bb-aa)/1000:.1f} m > {nz.JOIST_MAX_SPAN/1000:.1f} m ({nz.JOIST_REF}) — add support/SED"
                x,wy=world(midpoint(aa,bb),y)
                framing._el(elements,code,level.number,size,bb-aa,breadth,depth,x,wy,z+depth/2,angle,0,note=n)
        rows.append(y)
        if len(elements) > MAX_MEMBERS:raise ValueError("home exceeds the member generation budget")
    # Blocking follows each actual support segment between adjacent joist rows.
    if floor.purpose == "floor":
        for a,b in supports:
            if abs(b[1]-a[1]) < 0.001:continue
            for ya,yb in zip(rows,rows[1:]):
                if not min(a[1],b[1]) <= ya < yb <= max(a[1],b[1]):continue
                def sx(y):return a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1])
                xm=sx((ya+yb)/2)
                iv=scan_intervals(poly,(ya+yb)/2)
                if not any(p+200 < xm < q-200 for p,q in iv):continue
                if any(inside((xm,(ya+yb)/2),h) for h in holes):continue
                p,q=world(sx(ya),ya),world(sx(yb),yb)
                if any(intersects((sx(ya),ya),(sx(yb),yb),ha,hb) for h in holes for ha,hb in edges(h)):
                    continue
                framing._el(elements,"blocking",level.number,size,math.dist(p,q)-breadth,breadth,depth,
                    (p[0]+q[0])/2,(p[1]+q[1])/2,z+depth/2,math.atan2(q[1]-p[1],q[0]-p[0]),0,note=note)


def _porch(elements, p, level, note):
    import framing
    z=level.elevation_mm;beam_z=z+p.beam_base_mm;top=beam_z+nz.PORCH_BEAM_SIZE[0]
    for x in p.post_xs_mm:
        framing._el(elements,"post",level.number,"90x90",p.beam_base_mm,90,90,x,p.front_y_mm,
                    z+p.beam_base_mm/2,0,math.pi/2,treatment=nz.OUTDOOR_TREATMENT,note=note)
    for a,b in framing._split(p.minimum_x_mm,p.maximum_x_mm):
        framing._el(elements,"beam",level.number,"2/190x45",b-a,90,nz.PORCH_BEAM_SIZE[0],
                    (a+b)/2,p.front_y_mm,(beam_z+top)/2,0,0,treatment=nz.OUTDOOR_TREATMENT,note=note)
    dy=p.back_y_mm-p.front_y_mm;dz=z+p.wall_bearing_mm-top
    x=p.minimum_x_mm+150
    while x <= p.maximum_x_mm-100:
        framing._el(elements,"rafter",level.number,"140x45",math.hypot(dy,dz),45,140,x,
                    (p.front_y_mm+p.back_y_mm)/2,(top+z+p.wall_bearing_mm)/2,
                    math.pi/2,math.atan2(dz,dy),treatment=nz.OUTDOOR_TREATMENT,note=note)
        x=advance(x,p.spacing_mm,"porch rafter placement")
        if len(elements)>MAX_MEMBERS:raise ValueError("home exceeds the member generation budget")


def _roof_elevation(roof, level, walls):
    heights=[walls[wid].spec.wall_height_mm for wid in roof.bearing_wall_ids or ()]
    if heights and max(heights)-min(heights)>1:
        raise ValueError(f"{roof.id}: bearing wall heights must agree")
    return level.elevation_mm+(heights[0] if heights else level.wall_height_mm)


def _truss_roof(elements, roof, level, walls, warnings):
    axis=0 if roof.ridge_axis == "x" else 1
    other=1-axis
    span=roof.maximum_mm[other]-roof.minimum_mm[other]
    length=roof.maximum_mm[axis]-roof.minimum_mm[axis]
    last=length if roof.last_offset_mm is None else roof.last_offset_mm
    offsets=[];offset=roof.first_offset_mm
    while offset <= last+0.001:
        offsets.append(min(offset,last));offset+=roof.spacing_mm
        if len(offsets)*32 > MAX_MEMBERS:raise ValueError("roof layout exceeds the member generation budget")
    if not offsets or last-offsets[-1] > 0.001:offsets.append(last)
    if roof.bearing_wall_ids is None:
        warnings.append(f"{roof.id}: bearing walls are unspecified; review support positions and reactions")
    elif any(not walls[wid].spec.load_bearing for wid in roof.bearing_wall_ids):
        warnings.append(f"{roof.id}: a referenced wall is marked non-bearing; verify the roof load path")
    if roof.truss_type != "common":
        warnings.append(f"{roof.id}: specialized {roof.truss_type} layout is conceptual; transitions, supports and connections require supplier design")
    top=_roof_elevation(roof,level,walls)
    for i,offset in enumerate(offsets):
        start=list(roof.minimum_mm);start[axis]+=offset
        end=start.copy();end[other]=roof.maximum_mm[other]
        if roof.bearing_wall_ids:
            for point,wid in zip((start,end),roof.bearing_wall_ids):
                wall=walls[wid].spec
                if not on_segment(point,(wall.start_x_mm,wall.start_z_mm),(wall.end_x_mm,wall.end_z_mm),1):
                    raise ValueError(f"{roof.id}: truss {i+1} bearing lies outside wall {wid}")
        spec=ManualTrussInput(level=level.number,truss_id=f"{roof.id}:{i+1:03d}",truss_label=roof.id,
            span_mm=span,pitch_deg=roof.pitch_deg,spacing_mm=roof.spacing_mm,quantity=1,
            # Template local bearings are at +/- half span; manual placement
            # names this origin "start", but it is the truss centre.
            start_x_mm=(start[0]+end[0])/2,start_z_mm=(start[1]+end[1])/2,
            direction_deg=90 if axis == 0 else 0,
            top_chord_size=roof.top_chord_size,bottom_chord_size=roof.bottom_chord_size,
            web_size=roof.web_size,top_chord_material=roof.material,bottom_chord_material=roof.material,
            web_material=roof.material,overhang_mm=roof.overhang_mm,heel_height_mm=roof.heel_height_mm,
            treatment=roof.treatment,truss_type=roof.truss_type)
        members,notes=generate_truss(spec,"generated",roof.id,instance_offset=i)
        delta=top-((level.number-1)*nz.STOREY_RISE+2535)
        for m in members:
            m["cz"]+=delta;m["layout_id"]=roof.id;m["editable"]=False
        elements.extend(members);warnings.extend(f"{roof.id}: {n}" for n in notes)


def generate(definition: HomeDefinition, cfg):
    """Generate only the supplied entities; fixed sample constants are adapters."""
    import framing
    cfg=cfg.normalised();els=[];segments=[];warnings=list(cfg.warnings())+list(cfg.override_warnings)
    note="; ".join(cfg.warnings());levels={l.id:l for l in definition.levels}
    walls={w.id:w for w in definition.walls}
    def identify(start, ident):
        for member in els[start:]:
            member.setdefault("source_id",ident)
            if not member.get("physical_member_id"):
                fields=(ident,member["storey"],member["type_code"],member["size"],
                        *(round(member[k],6) for k in ("length_mm","cx","cy","cz","yaw","pitch")))
                member["physical_member_id"]=hashlib.sha256(repr(fields).encode()).hexdigest()[:24]
        if len(els)>MAX_MEMBERS:raise ValueError("home exceeds the member generation budget")
    for slab in definition.slabs:
        start=len(els)
        level=levels[slab.level_id];a,b=slab.minimum_mm,slab.maximum_mm
        framing._el(els,"slab",level.number,f"{slab.thickness_mm:g} thk",b[0]-a[0],b[1]-a[1],slab.thickness_mm,
                    midpoint(a[0],b[0]),midpoint(a[1],b[1]),level.elevation_mm-slab.thickness_mm/2,
                    grade="concrete",treatment="-",note=slab.label)
        identify(start,slab.id)
    for level in sorted(definition.levels,key=lambda l:l.number):
        for wall in (w for w in definition.walls if w.level_id == level.id):
            spec=wall.spec.model_copy(deep=True)
            spec.level=level.number;spec.segment_id=wall.id
            if wall.inherit_design_settings:
                default=nz.stud_spacing(level.number,len(definition.levels),cfg.wind_zone)
                spec.stud_spacing_mm=cfg.effective_stud_spacing(level.number,wall.id,default)
                spec.stud_material=materials.display_name(cfg.effective_stud_material(level.number,wall.id))
                spec.plies=cfg.effective_wall_plies(level.number,wall.id)
                spec.treatment=cfg.wall_treatment or spec.treatment
            spec=ManualWallFrameInput.model_validate(spec.model_dump())
            length=math.hypot(spec.end_x_mm-spec.start_x_mm,spec.end_z_mm-spec.start_z_mm)
            if length>6000:
                warnings.append(f"{wall.id}: wall length {length/1000:.1f} m exceeds the 6 m x 3 m frame envelope — verify panel joins")
            wall_note=note
            if wall.inherit_design_settings and spec.stud_spacing_mm != default:
                wall_note=(f"{note}; " if note else "")+framing.CUSTOM_SPACING_NOTE
            members,_=generate_wall(spec,"generated",wall.id)
            for m in members:
                m["cz"]+=level.elevation_mm-(level.number-1)*nz.STOREY_RISE
                m["editable"]=False;m["note"]="; ".join(filter(None,[wall_note,m["note"]]))
            els.extend(members)
            if len(els)>MAX_MEMBERS:raise ValueError("home exceeds the member generation budget")
            segments.append(dict(segment_id=wall.id,storey=level.number,label=spec.segment_label,length_mm=round(length,1),
                exterior=spec.exterior,openings=len(spec.openings),material=spec.stud_material,
                spacing_mm=spec.stud_spacing_mm,plies=spec.plies,treatment=spec.treatment))
        for floor in (f for f in definition.floors if f.level_id == level.id):
            start=len(els)
            if floor.holes_mm:
                warnings.append(f"{floor.id}: opening trimming/headers and floor load transfer require specific design")
            truss_zones=[r for r in definition.roofs if r.level_id == level.id and r.system == "truss"]
            if floor.purpose == "ceiling" and truss_zones:
                # Clip the ceiling to leave bottom-chord zones clear.
                clipped=floor.model_copy(deep=True)
                clipped.holes_mm += [[r.minimum_mm,(r.maximum_mm[0],r.minimum_mm[1]),r.maximum_mm,
                                      (r.minimum_mm[0],r.maximum_mm[1])] for r in truss_zones]
                _floor(els,clipped,level,note)
            else:_floor(els,floor,level,note)
            identify(start,floor.id)
    for i,roof in enumerate(definition.roofs):
        level=levels[roof.level_id];start=len(els)
        for previous in definition.roofs[:i]:
            if previous.level_id == roof.level_id and all(min(a,b)>max(c,d) for a,b,c,d in
                zip(roof.maximum_mm,previous.maximum_mm,roof.minimum_mm,previous.minimum_mm)):
                warnings.append(f"roof join {previous.id}/{roof.id}: overlapping zones; valley/trim/load transfer unresolved")
        if roof.system == "truss":_truss_roof(els,roof,level,walls,warnings)
        else:
            rect=(*roof.minimum_mm,*roof.maximum_mm,roof.ridge_axis)
            shape=cfg.roof if roof.inherit_shape else roof.shape
            options=dict(units="mm",pitch_deg=roof.pitch_deg,overhang_mm=roof.overhang_mm,
                         heel_height_mm=roof.heel_height_mm,gable_end_inset_mm=roof.gable_end_inset_mm)
            if shape == "hip":framing.frame_hip_roof(els,rect,level.number,_roof_elevation(roof,level,walls),
                                                     roof.spacing_mm,note,**options)
            else:framing.frame_gable_roof(els,rect,level.number,_roof_elevation(roof,level,walls),
                                         roof.spacing_mm,cfg.gable_spacing,note,
                                         material=materials.display_name(cfg.effective_stud_material(level.number)),**options)
        identify(start,roof.id)
    for porch in definition.porches:
        start=len(els);_porch(els,porch,levels[porch.level_id],note);identify(start,porch.id)
    if len(els)>MAX_MEMBERS:raise ValueError("home exceeds the member generation budget")
    if cfg.has_spacing_override():warnings.append(framing.CUSTOM_SPACING_NOTE)
    if max(l.number for l in definition.levels)>3:
        warnings.append("Home level numbers exceed the sample's 1–3 storey range; specific engineering is required")
    known={w.id for w in definition.walls}
    for param in ("stud_material_segments","stud_spacing_segments","wall_plies_segments"):
        for ident in getattr(cfg,param):
            if ident not in known:warnings.append(f"unknown frame segment '{framing._safe(ident)}' in {param} — ignored")
    return framing.GenerateResult(els,segments,list(dict.fromkeys(warnings)))
