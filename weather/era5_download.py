import argparse
import cdsapi

def download_era5_data(output_file, parameters, bbox, date_range):
    """
    Download ERA-5 reanalysis data from Copernicus Climate Data Store.

    Requires ~/.cdsapirc file for API authentication. 

    Require cdsapi with version > 0.7.2 (Ubuntu 22.04 repo has version which 
    is too old, so don't use apt get. Instead pip3 install 'cdsapi>=0.7.2'.)
    Also this was required: pip3 install --upgrade attrs

    Args:
        output_file (str): Path to save the output NetCDF file.
        parameters (list): List of parameters (variable names) to download.
        bbox (list): Bounding box [North, West, South, East] (degrees).
        start_date (str): Start date in 'YYYY-MM-DD' format.
        end_date (str): End date in 'YYYY-MM-DD' format.
    """
    c = cdsapi.Client()


    dataset = 'reanalysis-era5-single-levels'
    #dataset = 'reanalysis-era5-single-levels-monthly-means'
    hours = [f"{hour:02d}:00" for hour in range(24)]
    print (f"hours={hours}")
    c.retrieve(
        dataset,
        {
            'product_type': ['reanalysis'],
            'variable': parameters,
            'data_format': 'grib',

            #'format': 'netcdf',
            'format': 'grib',

            'area': bbox,  # North, West, South, East
            #'date': f"{start_date}/{end_date}",
            #'date': f"{start_date}",
            'date': date_range,
            'time': [f"{hour:02d}:00" for hour in range(24)],  # All hours of the day
        },
        output_file
    )
    print(f"Data successfully downloaded to {output_file}")


if __name__ == "__main__":


    parser = argparse.ArgumentParser(
        description="Download ERA5 reanalysis data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument("--date", help="Date in yyyy-MM-dd format, example 2024-11-21", required=False)
    parser.add_argument("--start-date", help="Start date in yyyy-MM-dd format, example 2024-11-21", required=False)
    parser.add_argument("--end-date", help="End date in yyyy-MM-dd format, example 2024-11-21", required=False)
    parser.add_argument("--variable", help="One of 2m_temperature, total_precipitation...", default="2m_temperature", required=True)
    parser.add_argument("--output", help="Output file", required=True)
    args = parser.parse_args()

    #parameters = ["2m_temperature", "total_precipitation"]
    #parameters = ["2m_temperature"]
    variables = args.variable.split(",")

    # Ireland (island) bounding box: North, West, South, East
    bbox = (56, -11, 51, -5)

    if args.start_date and args.end_date :
        date_range = f"{args.start_date}/{args.end_date}"
    else :
        date_range = f"{args.start_date}"

    variables = args.variable.split(",")
    print (f"variables={variables}")

    download_era5_data(args.output, variables, bbox, date_range)

