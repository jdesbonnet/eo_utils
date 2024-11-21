import cdsapi

def download_era5_data(output_file, parameters, bbox, start_date, end_date):
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

    c.retrieve(
        'reanalysis-era5-single-levels',
        {
            'product_type': ['reanalysis'],
            'variable': parameters,
            #'year': ['2024'],
            #'month': ['03'],
            #'day': ['01'],
            #'time': ['13:00'],
            'pressure_level': ['1000'],
            'data_format': 'grib',

            #'format': 'netcdf',
            'format': 'grib',

            #'area': bbox,  # North, West, South, East
            'date': f"{start_date}/{end_date}",
            'time': [f"{hour:02d}:00" for hour in range(24)],  # All hours of the day
        },
        output_file
    )
    print(f"Data successfully downloaded to {output_file}")

# Example Usage
if __name__ == "__main__":
    output_file = "era5_data_2023-01.grib"

    parameters = ["2m_temperature", "total_precipitation"]
    #parameters = ["geopotential"]
    bbox = (55, -10, 51, -6)  # Bounding box: North, West, South, East
    start_date = "2023-01-01"
    end_date = "2023-01-31"

    download_era5_data(output_file, parameters, bbox, start_date, end_date)

