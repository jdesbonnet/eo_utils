#!/usr/bin/env python3
"""
Create a single polygon AOI from LineStrings, optionally:
- connect disjoint components with corridor connectors
- remove holes (fill small ones by area threshold)
- optionally "de-hole" by cutting narrow channels from holes to exterior

Dependencies:
  pip install geopandas shapely pyproj
"""

import argparse
import sys
import math

import geopandas as gpd
from shapely.ops import unary_union, nearest_points
from shapely.geometry import Polygon, MultiPolygon, LineString


def choose_metric_crs(gdf: gpd.GeoDataFrame):
    if gdf.crs is None:
        raise ValueError("Input has no CRS. Assign one (often EPSG:4326).")
    if not gdf.crs.is_geographic:
        return gdf.crs
    return gdf.estimate_utm_crs()


def to_polygons(geom):
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    polys = []
    for g in getattr(geom, "geoms", []):
        if isinstance(g, Polygon):
            polys.append(g)
        elif isinstance(g, MultiPolygon):
            polys.extend(list(g.geoms))
    return polys


def morphological_close(geom, dist_m: float):
    return geom.buffer(dist_m).buffer(-dist_m)


def mst_edges(centroids):
    n = len(centroids)
    if n <= 1:
        return []
    in_tree = [False] * n
    in_tree[0] = True
    best_dist = [math.inf] * n
    parent = [-1] * n

    def dist(i, j):
        return centroids[i].distance(centroids[j])

    for j in range(1, n):
        best_dist[j] = dist(0, j)
        parent[j] = 0

    edges = []
    for _ in range(n - 1):
        v = -1
        dmin = math.inf
        for j in range(n):
            if not in_tree[j] and best_dist[j] < dmin:
                dmin = best_dist[j]
                v = j
        if v == -1:
            break
        in_tree[v] = True
        edges.append((parent[v], v))
        for j in range(n):
            if not in_tree[j]:
                d = dist(v, j)
                if d < best_dist[j]:
                    best_dist[j] = d
                    parent[j] = v
    return edges


def connect_components_with_corridors(geom, max_gap_m: float, corridor_halfwidth_m: float, max_iters: int = 5):
    if max_gap_m <= 0:
        return geom, False
    current = geom
    connected_any = False

    for _ in range(max_iters):
        polys = to_polygons(current)
        if len(polys) <= 1:
            return current, connected_any

        centroids = [p.centroid for p in polys]
        edges = mst_edges(centroids)

        connectors = []
        for i, j in edges:
            p_i, p_j = polys[i], polys[j]
            a, b = nearest_points(p_i, p_j)
            if a.distance(b) <= max_gap_m:
                connectors.append(LineString([a, b]).buffer(corridor_halfwidth_m))

        if not connectors:
            return current, connected_any

        connected_any = True
        current = unary_union([current] + connectors).buffer(0)

    return current, connected_any


def fill_holes_by_area(poly: Polygon, max_hole_area_m2: float) -> Polygon:
    """
    Remove interior rings whose area <= max_hole_area_m2 by dropping them from interiors.
    """
    if not isinstance(poly, Polygon):
        raise TypeError("fill_holes_by_area expects a Polygon")

    if max_hole_area_m2 <= 0 or len(poly.interiors) == 0:
        return poly

    keep_interiors = []
    for ring in poly.interiors:
        hole_poly = Polygon(ring)
        if hole_poly.area > max_hole_area_m2:
            keep_interiors.append(ring)

    return Polygon(poly.exterior, keep_interiors)


def extend_segment(line: LineString, extend_m: float) -> LineString:
    """
    Extend a 2-point LineString by extend_m beyond both ends.
    """
    coords = list(line.coords)
    if len(coords) != 2:
        raise ValueError("extend_segment expects a 2-point LineString")

    (x1, y1), (x2, y2) = coords
    dx, dy = (x2 - x1), (y2 - y1)
    length = math.hypot(dx, dy)
    if length == 0:
        return line

    ux, uy = dx / length, dy / length
    p1 = (x1 - ux * extend_m, y1 - uy * extend_m)
    p2 = (x2 + ux * extend_m, y2 + uy * extend_m)
    return LineString([p1, p2])



from shapely.ops import nearest_points
from shapely.geometry import LineString, Polygon

def cut_channels_to_exterior(poly: Polygon, channel_halfwidth_m: float, extend_m: float = 0.0) -> Polygon:
    """
    Remove (difference) a narrow strip connecting each hole to the exterior,
    optionally extending the cut beyond both ends to avoid leaving slivers.
    """
    if len(poly.interiors) == 0:
        return poly

    current = poly
    for _ in range(3):  # a few passes helps on tricky geometries
        if current.geom_type != "Polygon" or len(current.interiors) == 0:
            break

        exterior_line = LineString(current.exterior.coords)

        cuts = []
        for ring in current.interiors:
            hole_line = LineString(ring.coords)
            a, b = nearest_points(hole_line, exterior_line)  # a on hole, b on exterior

            cut_line = LineString([a, b])
            if extend_m and extend_m > 0:
                cut_line = extend_segment(cut_line, extend_m)

            cuts.append(cut_line.buffer(channel_halfwidth_m, cap_style=2, join_style=2))

        if not cuts:
            break

        cut_union = cuts[0]
        for c in cuts[1:]:
            cut_union = cut_union.union(c)

        current = current.difference(cut_union).buffer(0)

        # If it becomes MultiPolygon, keep the largest piece (or reconnect later)
        if current.geom_type == "MultiPolygon":
            current = max(current.geoms, key=lambda p: p.area)

    return current


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_geojson")
    ap.add_argument("output_geojson")
    ap.add_argument("--buffer-m", type=float, required=True, help="Corridor half-width around lines, meters.")
    ap.add_argument("--gap-close-m", type=float, default=0.0, help="Morphological closing distance (meters).")
    ap.add_argument("--connect-gaps-m", type=float, default=0.0,
                    help="Max gap (meters) to connect disjoint buffered components with corridors.")
    ap.add_argument("--connector-width-m", type=float, default=None,
                    help="Half-width of connector corridors (meters). Defaults to --buffer-m.")
    ap.add_argument("--connect-iters", type=int, default=5)
    ap.add_argument("--simplify-m", type=float, default=0.0, help="Simplify tolerance (meters).")

    # Hole cheating options:
    ap.add_argument("--fill-holes-max-area-m2", type=float, default=0.0,
                    help="Fill holes with area <= this threshold (m^2). 0 disables.")
    ap.add_argument("--cut-channels", action="store_true",
                    help="Cut narrow channels from each remaining hole to exterior to eliminate holes.")
    ap.add_argument("--channel-width-m", type=float, default=None,
                    help="Half-width of channels used by --cut-channels. Defaults to buffer/5.")

    ap.add_argument("--channel-extend-m", type=float, default=0.0,
                help="Extend each channel cut beyond both ends by this many meters (helps remove slivers).")


    ap.add_argument("--out-crs", default="EPSG:4326")
    args = ap.parse_args()

    gdf = gpd.read_file(args.input_geojson)
    if gdf.empty:
        raise ValueError("Input has no features.")

    gdf = gdf[gdf.geometry.notna()].copy()
    gdf = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    if gdf.empty:
        raise ValueError("No LineString/MultiLineString features found.")

    metric_crs = choose_metric_crs(gdf)
    gdf_m = gdf.to_crs(metric_crs)

    # 1) Buffer lines -> union
    geom = unary_union(gdf_m.geometry.buffer(args.buffer_m)).buffer(0)

    # 2) Close small gaps
    if args.gap_close_m > 0:
        geom = morphological_close(geom, args.gap_close_m).buffer(0)

    # 3) Connect disjoint components with corridors (optional)
    connector_w = args.connector_width_m if args.connector_width_m is not None else args.buffer_m
    geom, _ = connect_components_with_corridors(
        geom, max_gap_m=args.connect_gaps_m, corridor_halfwidth_m=connector_w, max_iters=args.connect_iters
    )

    # Must be a single polygon at this stage (before hole removal), otherwise define more connection rules
    polys = to_polygons(geom)
    if len(polys) == 0:
        raise ValueError("Result geometry is empty.")
    if len(polys) > 1:
        raise ValueError(
            f"Still disjoint ({len(polys)} polygons). Increase --connect-gaps-m / --gap-close-m, "
            f"or accept MultiPolygon."
        )

    poly = polys[0]

    # 4) Optional simplify
    if args.simplify_m > 0:
        poly = poly.simplify(args.simplify_m, preserve_topology=True).buffer(0)
        # simplify can sometimes return MultiPolygon; take largest piece as a pragmatic safeguard
        ps = to_polygons(poly)
        poly = max(ps, key=lambda p: p.area)

    # 5) Cheat: fill small holes
    if args.fill_holes_max_area_m2 > 0:
        poly = fill_holes_by_area(poly, args.fill_holes_max_area_m2).buffer(0)

    # 6) Cheat: cut channels to remove remaining holes
    if args.cut_channels:
        ch_w = args.channel_width_m if args.channel_width_m is not None else (args.buffer_m / 5.0)
        #poly = cut_channels_to_exterior(poly, ch_w).buffer(0)
        poly = cut_channels_to_exterior(poly, ch_w, extend_m=args.channel_extend_m).buffer(0)


        # After channel cutting, ensure Polygon
        ps = to_polygons(poly)
        if len(ps) == 0:
            raise ValueError("Geometry became empty after cutting channels (unexpected).")
        # If it turned MultiPolygon, keep largest (rare, but possible if topology is odd)
        poly = max(ps, key=lambda p: p.area)

    # Final: ensure hole-less
    if len(poly.interiors) != 0:
        raise ValueError(
            f"Output still has {len(poly.interiors)} hole(s). "
            f"Increase --fill-holes-max-area-m2 and/or use --cut-channels."
        )

    out = gpd.GeoDataFrame({"name": ["AOI"]}, geometry=[poly], crs=metric_crs).to_crs(args.out_crs)
    out.to_file(args.output_geojson, driver="GeoJSON")
    print(f"AOI written to: {args.output_geojson} (hole-less Polygon)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


