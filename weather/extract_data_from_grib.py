import argparse
import xarray as xr
import numpy as np
import pandas as pd


def extract_data_from_grib (grib_file, variable_name, target_lat, target_lon, output_file) :

    ds = xr.open_dataset(grib_file, engine='cfgrib')

    # Adjust longitude if necessary
    if target_lon < 0:
        target_lon += 360

    # Select data at the specified point for all times
    data_at_point = ds[variable_name].sel(
        latitude=target_lat,
        longitude=target_lon,
        method='nearest'
    )

    # Extract time and temperature data
    times = data_at_point['time'].values
    temperatures = data_at_point.values

    # Convert times to pandas datetime
    times = pd.to_datetime(times)

    # Convert to Unix epoch time (seconds since 1970-01-01)
    epoch_times = times.astype(np.int64) // 1e9  # nanoseconds to seconds

    # Create a DataFrame
    df = pd.DataFrame({
        'time': epoch_times,
        'temperature': temperatures
    })

    # Optional: Convert temperature from Kelvin to Celsius
    #df['temperature'] = df['temperature'] - 273.15

    # Save to a CSV file
    df.to_csv(output_file, sep=' ', index=False)




if __name__ == "__main__":


    parser = argparse.ArgumentParser(
        description="Extract variable at lat,lng from ERA5 reanalysis data GRIB file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument("grib_file", help="GRIB file")
    parser.add_argument("--latitude", help="Latitude of location, eg 53.3", required=True)
    parser.add_argument("--longitude", help="Longitude of location, eg -8.5", required=True)
    parser.add_argument("--variable", help="One of t2m,tp,...", default="t2m")
    parser.add_argument("--output", help="Output file", required=True)
    args = parser.parse_args()

    extract_data_from_grib (args.grib_file, args.variable, float(args.latitude), float(args.longitude), args.output)
