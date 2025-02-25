#!/usr/bin/env python3
# 
# Script to download Sentinel-1 GRD products from Copernicus DataSpace service.
# This is cloned from a corresponding Sentinel-2 L2A download script.
#
#
# Joe Desbonnet 2025-02-04
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
    
    args (object) : arguments from argparse
    
    """


    #
    # Calculate geographic area part of query based on bounding_box and mgrs_tiles argument.
    #
    geographic_criteria = ""
    if args.bounding_box :
        geographic_criteria += f"and OData.CSC.Intersects(area=geography'SRID=4326;{args.bounding_box}') " 

    cog_criteria = ""
    if args.cog :
        cog_criteria += "and contains(Name,'_COG')"
     
    # OData API: https://documentation.dataspace.copernicus.eu/APIs/OData.html
    # Older OData documentation: https://scihub.copernicus.eu/userguide/ODataAPI
    # List of Sentinel-1 query attributes: https://catalogue.dataspace.copernicus.eu/odata/v1/Attributes(SENTINEL-1)    
    # TODO: can we work the MGRS tiles in this query?
    query_url = (f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products?" 
             f"$filter=Collection/Name eq 'SENTINEL-1' and contains(Name,'GRD') eq true" 
             f" {cog_criteria}"
             f" {geographic_criteria}"
             f" and ContentDate/Start gt {args.begin_date}T00:00:00.000Z" 
             f" and ContentDate/Start lt {args.end_date}T00:00:00.000Z"
             f"&$count=True&$top=1000" 
             )

    if args.debug == True :
        print (f"query_url={query_url}")

    json_ = requests.get(query_url).json()

    if args.debug == True :
        print (f"json={json_}")



    p = pd.DataFrame.from_dict(json_["value"])
    p["geometry"] = p["GeoFootprint"].apply(shape)
    productDF = gpd.GeoDataFrame(p).set_geometry("geometry") # Convert PD to GPD
    #productDF = productDF[~productDF["Name"].str.contains("L1C")] # Remove L1C dataset
    print(f" total GRD products found {len(productDF)}")
    productDF["identifier"] = productDF["Name"].str.split(".").str[0]
    allfeat = len(productDF)

    #return pd.DataFrame.from_dict(json_["value"])
    return productDF



def list_products (productDF, args) :

    for index,feat in enumerate(productDF.iterfeatures()):
        product_uuid = feat['properties']['Id']
        product_name = feat['properties']['Name']
        size_MiB = feat['properties']['ContentLength'] / (1024*1024)
        safe_file_path = get_safe_file_path(product_name,args)

        downloaded_checkmark = "x"
        if os.path.exists(safe_file_path) :
            downloaded_checkmark = "✔"

        print (f"{product_name} {size_MiB:5.0f} {downloaded_checkmark}")



def get_safe_file_path (product_name, args) :
    if product_name.endswith(".SAFE") :
        safe_file = f"{product_name}.zip"
    else :
        safe_file = f"{product_name}.SAFE.zip"
        
    return f"{args.grd_root}/{safe_file}"



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
def download_products (productDF,args) :

    allfeat = len(productDF)
    
    if allfeat == 0:
        print("No products found.")
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

            # If the product is already downloaded, skip (TODO: check for valid ZIP) 
            safe_path = f"{args.grd_root}/{safe_file}"
            safe_download_path = f"{args.grd_root}/_downloading_{safe_file}"
            if os.path.exists(safe_path) :
                print (f"Product {safe_path} already downloaded")
                continue
            
            
            print(f"Downloading product_name={product_name} product_id={product_uuid} into {safe_path}")
                
            download_one_product(feat['properties']['Id'],safe_download_path,safe_path,args)



if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Download Sentinel-1 GRD products.")

    parser.add_argument("--begin-date",help="The begin date (yyyy-MM-dd) for the search.", required=True)
    parser.add_argument("--end-date",  help="The end date (yyyy-MM-dd) for the search.")
    parser.add_argument("--bounding-box", help="Lat/lng based bounding box of the area of interest. Example: 'POLYGON((2.51 49.52, 6.15 49.52, 6.15 51.48, 2.51 51.48, 2.51 49.52))'")
    parser.add_argument("--grd-root",  help="The root of the S1 GRD directory into which to write files.", required=True)
    parser.add_argument("--username",  help="Dataspace username / email address.")
    parser.add_argument("--password",  help="Password associated with username.")
    parser.add_argument("--query-only", action="store_true", help="Only issue the product query and determine which products require downloading. No product downloads will take place.")
    parser.add_argument("--cog", action="store_true", help="Download COG version of product.")
    parser.add_argument("--debug", action="store_false", help="Output debugging information.")
    args = parser.parse_args()

    products = query_products (args) 
    
    if products.shape[0] == 0 :
        print ("No products found that match query.")
        exit(0)
    

    if args.query_only == True :
        list_products (products, args)
    else :
        download_products (products, args)


