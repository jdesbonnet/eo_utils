#!/usr/bin/env python3
"""
Cloud cover estimate using ONLY Sentinel-2 10m bands: B02, B03, B04, B08.
No SAFE / SCL / QA60 required.

Works with:
  A) A single 4-band GeoTIFF (bands in order B02,B03,B04,B08)  [recommended]
  B) Separate single-band files per scene (requires a naming convention; see notes)

Outputs a CSV with cloud area per file, excluding NoData pixels (handles non-rectangular AOI).

Limitations:
- Without SWIR, bright soil/sand/snow/foam can be confused with clouds.
- You may need to tune thresholds for your AOI/season.

Usage:
  python cloud_cover_10m_only.py /path/to/geotiffs output.csv

Optional:
  --pattern "*.tif"
  --assume-scale 0.0001          (common for S2 L2A reflectance in 0..10000)
  --b2 1 --b3 2 --b4 3 --b8 4    (1-based band indices in the stack)
  --t-bright 0.20                (visible brightness threshold)
  --t-ndvi 0.35                  (NDVI must be below this to be cloud)
  --t-white 0.70                 (whiteness threshold; lower means "whiter")
  --haze-blue 1.15               (blue ratio threshold to boost haze-like cloud)
  --min-cloud-frac 0.0           (drop tiny detections by requiring min fraction)
  --debug
"""

import argparse
import csv
import glob
import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import rasterio


@dataclass
class Thresholds:
    t_bright: float = 0.20
    t_ndvi: float = 0.35
    t_white: float = 0.70
    haze_blue: float = 1.15
    min_cloud_frac: float = 0.0


def pixel_area_m2(ds: rasterio.DatasetReader) -> float:
    t = ds.transform
    return abs(t.a * t.e)


def infer_scale_factor(arr: np.ndarray, assume_scale: Optional[float]) -> float:
    """
    If assume_scale is provided, use it.
    Otherwise infer:
      - If values look like 0..10000-ish -> 0.0001
      - If values look like 0..1-ish -> 1.0
    """
    if assume_scale is not None:
        return float(assume_scale)

    # robust sample
    sample = arr[:: max(1, arr.shape[0] // 200), :: max(1, arr.shape[1] // 200)]
    sample = sample[np.isfinite(sample)]
    if sample.size == 0:
        return 1.0

    p99 = float(np.percentile(sample, 99))
    if p99 > 2.0:   # likely scaled ints
        return 0.0001
    return 1.0


def read_band(ds: rasterio.DatasetReader, band_index_1based: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Returns (data_float32, valid_mask_bool) for one band.
    valid_mask excludes nodata and masked pixels.
    """
    arr = ds.read(band_index_1based, masked=True)
    if np.ma.isMaskedArray(arr):
        valid = ~arr.mask
        data = np.asarray(arr.filled(ds.nodata if ds.nodata is not None else 0), dtype=np.float32)
    else:
        data = arr.astype(np.float32, copy=False)
        if ds.nodata is None:
            valid = np.ones(data.shape, dtype=bool)
        else:
            valid = data != ds.nodata
    return data, valid


def compute_cloud_mask(
    b2: np.ndarray, b3: np.ndarray, b4: np.ndarray, b8: np.ndarray,
    valid: np.ndarray,
    th: Thresholds
) -> np.ndarray:
    """
    Heuristic cloud detector using only B2,B3,B4,B8 reflectance in [0..1].
    """

    eps = 1e-6

    # Visible brightness: clouds are bright in visible
    vis_mean = (b2 + b3 + b4) / 3.0

    # NDVI: clouds tend to have low NDVI; vegetation has high NDVI
    ndvi = (b8 - b4) / (b8 + b4 + eps)

    # Whiteness: clouds are relatively flat across visible bands (white-ish)
    # Lower whiteness => "more white"
    whiteness = (
        np.abs(b2 - vis_mean) / (vis_mean + eps) +
        np.abs(b3 - vis_mean) / (vis_mean + eps) +
        np.abs(b4 - vis_mean) / (vis_mean + eps)
    )

    # Haze / thin cloud cue: blue stronger relative to red/green
    blue_ratio = b2 / (0.5 * (b3 + b4) + eps)

    # Base cloud rule (conservative-ish)
    base_cloud = (vis_mean > th.t_bright) & (ndvi < th.t_ndvi) & (whiteness < th.t_white)

    # Optional boost for haze-like pixels: if blue_ratio is high and it's bright-ish and low NDVI
    haze_cloud = (blue_ratio > th.haze_blue) & (vis_mean > (0.8 * th.t_bright)) & (ndvi < th.t_ndvi)

    cloud = (base_cloud | haze_cloud) & valid
    return cloud


def process_file(
    path: str,
    b2i: int, b3i: int, b4i: int, b8i: int,
    assume_scale: Optional[float],
    th: Thresholds,
    debug: bool
) -> Optional[Dict]:
    try:
        with rasterio.open(path) as ds:
            if ds.count < max(b2i, b3i, b4i, b8i):
                if debug:
                    print(f"[SKIP] {os.path.basename(path)}: needs >= {max(b2i,b3i,b4i,b8i)} bands; has {ds.count}")
                return None

            # Read bands and intersect valid masks (AOI may be irregular / nodata outside)
            b2_raw, v2 = read_band(ds, b2i)
            b3_raw, v3 = read_band(ds, b3i)
            b4_raw, v4 = read_band(ds, b4i)
            b8_raw, v8 = read_band(ds, b8i)
            valid = v2 & v3 & v4 & v8

            # Infer scale on one band (they should share scaling)
            scale = infer_scale_factor(b2_raw, assume_scale)
            b2 = b2_raw * scale
            b3 = b3_raw * scale
            b4 = b4_raw * scale
            b8 = b8_raw * scale

            # Clip to sane reflectance range to reduce outlier impact
            b2 = np.clip(b2, 0.0, 1.5)
            b3 = np.clip(b3, 0.0, 1.5)
            b4 = np.clip(b4, 0.0, 1.5)
            b8 = np.clip(b8, 0.0, 1.5)

            cloud = compute_cloud_mask(b2, b3, b4, b8, valid, th)

            valid_px = int(np.count_nonzero(valid))
            cloud_px = int(np.count_nonzero(cloud))

            if valid_px == 0:
                cloud_frac = 0.0
            else:
                cloud_frac = cloud_px / valid_px

            # Optionally suppress tiny detections
            if th.min_cloud_frac > 0 and cloud_frac < th.min_cloud_frac:
                cloud_px = 0
                cloud_frac = 0.0

            area_px = pixel_area_m2(ds)
            valid_area_m2 = valid_px * area_px
            cloud_area_m2 = cloud_px * area_px
            cloud_percent = (cloud_area_m2 / valid_area_m2 * 100.0) if valid_area_m2 > 0 else 0.0

            if debug:
                print(
                    f"[OK] {os.path.basename(path)} "
                    f"scale={scale:g} valid_px={valid_px} cloud_px={cloud_px} cloud%={cloud_percent:.2f}"
                )

            return {
                "file": os.path.basename(path),
                "path": os.path.abspath(path),
                "scale_factor_used": scale,
                "pixel_area_m2": area_px,
                "valid_pixels": valid_px,
                "cloud_pixels": cloud_px,
                "total_valid_area_m2": valid_area_m2,
                "cloud_area_m2": cloud_area_m2,
                "cloud_area_ha": cloud_area_m2 / 1e4,
                "cloud_area_km2": cloud_area_m2 / 1e6,
                "cloud_percent": cloud_percent,
                "t_bright": th.t_bright,
                "t_ndvi": th.t_ndvi,
                "t_white": th.t_white,
                "haze_blue": th.haze_blue,
                "min_cloud_frac": th.min_cloud_frac,
            }

    except Exception as e:
        if debug:
            print(f"[ERR] {path}: {e}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_dir", help="Directory of GeoTIFFs (each should include the 4×10m bands).")
    ap.add_argument("output_csv", help="Output CSV path.")
    ap.add_argument("--pattern", default="*.tif", help="Glob pattern (default: *.tif)")

    # 1-based indices (rasterio uses 1..count)
    ap.add_argument("--b2", type=int, default=1, help="Band index for B02 (blue), 1-based (default 1)")
    ap.add_argument("--b3", type=int, default=2, help="Band index for B03 (green), 1-based (default 2)")
    ap.add_argument("--b4", type=int, default=3, help="Band index for B04 (red), 1-based (default 3)")
    ap.add_argument("--b8", type=int, default=4, help="Band index for B08 (NIR), 1-based (default 4)")

    ap.add_argument("--assume-scale", type=float, default=None,
                    help="Force a reflectance scale factor (e.g. 0.0001). If omitted, inferred.")

    ap.add_argument("--t-bright", type=float, default=0.20, help="Visible brightness threshold (default 0.20)")
    ap.add_argument("--t-ndvi", type=float, default=0.35, help="NDVI must be below this (default 0.35)")
    ap.add_argument("--t-white", type=float, default=0.70, help="Whiteness threshold (default 0.70)")
    ap.add_argument("--haze-blue", type=float, default=1.15, help="Blue ratio threshold (default 1.15)")
    ap.add_argument("--min-cloud-frac", type=float, default=0.0,
                    help="Suppress results if cloud fraction below this (default 0.0)")

    ap.add_argument("--debug", action="store_true")

    args = ap.parse_args()

    th = Thresholds(
        t_bright=args.t_bright,
        t_ndvi=args.t_ndvi,
        t_white=args.t_white,
        haze_blue=args.haze_blue,
        min_cloud_frac=args.min_cloud_frac,
    )

    files = sorted(glob.glob(os.path.join(args.input_dir, args.pattern)))
    if not files:
        raise SystemExit("No files matched your pattern.")

    rows = []
    for f in files:
        r = process_file(
            f,
            b2i=args.b2, b3i=args.b3, b4i=args.b4, b8i=args.b8,
            assume_scale=args.assume_scale,
            th=th,
            debug=args.debug,
        )
        if r is not None:
            rows.append(r)

    if not rows:
        raise SystemExit("No suitable 4-band (or multi-band) GeoTIFFs found with the requested band indices.")

    fieldnames = list(rows[0].keys())
    os.makedirs(os.path.dirname(os.path.abspath(args.output_csv)) or ".", exist_ok=True)
    with open(args.output_csv, "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    if args.debug:
        print(f"Wrote {len(rows)} rows -> {args.output_csv}")


if __name__ == "__main__":
    main()

