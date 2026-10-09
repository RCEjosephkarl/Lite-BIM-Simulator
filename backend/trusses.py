"""Connected conceptual truss graphs; geometry validation is not a load design.

Nodes are in the truss plane: x along the span, y above the bearing plane.
Every chord is split at its connected nodes, including overhang/bearing joints.
"""
import math

WEB_ROLES = {"web", "king_post", "queen_post"}
ROLES = WEB_ROLES | {"top_chord", "bottom_chord", "girder"}
MAX_TOPOLOGY_MEMBERS = 4096


def validate_graph(nodes, members):
    if len(nodes) < 3 or not members:
        raise ValueError("truss requires at least three connected nodes and members")
    positions = list(nodes.values())
    if any(math.dist(a, b) < 1 for i, a in enumerate(positions) for b in positions[i + 1:]):
        raise ValueError("truss nodes must have distinct positions at least 1 mm apart")
    a = positions[0]
    b = max(positions[1:], key=lambda point: math.dist(a, point))
    if not any(abs((b[0]-a[0])*(point[1]-a[1])-(b[1]-a[1])*(point[0]-a[0])) > math.dist(a,b)
               for point in positions):
        raise ValueError("truss nodes must form a non-collinear framework")
    roles = {member[2] for member in members}
    if not {"top_chord", "bottom_chord"} <= roles or not roles & WEB_ROLES:
        raise ValueError("truss requires top chords, bottom chords and connected web/post members")
    adjacency = {identifier: set() for identifier in nodes}
    edges = set()
    for start, end, role, *_ in members:
        if role not in ROLES:
            raise ValueError(f"unknown truss member role: {role}")
        if start not in nodes or end not in nodes:
            raise ValueError("truss member references unknown node")
        if math.dist(nodes[start], nodes[end]) < 1:
            raise ValueError("truss members must be at least 1 mm long")
        edge = tuple(sorted((start, end)))
        if edge in edges:
            raise ValueError("duplicate/overlapping truss members")
        edges.add(edge)
        adjacency[start].add(end)
        adjacency[end].add(start)
    visited, queue = set(), [next(iter(nodes))]
    while queue:
        node = queue.pop()
        if node not in visited:
            visited.add(node)
            queue.extend(adjacency[node] - visited)
    if visited != set(nodes):
        raise ValueError("truss has disconnected members or unused nodes")
    if len(edges) < len(nodes):
        raise ValueError("truss chords and webs must form a closed framework")
    # Crossings must have a shared node, rather than merely overlapping boxes.
    for i, first in enumerate(members):
        a, b = nodes[first[0]], nodes[first[1]]
        for second in members[i + 1:]:
            if {first[0], first[1]} & {second[0], second[1]}:
                continue
            c, d = nodes[second[0]], nodes[second[1]]
            rx, ry, sx, sy = b[0]-a[0], b[1]-a[1], d[0]-c[0], d[1]-c[1]
            determinant = rx*sy - ry*sx
            if abs(determinant) < 1e-8:
                continue
            t = ((c[0]-a[0])*sy - (c[1]-a[1])*sx) / determinant
            u = ((c[0]-a[0])*ry - (c[1]-a[1])*rx) / determinant
            if 1e-6 < t < 1-1e-6 and 1e-6 < u < 1-1e-6:
                raise ValueError("crossing truss members require an explicit shared node")


def split_at_nodes(nodes, members):
    """A node lying on a member becomes a real endpoint in the graph."""
    result = []
    for start, end, *attributes in members:
        ax, ay = nodes[start]
        bx, by = nodes[end]
        dx, dy = bx-ax, by-ay
        length_squared = dx*dx + dy*dy
        if length_squared < 1:
            raise ValueError("truss members must be at least 1 mm long")
        points = [(0, start), (1, end)]
        for identifier, (x, y) in nodes.items():
            if identifier in {start, end}:
                continue
            position = ((x-ax)*dx + (y-ay)*dy) / length_squared
            if 1e-8 < position < 1-1e-8 and math.dist((x, y), (ax+position*dx, ay+position*dy)) < .01:
                points.append((position, identifier))
        points.sort()
        result.extend((left[1], right[1], *attributes) for left, right in zip(points, points[1:]))
        if len(result) > MAX_TOPOLOGY_MEMBERS:
            raise ValueError(f"one truss exceeds the {MAX_TOPOLOGY_MEMBERS} topology member limit")
    return result


def continuous_chords(nodes, members):
    """Template chord joints connect webs without prescribing a saw cut.

    Only join collinear chord chains with matching sections/materials. Custom
    input rows are explicit cuts and never pass through this template helper.
    """
    remaining = list(members)
    result = []
    while remaining:
        start, end, role, size, material = remaining.pop(0)
        if role in {"top_chord", "bottom_chord"}:
            extended = True
            while extended:
                extended = False
                for endpoint, other in ((start, end), (end, start)):
                    incident = [(i, edge) for i, edge in enumerate(remaining)
                                if edge[2:] == (role, size, material) and endpoint in edge[:2]]
                    if len(incident) != 1:
                        continue
                    index, edge = incident[0]
                    next_node = edge[1] if edge[0] == endpoint else edge[0]
                    a, b, c = nodes[other], nodes[endpoint], nodes[next_node]
                    ab, bc = (b[0]-a[0], b[1]-a[1]), (c[0]-b[0], c[1]-b[1])
                    if (abs(ab[0]*bc[1]-ab[1]*bc[0]) <= .001 * math.dist(a, b)
                            and ab[0]*bc[0]+ab[1]*bc[1] > 0):
                        remaining.pop(index)
                        if endpoint == start:
                            start = next_node
                        else:
                            end = next_node
                        extended = True
                        break
        result.append((start, end, role, size, material))
    return result


def graph_with_cuts(nodes, cuts, include_cuts):
    cuts = [(a, b, role, size, material, f"cut-{i:04d}", math.dist(nodes[a], nodes[b]))
            for i, (a, b, role, size, material) in enumerate(cuts, start=1)]
    members = split_at_nodes(nodes, cuts)
    validate_graph(nodes, members)
    return nodes, members if include_cuts else [member[:5] for member in members]


def canonical_graph(spec, include_cuts=False):
    if spec.truss_type == "custom":
        nodes = {node.id: (node.x, node.y) for node in spec.nodes}
        members = [(m.start_node, m.end_node, m.element_type, m.size, m.material) for m in spec.members]
        if any(start not in nodes or end not in nodes for start, end, *_ in members):
            raise ValueError("truss member references unknown node")
        return graph_with_cuts(nodes, members, include_cuts)

    nodes, members, aliases = {}, [], {}
    half = spec.span_mm / 2
    slope = math.tan(math.radians(spec.pitch_deg))
    rise, heel = half*slope, spec.heel_height_mm

    def node(identifier, x, y):
        # Zero heel/overhang deliberately share bearing/eave nodes.
        existing = next((key for key, value in nodes.items() if math.dist(value, (x,y)) < .01), None)
        aliases[identifier] = existing or identifier
        if not existing:
            nodes[identifier] = (x,y)

    def member(start, end, role):
        start, end = aliases[start], aliases[end]
        if start == end:
            return
        size, material = ((spec.top_chord_size, spec.top_chord_material) if role == "top_chord" else
                          (spec.bottom_chord_size, spec.bottom_chord_material) if role == "bottom_chord" else
                          (spec.web_size, spec.web_material))
        members.append((start, end, role, size, material))

    node("BL", -half, 0)
    node("BR", half, 0)
    node("TL", -half, heel)
    if spec.truss_type == "mono":
        node("TR", half, heel+2*rise)
        node("Q", 0, heel+rise)
        node("BC", 0, 0)
        node("EL", -half-spec.overhang_mm, heel-spec.overhang_mm*slope)
        node("ER", half+spec.overhang_mm, heel+2*rise+spec.overhang_mm*slope)
        for start,end in [("EL","TL"),("TL","Q"),("Q","TR"),("TR","ER")]:
            member(start,end,"top_chord")
        member("BL","BR","bottom_chord")
        for start,end in [("BL","TL"),("BR","TR"),("BC","Q"),("Q","BR")]:
            member(start,end,"web")
    else:
        node("TR", half, heel)
        node("A", 0, heel+rise)
        node("Q1", -half/2, heel+rise/2)
        node("Q2", half/2, heel+rise/2)
        node("EL", -half-spec.overhang_mm, heel-spec.overhang_mm*slope)
        node("ER", half+spec.overhang_mm, heel-spec.overhang_mm*slope)
        for start,end in [("EL","TL"),("TL","Q1"),("Q1","A"),("A","Q2"),("Q2","TR"),("TR","ER")]:
            member(start,end,"top_chord")
        for start,end in [("BL","TL"),("BR","TR")]:
            member(start,end,"web")
        if spec.truss_type == "attic":
            node("FL", -spec.span_mm*.18, 0)
            node("FR", spec.span_mm*.18, 0)
            node("UL", -spec.span_mm*.18, rise*.4)
            node("UR", spec.span_mm*.18, rise*.4)
            for start,end in [("BL","FL"),("FL","FR"),("FR","BR")]:
                member(start,end,"bottom_chord")
            for start,end in [("FL","UL"),("FR","UR")]:
                member(start,end,"queen_post")
            for start,end in [("Q1","FL"),("Q1","UL"),("UL","A"),("A","UR"),("UR","Q2"),("FR","Q2"),("UL","UR")]:
                member(start,end,"web")
        else:
            node("BC", 0, rise*.45 if spec.truss_type == "scissor" else 0)
            member("BL","BC","bottom_chord")
            member("BC","BR","bottom_chord")
            member("BC","A","king_post")
            member("Q1","BC","web")
            member("BC","Q2","web")
    return graph_with_cuts(nodes, continuous_chords(nodes, members), include_cuts)
