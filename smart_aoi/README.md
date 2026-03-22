For some applications it is necessary to acquire aerial or EO products only along a corridor (eg road or hedgerow).
Some providers allow polygon AOIs but require that the polygon is simply-connected (ie no holes). 

This script takes a LineString network, applies a configurable buffer to the LineStrings and cuts channels when necessary to eliminate holes.

Usage examples:

```bash
python eo_utils/smart_aoi/linestring_to_aoi.py hedgerow.geojson --buffer-m 20 > aoi.geojson
python eo_utils/smart_aoi/linestring_to_aoi.py part1.geojson part2.geojson part3.geojson --buffer-m 20 --output aoi.geojson
```

Notes:

- one or more input GeoJSON files may be provided
- inputs are read, reprojected to a common CRS if needed, and concatenated internally
- if `--output` is omitted, GeoJSON is written to stdout

 
