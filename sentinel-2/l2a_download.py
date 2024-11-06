#!/usr/bin/env python3
# 
# Script to download Sentinel-2 L2A products from Copernicus DataSpace service.
#
#
# Joe Desbonnet 2024-02-03
#
from datetime import date, timedelta
import requests
import pandas as pd
import geopandas as gpd
from shapely.geometry import shape
import os
import sys
import signal
import argparse


#
# Allow CTRL-C interrupt
#
def signal_handler(sig, frame):
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)


def get_keycloak(username: str, password: str) -> str:
    data = {
        "client_id": "cdse-public",
        "username": username,
        "password": password,
        "grant_type": "password",
    }
    try:
        r = requests.post(
            "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
            data=data,
        )
        r.raise_for_status()
    except Exception as e:
        raise Exception(
            f"Keycloak token creation failed. Reponse from the server was: {r.json()}"
        )
    return r.json()["access_token"]


def query_products (args) :
    """
    Query Copernicus Dataspace prdouct database. Return result structure which
    can be used with download_products().
    
    Parameters:
    
    begin_date_string (string) : The date on which to begin the search. yyyy-MM-dd format.
    
    end_date_string (string)   : The end date for the search. yyyy-MM-dd format.
    
    """
        
    # TODO: can we work the MGRS tiles in this query?
    query_url = (f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products?" 
             f"$filter=Collection/Name eq 'SENTINEL-2' " 
             f"and OData.CSC.Intersects(area=geography'SRID=4326;{args.bounding_box}') " 
             f"and ContentDate/Start gt {args.begin_date}T00:00:00.000Z " 
             f"and ContentDate/Start lt {args.end_date}T00:00:00.000Z "
             f"and Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and att/OData.CSC.DoubleAttribute/Value le {args.max_cloud})"
             f"&$count=True&$top=1000" )
             
    print (f"query_url={query_url}")
    json_ = requests.get(query_url).json()  
    print (f"json={json_}")
    return pd.DataFrame.from_dict(json_["value"])


def download_one_product (product_id, safe_download_path, safe_path, args) :

    """
    
    product_id (string) : Product ID. Example 'S2A_MSIL2A_20241105T105231_N0511_R051_T31UGS_20241105T150152'
    
    safe_download_path (string) : A temporary file path into which to start the download. When complete it will be moved to safe_path.
    
    safe_path (string) : The final destination of the fully downloaded product file.
    """
    
    try:
        session = requests.Session()
        keycloak_token = get_keycloak(args.username,args.password)
                
        session.headers.update({"Authorization": f"Bearer {keycloak_token}"})
        url = f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"
                
        print(f"getting {url}")
        response = session.get(url, allow_redirects=False)
                
        print(f"response={response}")
                
        # Unclear what this is about
        # 301: moved permanently
        while response.status_code in (301, 302, 303, 307):
            url = response.headers["Location"]
            # This takes a while
            response = session.get(url, allow_redirects=False)
            print (f" ** response={response}")
                    

            print(f"getting {url}")
            file = session.get(url, verify=False, allow_redirects=True)
            with open(safe_download_path, "wb") as p:
                print(f"{product_id} writing to {safe_download_path}")
                p.write(file.content)

                # Check if good SAFE.zip file, use file length for the moment.
                safe_file_size = os.path.getsize(safe_download_path)
                if safe_file_size > 100000 :
                    print(f"{product_id} renaming from {safe_download_path} to {safe_path}")
                    # Now that we've got a good product downloaded, rename to final filename
                    os.rename(safe_download_path, safe_path)
                    print(f"{product_id} has been downloaded")
                else :
                    print(f"{safe_download_path} too small to be a valid SAFE.zip size={safe_file_size}")
                    
    except Exception as e:
                print(f"problem with server: {e}")


#
def download_products (p,args) :

    p["geometry"] = p["GeoFootprint"].apply(shape)
    productDF = gpd.GeoDataFrame(p).set_geometry("geometry") # Convert PD to GPD
    productDF = productDF[~productDF["Name"].str.contains("L1C")] # Remove L1C dataset
    print(f" total L2A tiles found {len(productDF)}")
    productDF["identifier"] = productDF["Name"].str.split(".").str[0]
    allfeat = len(productDF)
        
    tiles_of_interest = args.mgrs_tiles.split(",")

    if allfeat == 0:
        print("No tiles found.")
    else:
        ## download all tiles from server
        for index,feat in enumerate(productDF.iterfeatures()):
        
        
            # Show all properties
            #for propertyName in feat['properties'] :
            #    print (f"property[{propertyName}]={feat['properties'][propertyName]}")

            #print(f"feat={feat}")
            
            #for f in feat:
            #    for propertyName in feat[f] :
            #        print (f"property[{f}][{propertyName}]={feat[f][propertyName]}")
        
            product_uuid = feat['properties']['Id']

            # Product name sometimes ends in .SAFE and sometimes not (!?)
            product_name = feat['properties']['Name']
            if product_name.endswith(".SAFE") :
                safe_file = f"{product_name}.zip"
            else :
                safe_file = f"{product_name}.SAFE.zip"

            print(f"SAFE_FILE={safe_file}")

            safe_parts = product_name.split('_')
            mgrs_tile = safe_parts[5]
            
            if not mgrs_tile in tiles_of_interest :
                print (f"only interested in {tiles_of_interest}, skipping {mgrs_tile}")
                continue
            	
            # If directory for the tile does not exist, create it 
            mgrs_tile_path = f"{args.l2a_root}/{mgrs_tile}"
            if not os.path.exists(mgrs_tile_path) :
                print(f"mkdir {mgrs_tile_path}")
                os.mkdir(mgrs_tile_path)

            # If the product is already downloaded, skip (TODO: check for valid ZIP) 
            safe_path = f"{args.l2a_root}/{mgrs_tile}/{safe_file}"
            safe_download_path = f"{args.l2a_root}/{mgrs_tile}/_downloading_{safe_file}"
            if os.path.exists(safe_path) :
                print (f"Product {safe_path} already downloaded")
                continue
            
            
            print(f"Downloading mgrs_tile={mgrs_tile} product_name={product_name} product_id={product_uuid} into {safe_path}")
                
            download_one_product(feat['properties']['Id'],safe_download_path,safe_path,args)



if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Download Sentinel-2 L2A products.")
    parser.add_argument("--begin-date",help="The begin date (yyyy-MM-dd) for the search.")
    parser.add_argument("--end-date",  help="The end date (yyyy-MM-dd) for the search.")
    parser.add_argument("--max-cloud", help="Limit to only products with this much cloud coverage or less.")
    parser.add_argument("--mgrs-tiles", help="MGRS tiles of interest separated by comma. Only download if in this set. Example 'T29UNU'.")
    parser.add_argument("--bounding-box", help="Lat/lng based bounding box of the area of interest. Example: 'POLYGON((2.51 49.52, 6.15 49.52, 6.15 51.48, 2.51 51.48, 2.51 49.52))'")
    parser.add_argument("--l2a-root",  help="The root of the L2A directory into which to write the L2A SAFE.zip files.")
    parser.add_argument("--username",  help="Dataspace username / email address.")
    parser.add_argument("--password",  help="Password associated with username.")
    args = parser.parse_args()

    products = query_products (args) 
    
    if products.shape[0] == 0 :
        print ("No products found that match query.")
        exit(0)
        
    download_products (products, args)



