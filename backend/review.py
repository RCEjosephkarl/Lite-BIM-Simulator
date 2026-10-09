"""Auditable software diagnostics, deliberately separate from design approval.

Limits and clause labels are taken from this repository's simplified profile.
No entry asserts that its standards/manufacturer basis has been independently
verified. Passing a geometry diagnostic never clears member/load-path review.
"""
from __future__ import annotations

import hashlib
import json
import math

import materials
import nzs3604 as nz

PROFILE_ID="NZS3604:2011-conceptual"
PROFILE_VERSION=2
STATUSES={"reference_only","evaluated_within_assumptions","requires_specific_design","not_evaluated"}

RULES={
    "profile.height":("Source height-envelope assumption","nzs3604.py: general scope","Modelled geometry; site ground datum and standards basis require review"),
    "profile.exposure":("Wind/snow inputs",f"{nz.WIND_REF}; {nz.SNOW_REF}","User exposure inputs; site classification and loads are unverified"),
    "wall.stud-assumptions":("Simplified stud selection","Table 8.2","SG8 90x45, one frame ply, 2400 mm stud height; no loaded dimension/capacity check"),
    "floor.span-assumption":("Simplified joist span",nz.JOIST_REF,"190x45 SG8 at nominal 450 mm centres; loads, deflection, bearings and joints are unverified"),
    "truss.topology":("Truss geometry connectivity","trusses.py canonical graph","Connected physical endpoints, chords/webs and a closed graph outline; no force/capacity analysis"),
    "truss.bearings":("Automatic truss bearing alignment","Home roof bearing wall references","BL/BR physical nodes on referenced wall runs and actual wall tops within 1 mm; support capacity and connections are not evaluated"),
    "truss.design":("Truss design and supplier review","Supplier / specific engineering","Reactions, member/joint capacity, bracing, uplift and fabrication are not evaluated"),
    "model.references":("Member reference labels","nzs3604.py ELEMENT_TYPES","Clause labels identify source references; independent standards audit is pending"),
    "model.load-path":("Complete building load path","Qualified structural review","Foundation, bracing, connections, hold-downs, floor/roof junctions and loaded dimensions are not evaluated"),
    "roof.junction":("Roof zone junction","Home definition roof zones","Intersecting zones require designed trim, valley framing and load transfer"),
}


def _topology(members):
    if any(not m.get("start_node") or not m.get("end_node") for m in members):
        return None,"Node identities are missing in this legacy geometry"
    graph={};points={};roles=set()
    for m in members:
        roles.add(m.get("member_role"))
        dx=math.cos(m["yaw"])*math.cos(m["pitch"])*m["length_mm"]/2
        dy=math.sin(m["yaw"])*math.cos(m["pitch"])*m["length_mm"]/2
        dz=math.sin(m["pitch"])*m["length_mm"]/2
        for name,sign in ((m["start_node"],-1),(m["end_node"],1)):
            point=(m["cx"]+sign*dx,m["cy"]+sign*dy,m["cz"]+sign*dz)
            if name in points and math.dist(point,points[name])>1:
                return False,f"Shared node {name} has inconsistent physical endpoints"
            points[name]=point
        graph.setdefault(m["start_node"],set()).add(m["end_node"])
        graph.setdefault(m["end_node"],set()).add(m["start_node"])
    seen=set();todo=[next(iter(graph))]
    while todo:
        node=todo.pop()
        if node not in seen:seen.add(node);todo.extend(graph[node]-seen)
    closed=sum(len(v) for v in graph.values())//2>=len(graph)
    chords={"top_chord","bottom_chord"}<=roles
    webs=bool(roles&{"web","king_post","queen_post"})
    valid=len(seen)==len(graph) and closed and chords and webs
    return valid,"Connected chord/web geometry" if valid else "Truss graph is disconnected, lacks chords/webs, or has no closed outline"


def _bearing_alignment(members,roof,wall_specs,wall_members):
    references=roof.get("bearing_wall_ids")
    if not references or len(references)!=2:
        return None,"Roof bearing walls are unspecified",{}
    nodes={}
    for member in members:
        half=member["length_mm"]/2
        delta=(math.cos(member["yaw"])*math.cos(member["pitch"])*half,
               math.sin(member["yaw"])*math.cos(member["pitch"])*half,math.sin(member["pitch"])*half)
        for field,sign in (("start_node",-1),("end_node",1)):
            name=member.get(field)
            if name in {"BL","BR"}:
                point=tuple(member[c]+sign*d for c,d in zip(("cx","cy","cz"),delta))
                if name in nodes and math.dist(nodes[name],point)>1:
                    return False,"Physical bearing node endpoints disagree",{"bearing_wall_ids":references}
                nodes[name]=point
    if set(nodes)!={"BL","BR"}:
        return None,"Physical BL/BR bearing node identities are missing",{"bearing_wall_ids":references}
    inputs={"bearing_wall_ids":references,"bearing_nodes_mm":nodes,"wall_tops_mm":{},"tolerance_mm":1}
    aligned=True
    for name,ident in zip(("BL","BR"),references):
        wall=wall_specs.get(ident)
        actual=wall_members.get(ident)
        if not wall or not actual:return None,"Referenced wall geometry is missing",inputs
        spec=wall["spec"];a=(spec["start_x_mm"],spec["start_z_mm"]);b=(spec["end_x_mm"],spec["end_z_mm"])
        dx,dy=b[0]-a[0],b[1]-a[1];den=dx*dx+dy*dy
        if not den:return None,"Referenced wall run has no usable length",inputs
        p=nodes[name];t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den))
        top=max(m["cz"]+abs(math.sin(m["pitch"]))*m["length_mm"]/2+abs(math.cos(m["pitch"]))*m["h_mm"]/2 for m in actual)
        inputs["wall_tops_mm"][ident]=top
        aligned &= math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)<=1 and abs(p[2]-top)<=1
    return bool(aligned),("Physical bearing nodes align with referenced wall geometry" if aligned else
                          "Physical bearing nodes lie away from referenced wall runs or wall tops"),inputs


def evaluate(elements,params,home=None):
    checks=[]
    def add(code,status,cause,action,member=None,inputs=None,count=1):
        title,reference,assumptions=RULES[code]
        source=member.get("source","generated") if member else "model"
        sid=member.get("source_id","") if member else ""
        entity=(member.get("segment_id") or member.get("truss_id") or sid) if member else ""
        level=member.get("storey") if member else None
        ident=hashlib.sha256(json.dumps((code,source,sid,entity,level),ensure_ascii=False).encode()).hexdigest()[:20]
        checks.append(dict(id=ident,code=code,status=status,severity="warning" if status=="requires_specific_design" else "info",
            title=title,message=cause,cause=cause,next_action=action,rule_reference=reference,rule_version=PROFILE_VERSION,
            assumptions=assumptions,basis_review_status="not_independently_verified",source=source,source_id=sid,
            entity_id=entity,level=level,element_id=member.get("id") if member else None,occurrences=count,inputs=inputs or {}))
    timber=[m for m in elements if m.get("type_code") in nz.ELEMENT_TYPES and nz.ELEMENT_TYPES[m["type_code"]][1]!="concrete"]
    highest_timber_level=max((m["storey"] for m in timber),default=1)
    zmin=min((m["cz"]-abs(math.sin(m["pitch"]))*m["length_mm"]/2-abs(math.cos(m["pitch"]))*m["h_mm"]/2 for m in timber),default=None)
    zmax=max((m["cz"]+abs(math.sin(m["pitch"]))*m["length_mm"]/2+abs(math.cos(m["pitch"]))*m["h_mm"]/2 for m in timber),default=None)
    datum=min((l["elevation_mm"] for l in home.get("levels",[])),default=None) if home else None
    height=zmax-datum if zmax is not None and datum is not None else None
    height_inputs=dict(model_z_min_mm=zmin,model_z_max_mm=zmax,lowest_level_elevation_mm=datum,
                       height_above_lowest_level_mm=height,source_candidate_limit_mm=10000)
    if height is None:
        add("profile.height","not_evaluated","An explicit level/ground datum is unavailable","Set project levels and confirm the site ground datum before scope assessment",inputs=height_inputs)
    elif height>10000:
        add("profile.height","requires_specific_design",f"Model height {height/1000:.2f} m exceeds the source profile's candidate 10 m envelope",
            "Have a qualified reviewer verify the actual height and applicable scope",inputs=height_inputs)
    else:
        add("profile.height","evaluated_within_assumptions",f"Model height {height/1000:.2f} m is within the source candidate envelope",
            "Verify ground datum, jurisdiction and standards assumptions; this does not establish overall applicability",inputs=height_inputs)
    exposure=dict(wind_zone=params.get("wind_zone"),wind_speed=params.get("wind_speed"),snow_zone=params.get("snow_zone"))
    outside=params.get("wind_zone")=="sed" or params.get("snow_zone")=="N5"
    add("profile.exposure","requires_specific_design" if outside else "reference_only",
        "Exposure input exceeds the simplified profile" if outside else "Wind/snow selection uses unverified user/site inputs",
        "Verify site exposure, loading and standards/manufacturer applicability",inputs=exposure)
    add("model.references","reference_only","Member clause labels are reference information","Audit each advertised rule and record reviewer, edition/amendments and supported inputs",count=len(timber))
    add("model.load-path","not_evaluated","Complete building load path and structural capacity are not evaluated",
        "Review foundations, bracing, uplift, connections, roof/floor junctions and member capacity",count=len(timber))
    groups={}
    wall_specs={w["id"]:w for w in home.get("walls",[])} if home else {}
    roof_specs={r["id"]:r for r in home.get("roofs",[]) if r.get("system")=="truss"} if home else {}
    wall_members={}
    for m in timber:
        if m.get("source")=="generated" and m.get("source_id") in wall_specs:
            wall_members.setdefault(m["source_id"],[]).append(m)
        entity=m.get("segment_id") or m.get("truss_id") or m.get("source_id","")
        groups.setdefault((m.get("source"),m.get("source_id"),m.get("storey"),entity),[]).append(m)
    for members in groups.values():
        first=members[0]
        studs=[m for m in members if m["type_code"] in {"stud","trimmer_stud","jack_stud"}]
        if studs:
            bad=[m for m in studs if m["length_mm"]>2400.01 or m.get("size")!="90x45"
                 or materials.normalise_material_key(m.get("material"))!="sg8" or m.get("plies",1)!=1
                 or m.get("stud_spacing_mm") is None
                 or m["stud_spacing_mm"]>nz.stud_spacing(m["storey"],highest_timber_level,params.get("wind_zone","medium"))]
            add("wall.stud-assumptions","requires_specific_design" if bad else "reference_only",
                "Wall geometry/material/spacing/ply inputs differ from the simplified stud assumptions" if bad else "Stud dimensions match the source assumptions; capacity and loaded dimensions remain unchecked",
                "Verify loaded dimension, actual height, material/section, spacing, ply connections and loading",bad[0] if bad else studs[0],
                inputs=dict(max_stud_length_mm=max(m["length_mm"] for m in studs),materials=sorted({m["material"] for m in studs}),
                            sections=sorted({m["size"] for m in studs}),spacing_mm=sorted({m.get("stud_spacing_mm") for m in studs},key=str)),count=len(studs))
        joists=[m for m in members if m["type_code"]=="joist"]
        if joists:
            floor=next((f for f in home.get("floors",[]) if f["id"]==first.get("source_id")),None) if home else None
            spacing=floor.get("spacing_mm",450) if floor else None
            bad=[m for m in joists if m["length_mm"]>nz.JOIST_MAX_SPAN or m["size"]!="190x45" or materials.normalise_material_key(m.get("material"))!="sg8" or (spacing is not None and spacing>450)]
            add("floor.span-assumption","requires_specific_design" if bad else "reference_only" if spacing is not None else "not_evaluated",
                "A joist span/section/material differs from the simplified source assumptions" if bad else "Joist span matches the source assumption; loading, deflection and support capacity remain unchecked",
                "Review joist loading, spacing, deflection, bearings, holes and connections",bad[0] if bad else joists[0],
                inputs=dict(max_span_mm=max(m["length_mm"] for m in joists),source_span_limit_mm=nz.JOIST_MAX_SPAN,spacing_mm=spacing),count=len(joists))
        trusses=[m for m in members if m["type_code"].startswith("truss_")]
        if trusses:
            valid,cause=_topology(trusses)
            add("truss.topology","not_evaluated" if valid is None else "evaluated_within_assumptions" if valid else "requires_specific_design",
                cause,"Inspect physical endpoints and chords/webs, then obtain supplier design",trusses[0],count=len(trusses))
            roof=roof_specs.get(first.get("source_id")) if first.get("source")=="generated" else None
            if roof:
                aligned,cause,inputs=_bearing_alignment(trusses,roof,wall_specs,wall_members)
                add("truss.bearings","not_evaluated" if aligned is None else "evaluated_within_assumptions" if aligned else "requires_specific_design",
                    cause,"Inspect physical support positions; regenerate older automatic layouts, then review bearing capacity and connections with the supplier",
                    trusses[0],inputs=inputs,count=2)
            add("truss.design","requires_specific_design","Truss member and joint capacity, reactions and connections require supplier/specific design",
                "Obtain the supplier layout, reactions, bracing and connector specification",trusses[0],count=len(trusses))
    if home:
        roofs=home.get("roofs",[])
        for i,r in enumerate(roofs):
            for other in roofs[:i]:
                if r["level_id"]==other["level_id"] and all(min(a,b)>max(c,d) for a,b,c,d in zip(r["maximum_mm"],other["maximum_mm"],r["minimum_mm"],other["minimum_mm"])):
                    member=next((m for m in timber if m.get("source")=="generated" and m.get("source_id")==r["id"]),None)
                    add("roof.junction","requires_specific_design",f"Roof zones {other['id']} and {r['id']} overlap",
                        "Design junction/valley/trim members and support reactions before using quantities",member,
                        inputs=dict(roof_zone_ids=[other["id"],r["id"]]))
    statuses={status:sum(c["status"]==status for c in checks) for status in sorted(STATUSES)}
    return dict(profile=dict(id=PROFILE_ID,version=PROFILE_VERSION,jurisdiction="New Zealand reference profile",
                             review_status="not_independently_verified",structural_approval=False),
                overall_status="requires_specific_design" if statuses["requires_specific_design"] else "not_evaluated",
                height=height_inputs,checks=checks,status_counts=statuses,
                rule_register=[dict(code=code,title=data[0],reference=data[1],assumptions=data[2],version=PROFILE_VERSION,
                                    review_status="not_independently_verified") for code,data in RULES.items()],
                disclaimer="Software geometry/source-assumption diagnostics only; qualified standards, site and supplier review remains required")
