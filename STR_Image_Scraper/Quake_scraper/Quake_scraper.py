
# coding: utf-8

# In[1]:


# You'll probably want to set our data rate higher for this notebook. 
# follow: http://stackoverflow.com/questions/43288550/iopub-data-rate-exceeded-when-viewing-image-in-jupyter-notebook


# # Setup 
# Let's setup our environment. We'll pull in the the usual gis suspects and setup a leaflet map, read our API keys from a json file, and setup our Planet client

# In[7]:


# See requirements.txt to set up your dev environment.
import time
import sys
import os
import os.path
import json
import scipy
import urllib
import datetime 
from datetime import timedelta
from datetime import datetime
import urllib3
import rasterio
import subprocess
import numpy as np
import pandas as pd
import seaborn as sns
from osgeo import gdal
from planet import api
from planet.api import filters
from traitlets import link
from pygeocoder import Geocoder
import reverse_geocoder as rg
import rasterio.tools.mask as rio_mask
from shapely.geometry import mapping, shape
from IPython.display import display, Image, HTML
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
urllib3.disable_warnings()
from ipyleaflet import (
    Map,
    Marker,
    TileLayer, ImageOverlay,
    Polyline, Polygon, Rectangle, Circle, CircleMarker,
    GeoJSON,
    DrawControl
)




# In[8]:


import logging
import logging.config

LOG_FILENAME = 'root'

logging.config.fileConfig('logger.conf')
logger = logging.getLogger(LOG_FILENAME)

fh = logging.FileHandler('quake_scraper_{:%Y-%m-%d}.log'.format(datetime.now()))
formatter = logging.Formatter('%(asctime)s | %(levelname)-8s | %(lineno)04d | %(message)s')
fh.setFormatter(formatter)

logger.addHandler(fh)
logger.debug("TEST")


# Here is a list of the different satellite resources from Planet:
# - PSScene3Band	- PlanetScope Scenes
# - PSScene4Band	- PlanetScope Scenes
# - PSOrthoTile   - PlanetScope OrthoTiles
# - REOrthoTile	- RapidEye OrthoTiles
# - REScene	    - RapidEye Scenes (unorthorectified strips)
# - SkySatScene	- SkySat Scenes
# - Landsat8L1G	- Landsat8 Scenes
# - Sentinel2L1C	- Copernicus Sentinel-2 Scenes

# In[38]:


#This little fancy piece of code will query the coordinates from entering the city and country
location = input("Use city, country or lat,long? Enter city or coords ")
while True:
    if(not location == "city" and not location == "coords"):
        print("Please enter a valid answer.")
        location = input("Use city, country or lat,long? Enter city or coords ")
        continue
    else:
        break

if (location == "city"):        
    cityName = input("Enter the City name: ")
    while True:
        if(not cityName.isalpha()):
            print("Please enter a valid city.")
            cityName = input("Enter the City name: ")
            continue
        else:
            break
    nationName = input("Enter the Country name: ")
    coords_raw = Geocoder.geocode(cityName,nationName)
    coords_str = str(coords_raw.coordinates)
    translation_table = dict.fromkeys(map(ord, '()'), None)
    coords = coords_str.translate(translation_table)
    lat = '%2f' % float(coords.split(',')[0])
    long = '%2f' % float(coords.split(',')[1])
else:
    lat = float(input("Enter the latitude: "))
    while True:
        if(not isinstance(lat, float)):
            print("Please enter a valid latitude.")
            lat = input("Enter the latitude: ")
            continue
        else:
            break
    long = float(input("Enter the longitude: "))
    while True:
        if(not isinstance(long, float)):
            print("Please enter a valid longitude.")
            lat = input("Enter the longitude: ")
            continue
        else:
            break
    coordinates = (lat, long)
    results = rg.search(coordinates) # default mode = 2
    cityName = (results[0]['name'])
    nationName = results[0]['cc']

year = int(input("Year (eg. 2015): "))
month = int(input("Month number(eg. 1 = january ): "))
day = int(input("Day (eg.6): "))
sats = ['PSScene3Band','PSScene4Band','PSOrthoTile','REOrthoTile','REScene','SkySatScene','Landsat8L1G','Sentinel2L1C']


# In[68]:


print ('PSScene3Band: 1\nPSScene4Band: 2\nPSOrthoTile: 3\nREOrthoTile: 4\nREScene: 5\nSkySatScene: 6\nLandsat8L1G: 7\nSentinel2L1C: 8\n')
sat_data_type = int(input("Which satellite data? Type in a number corresponding to it: "))
while True:
    if(not isinstance(sat_data_type, int) or sat_data_type < 1 or sat_data_type > 8):
        print("Please enter a valid answer.")
        sat_data_type = input("Which satellite data? Type in a number corresponding to it: ")
        continue
    else:
        break

sat_use = sats[sat_data_type-1]

print (lat, long)
print (sat_use)


# In[69]:


logger.info('Scraping starting for: '+cityName+', '+nationName)
logger.info('Coordinates: '+lat+', '+long)
logger.info('Date of Quake: '+str(year)+'-'+str(month)+'-'+str(day))
logger.info('Sat Source: '+sat_use)


# In[70]:


#This changes the directory to the current one running the notebook and then adds then goes into the folder tiffData. chdir changes the directory. getcwd finds the directory
main_folder = 'Quake_scraper'
current_path = os.getcwd()
orig_path = current_path
head, tail = os.path.split(current_path)
while(not tail == main_folder):
    head, tail = os.path.split(current_path)
    if (os.path.basename(head)== main_folder):
        orig_path = head
        os.chdir(orig_path)
        break
    elif (os.path.basename(head)=="Coding Experiments"):
        os.chdir(os.path.join(head, main_folder))
        orig_path = os.getcwd()
        break
    else:
        current_path = head
        orig_path = current_path
print (orig_path)


get_ipython().run_line_magic('matplotlib', 'inline')
# will pick up api_key via environment variable PL_API_KEY
# but can be specified using `api_key` named argument
api_keys = json.load(open("apikeys.json",'r'))
client = api.ClientV1(api_key=api_keys["PLANET_API_KEY"])

save_path = os.path.join(orig_path,'tiffFiles')
os.chdir(save_path)


# # Make a slippy map to get GeoJSON
# 
# * The planet API allows you to query using a [geojson](https://en.wikipedia.org/wiki/GeoJSON) which is a special flavor of json.
# * We are going to create a slippy map using leaflet and apply the Planet 2017 Q1 mosaic as the basemap. This requires our api key.
# * We are going to add a special draw handler that shoves a draw region into a object so we get the geojson.
# * If you don't want to do this, or need a fixed query try [geojson.io](http://geojson.io/#map=2/20.0/0.0)
# * To install and run:
# ```
# $ pip install ipyleaflet
# $ jupyter nbextension enable --py --sys-prefix ipyleaflet
# $ jupyter nbextension enable --py --sys-prefix widgetsnbextension
# ```
# * [More information](https://github.com/ellisonbg/ipyleaflet)
# 
# RISHI's NOTES: Once all the packages are installed, then the map will show up. Draw on the map itself your own polygons. Or as is said you can create your own fixed query. But when you create the polygon then the actioncount will go up.
# Learned from this website: https://stackoverflow.com/questions/39741287/google-maps-using-python

# In[72]:


# Basemap Mosaic (v1 API)
mosaicsSeries = 'global_quarterly_2016q1_mosaic'
# Planet tile server base URL (Planet Explorer Mosaics Tiles)
mosaicsTilesURL_base = 'https://tiles0.planet.com/experimental/mosaics/planet-tiles/' + mosaicsSeries + '/gmap/{z}/{x}/{y}.png'
# Planet tile server url
mosaicsTilesURL = mosaicsTilesURL_base + '?api_key=' + api_keys["PLANET_API_KEY"]
# Map Settings 
# Define colors
colors = {'blue': "#009da5"}
# Define initial map center lat/long
#NEXT STEP WOULD BE TO CAL A CITY AND RETRIEVE THE COORDINATES, Then use the name later on.
center = [lat,long]
# Define initial map zoom level
zoom = 13
# Set Map Tiles URL
planetMapTiles = TileLayer(url= mosaicsTilesURL)
# Create the map
m = Map(
    center=center, 
    zoom=zoom,
    default_tiles = planetMapTiles # Uncomment to use Planet.com basemap
)
# Define the draw tool type options
polygon = {'shapeOptions': {'color': colors['blue']}}
rectangle = {'shapeOptions': {'color': colors['blue']}} 

# Create the draw controls
# @see https://github.com/ellisonbg/ipyleaflet/blob/master/ipyleaflet/leaflet.py#L293
dc = DrawControl(
    polygon = polygon,
    rectangle = rectangle
)
# Initialize an action counter variable
actionCount = 0
AOIs = {}

# Register the draw controls handler
def handle_draw(self, action, geo_json):
    # Increment the action counter
    global actionCount
    actionCount += 1
    print (actionCount)
    # Remove the `style` property from the GeoJSON
    geo_json['properties'] = {}
    # Convert geo_json output to a string and prettify (indent & replace ' with ")
    geojsonStr = json.dumps(geo_json, indent=2).replace("'", '"')
    AOIs[actionCount] = json.loads(geojsonStr)

tiffFiles_path = os.path.join(orig_path, "tiffFiles")
os.chdir(tiffFiles_path)
jsonFile = cityName+".geojson"
geojson_exists = False;
if (os.path.exists(os.path.join(os.getcwd(),jsonFile))):
    actionCount += 1
    with open(os.path.join(os.getcwd(),jsonFile)) as f:
        AOIs[actionCount]= json.load(f)    
    print ("GEOJSON ALREADY CREATED - MOVE TO NEXT CELL\n")
    geojson_exists = True;
else:      
# Attach the draw handler to the draw controls `on_draw` event
    print ("Draw area of interest on map and a geojson will be generated\n")
    os.chdir(orig_path)
    dc.on_draw(handle_draw)
    m.add_control(dc)
    geojson_exists = False;
m 


# # Querying the Planet API.
# * First we'll grab our geojson area of interest (AOI) and use it to construct a query.
# * We'll then build a search to search that area looking for PSScene3Band
# * We have lots of products: RapidEye, PlanetScope (PS) 3 and 4 band, LandSat, and Sentinel are all possible.
# * Once we have our query, we'll do the search. We will then iterate over the results, slurp up the data, and put them in a pandas data frame for easy sorting.
# * We'll print the first few so we're sure it works. 

# In[73]:


import datetime
os.chdir(orig_path)
print (AOIs[1])
if (geojson_exists):
    myAOI = AOIs[1]
else:
    myAOI = AOIs[1]["geometry"]

# build a query using the AOI and
# a cloud_cover filter that excludes 'cloud free' scenes

quakeDay = datetime.datetime(year, month, day)
old = datetime.datetime(year, month, day) - timedelta(weeks=26)
now = datetime.datetime(year, month, day) + timedelta(weeks=26)
query = filters.and_filter(
    filters.geom_filter(myAOI),
    filters.range_filter('cloud_cover', lt=50),
    #filters.date_range('acquired', gt=old)
    filters.date_range('acquired', gt=old, lt=now)
)

# build a request for only PlanetScope imagery
request = filters.build_search_request(
    query, item_types=[sat_use]
)

# if you don't have an API key configured, this will raise an exception
result = client.quick_search(request)
scenes = []
planet_map = {}
for item in result.items_iter(limit=3000):
    planet_map[item['id']]=item
    props = item['properties']
    props["id"] = item['id']
    props["geometry"] = item["geometry"]
    props["thumbnail"] = item["_links"]["thumbnail"]
    scenes.append(props)
scenes = pd.DataFrame(data=scenes)
display(scenes)
print (len(scenes))


# # Cleanup
# * The data we got back is good, but we need some more information
# * We got back big scenes, but we only care about our area of interest. The scene may not cover the whole area of interest.
# * We can use the [Shapely](http://toblerity.org/shapely/manual.html) library to quickly figure out how much each scene overlaps our AOI
# * We will convert our AOI and the geometry of each scene to calculate overlap using a shapely call.
# * The returned acquisition, publish, and update times are strings, we'll convert them to datatime objects so we wan search.

# In[74]:


# now let's clean up the datetime stuff
# make a shapely shape from our aoi
city = shape(myAOI)
footprints = []
overlaps = []
# go through the geometry from our api call, convert to a shape and calculate overlap area.
# also save the shape for safe keeping
for footprint in scenes["geometry"].tolist():
    s = shape(footprint)
    footprints.append(s)
    overlap = 100.0*(city.intersection(s).area / city.area)
    overlaps.append(overlap)
# take our lists and add them back to our dataframe
scenes['overlap'] = pd.Series(overlaps, index=scenes.index)
scenes['footprint'] = pd.Series(footprints, index=scenes.index)
# now make sure pandas knows about our date/time columns.
scenes["acquired"] = pd.to_datetime(scenes["acquired"])
scenes["published"] = pd.to_datetime(scenes["published"])
scenes["updated"] = pd.to_datetime(scenes["updated"])
scenes.head()


# # Filtering our search using pandas.
# * Using our dataframe we will filter the scenes to just what we want.
# * First we want scenes with less than 10% clouds.
# * Second we want standard quality images. Test images may not be high quality.
# * Third well only look for scenes since January.
# * Finally we will create a new data frame with our queries and print the results. 
# 
# Rishi's notes: Had to change datetime.date to datetime.datetime, possibly due to the fact that the format is in a datetime and not just a date

# In[75]:


# Now let's get it down to just good, recent, clear scenes
clear = scenes['cloud_cover']<0.1
#good = scenes['quality_category']=="standard"
#recent = scenes["acquired"] > "%s-%s-%s" % (str(start_year),str(start_month),str(start_day))
no_quake = scenes["acquired"] < quakeDay
#partial_coverage = scenes["overlap"] > 30
before_scenes = scenes[(clear&no_quake)]
display(before_scenes)
print (len(before_scenes))

# Now let's get it down to just good, recent, clear scenes
#good = scenes['quality_category']=="standard"
quake = scenes["acquired"] > quakeDay
#recent = scenes["acquired"] > "%s-%s-%s" % (str(start_year),str(start_month),str(start_day))
#full_coverage = scenes["overlap"] >= 60
after_scenes = scenes[(clear&quake)]
display(after_scenes)
print (len(after_scenes))

all_scenes = scenes[(clear)]
display (all_scenes)


# # Visualizing scene foot prints overlap with our AOI
# * We know these scenes intersect with our AOI, but we aren't quite sure about the geometry.
# * We are going to plot our scene footprints and original AOI on our slippy map.
# * To do this we create GeoJson objects with properties. 

# In[76]:


# first create a list of colors
colors = ["#ff0000","#00ff00","#0000ff","#ffff00","#ff00ff","#00ffff"]
# grab our scenes from the geometry/footprint geojson
footprints = all_scenes["geometry"].tolist()
# for each footprint/color combo
for footprint,color in zip(footprints,colors):
    # create the leaflet object
    feat = {'geometry':footprint,"properties":{
            'style':{'color': color,'fillColor': color,'fillOpacity': 0.2,'weight': 1}},
            'type':u"Feature"}
    # convert to geojson
    gjson = GeoJSON(data=feat)
    # add it our map
    m.add_layer(gjson)
# now we will draw our original AOI on top 
feat = {'geometry':myAOI,"properties":{
            'style':{'color': "#FFFFFF",'fillColor': "#FFFFFF",'fillOpacity': 0.5,'weight': 1}},
            'type':u"Feature"}
gjson = GeoJSON(data=feat)
m.add_layer(gjson)   
m 


# # Let's see what we got. 
# * The API returns a handy thumbnail link.
# * Let's tell jupyter to show it.
# * You may need to login to planet explorer to have auth. 
#     * If this is the case just print the urls and paste them into your browser.

# In[77]:


imgs = []
# loop through our thumbnails and add display them
for img in all_scenes["thumbnail"].tolist():
    imgs.append(Image(url=img))
    print (img)
#display(*imgs)


# # Product Activation and Downloading
# * There are two things we need to know, the satellite type (asset) and image type (product).
# * Full resolution uncompressed satellite images are *big* and there are lots of ways to view them.
# * For this reason Planet generally keeps images in their native format and only processes them on customer requests. There is some caching of processed scenes, but this is the exception not the rule.
# * All images must be activated prior to downloading and this can take some time based on demand.
# * Additionally we need to determine what sort of product we want to download. Generally speaking there are three kinds of scenes:
#     * Analytic - multi-band full resolution images that have not been processed. These are like raw files for DSLR camers.
#     * Visual - these are color corrected rectified tifs. If you are just starting out this is your best call.
#     * UDM - Usable data mask. This mask can be used to find bad pixels and columns and to mask out areas with clouds.
#     

# In[78]:


#def get_products(client, scene_id, asset_type='PSScene3Band'): 
def get_products(client, scene_id, asset_type=sat_use): 
    """
    Ask the client to return the available products for a 
    given scene and asset type. Returns a list of product 
    strings
    """
    out = client.get_assets_by_id(asset_type,scene_id)
    temp = out.get()
    return temp.keys()

#def activate_product(client, scene_id, asset_type="PSScene3Band",product="analytic"):
def activate_product(client, scene_id, asset_type=sat_use,product="analytic"):
    """
    Activate a product given a scene, an asset type, and a product.
    
    On success return the return value of the API call and an activation object
    """
    temp = client.get_assets_by_id(asset_type,scene_id)  
    products = temp.get()
    if( product in products.keys() ):
        return client.activate(products[product]),products[product]
    else:
        return None 

def download_and_save(client,product):
    """
    Given a client and a product activation object download the asset. 
    This will save the tiff file in the local directory and return its 
    file name. 
    """
    out = client.download(product)
    fp = out.get_body()
    fp.write()
    return fp.name

def scenes_are_active(scene_list):
    """
    Check if all of the resources in a given list of
    scene activation objects is read for downloading.
    """
    retVal = True
    for scene in scene_list:
        if scene["status"] != "active":
            print ("{} is not ready.".format(scene))
            return False
    return True


# # Scenes ACTIVATE!
# * Given our good scenes list we will convert the data frame "id" column into a list and activate every item in that list. 
# * For this example we are going to default to using a 3Band visual product but I have included some four band methods to help you out.
# * Activation usually takes about 5-15 minutes so get some coffee.

# In[79]:


to_get = before_scenes["id"].tolist()
activated = []
# for each scene to get
sat_dict= {"PSScene3Band":"Visual","PSScene4Band":"analytic","PSOrthoTile":"Visual","REOrthoTile":"visual","REScene":"Visual","SkySatScene":"ortho_visual","Landsat8L1G":"Visual","Sentinel2L1C":"Visual"}
def reactivateScenes(temp_array):
    check_array = []
    to_get = before_scenes["id"].tolist()
    for i in to_get:
        for j in temp_array:
            if (j==i):
                check_array.append(i)
    activated = []
    for scene in check_array:
        product_types = get_products(client,scene)
        for p in product_types:
            if p == "visual"or  p == "ortho_visual":
                print ("Activating {0} for scene {1}".format(p,scene))
                _,product = activate_product(client,scene,product=p)
                activated.append(product)
    time.sleep(60)   
    print ("ReActivation Done! ..Downloading again")
    downloadingScenes(activated, check_array) 

def activateScenesTime():
    sceneCount = -1
    for scene in to_get:
        # get the product
        sceneCount += 1
        product_types = get_products(client,scene)
        for p in product_types:
            # if there is a visual product
            if p == "visual" or  p == "ortho_visual":
                print ("Activating {0} for scene {1}".format(p,scene))
                # activate the product
                _,product = activate_product(client,scene,product=p)
                activated.append(product)
    logger.info('Activation Done for Before images')            
    print ("Activation Done!")
logger.info("Scenes to activate : "+str(len(to_get)))                
print ("Scenes to activate : "+str(len(to_get)))    
activateScenesTime()    


# # Download Scenes
# * In this section we will see if our scenes have been activated.
# * If they are activated the client object will have its status flag set to active.
# * Once that is done we will then save the scenes to the local directory.
# * A smart engineer would set a path variable to store these files and check if the asset has already been downloaded prior to downloading

# In[80]:


tiff_files = []
#asset_type = "_3B_Visual"
os.chdir(os.path.join(os.path.join(orig_path,'tiffFiles'),'Before_quake'))
# check if our scenes have been activated
#if True: #scenes_are_active(activated):
def downloadingScenes(activated, to_get):
    temp_array = []
    for to_download,name in zip(activated,to_get):
        # create the product name
        if (not to_download["status"] == "active"):
            temp_array.append(name)
        else:
            name = name + "_"+ sat_dict[sat_use] + ".tif"
            check_name_path = os.path.join(os.getcwd(),name)
            # if the product exists locally
            if(os.path.isfile(check_name_path)):
                # do nothing 
                print ("We have scene {0} already, skipping...".format(name))
                tiff_files.append(name)
            elif (to_download["status"] == "active" and os.path.isfile(name) == False):
                # otherwise download the product
                print ("Downloading {0}....".format(name))
                fname = download_and_save(client,to_download)
                tiff_files.append(fname)
                print ("Download done.")
            else:
                print ("Could not download, still activating and still to: ")
                print (to_download["_permissions"])
    if (not len(temp_array) == 0):
        reactivateScenes(temp_array)

downloadingScenes(activated, to_get)
print (tiff_files)
        


# # Loading Images
# * There are a varitety of ways to load tif data including Rasterio, GDAL, OpenCV, SKImage. 
# * Today we are going to use rasterio and load each channel into a numpy array.
# * Since the visual 3Band products are rotated we can also open a mask layer for processing.

# In[81]:


def load_image4(filename):
    """Return a 4D (r, g, b, nir) numpy array with the data in the specified TIFF filename."""
    path = os.path.abspath(os.path.join('./', filename))
    if os.path.exists(path):
        with rasterio.open(path) as src:
            b, g, r, nir = src.read()
            return np.dstack([r, g, b, nir])
        
def load_image3(filename):
    """Return a 3D (r, g, b) numpy array with the data in the specified TIFF filename."""
    path = os.path.abspath(os.path.join('./', filename))
    if os.path.exists(path):
        with rasterio.open(path) as src:
            b,g,r,mask = src.read()
            return np.dstack([b, g, r])
        
def get_mask(filename):
    """Return a 1D mask numpy array with the data in the specified TIFF filename."""
    path = os.path.abspath(os.path.join('./', filename))
    if os.path.exists(path):
        with rasterio.open(path) as src:
            b,g,r,mask = src.read()
            return np.dstack([mask])

def rgbir_to_rgb(img_4band):
    """Convert an RGBIR image to RGB"""
    return img_4band[:,:,:3]


# # But all of these scenes are big, and we want downtown Portland 
# * We can clip all of the scenes to the AOI we selected at the start of the notebook
# * First we'll dump the geojson to a file.
# * Since geospatial data is "big" we often work with files and get stuff out of memory ASAP.
# * For each of our scenes we'll create a 'clip' file.
# * We will use a tool called GDAL to clip the scene to our AOI
# * GDAL stands for [Geospatial Data Abstraction Library](http://www.gdal.org/)
# * GDAL is a C++ library that is often run from the command line, but it does have SWIG bindings.

# In[82]:


aoi_file =cityName+".geojson" 
# write our input AOI to a geojson file.
with open(aoi_file,"w") as f:
    f.write(json.dumps(myAOI))
    

# create our full input and output names
clip_names = [os.path.abspath(tiff[:-4]+"_clip"+".tif") for tiff in tiff_files]
full_tif_files = [os.path.abspath("./"+tiff) for tiff in tiff_files]

for in_file,out_file in zip(tiff_files,clip_names):
    commands = ["gdalwarp", # t
           "-t_srs","EPSG:3857",
           "-cutline",aoi_file,
           "-crop_to_cutline",
           "-tap",
            "-tr", "3", "3"
           "-overwrite"]
    subprocess.call(["rm",out_file])
    commands.append(in_file)
    commands.append(out_file)
    print (" ".join(commands))
    subprocess.call(commands)


# In[83]:


subprocess.call(["rm","merged.tif"])
commands = ["gdalwarp", # t
           "-t_srs","EPSG:3857",
           "-cutline",aoi_file,
           "-crop_to_cutline",
           "-tap",
            "-tr", "3", "3"
           "-overwrite"]
output_mosaic = "merged.tif"
for tiff in tiff_files[0:2]:
    commands.append(tiff)
commands.append(output_mosaic)
print (" ".join(commands))
subprocess.call(commands)


# In[84]:


import subprocess
tiff_files = sorted(tiff_files)
# Create a list of tif file names. 
for tiff in tiff_files:
    if( os.path.isfile(os.path.abspath(tiff[:-4]+"_clip"+".tif") == True )):
            print ("We have scene {0} already, skipping...".format(name))
    else:
        clip_names.append(os.path.abspath(tiff[:-4]+"_clip"+".tif"))

full_tif_files = []
for tiff in tiff_files:
    full_tif_files.append(os.path.abspath("./"+tiff))

    # Run GDAL to crop our file down.
for in_file,out_file in zip(tiff_files,clip_names):
    commands = ["gdalwarp", # t
           "-t_srs","EPSG:3857",
           "-cutline",aoi_file,
           "-crop_to_cutline",
           "-tap",
            "-tr", "3", "3"
           "-overwrite"]
    subprocess.call(["rm",out_file])
    commands.append(in_file)
    commands.append(out_file)
    print (" ".join(commands))
    subprocess.call(commands)


# In[85]:


temp_names = []
i = 0 
# use image magic convert to
for in_file in clip_names:
    temp_name = cityName+"_"+nationName+"_"+sat_use+"_img{0}.gif".format(i) 
    command = ["convert", in_file, "-sample", "30x30%",temp_name]
    temp_names.append(temp_name)
    i += 1 
    subprocess.call(command)
    #if (os.path.isfile(in_file)):
     #   os.rename(in_file, os.path.join(os.getcwd(),temp_name))
   # print (in_file)
    #time.sleep(3)
    #print (temp_name)
    #time.sleep(3)
    #if (os.path.isfile(os.path.join(os.getcwd(),temp_name))):
for in_file in clip_names:
    if (os.path.isfile(in_file)):
        os.remove(in_file)
logger.info("All done with the Gifs for before quake!")        
print("All done with the Gifs for before quake!")
        


# In[86]:


for i in tiff_files:
    os.remove(i)


# # This completes the gif images for before the Earthquake
# 

# # ---------------------------------------------------

# # Now let's do it for after
# * First we'll download and activate all of our targe scenes.
# * Then we'll clip them using GDAL to the small AOI we selected above.
# * Finally we'll export them and use that data to make a mosaic. 
# * We'll use [ImageMagick](https://www.imagemagick.org/script/index.php) to convert our tifs to gifs, and our multiple gifs to an animated gif. 

# In[87]:


to_get = after_scenes["id"].tolist()
activated = []
# for each scene to get
sat_dict= {"PSScene3Band":"Visual","PSScene4Band":"analytic","PSOrthoTile":"Visual","REOrthoTile":"visual","REScene":"Visual","SkySatScene":"ortho_visual","Landsat8L1G":"Visual","Sentinel2L1C":"Visual"}
def reactivateScenes(temp_array):
    check_array = []
    to_get = after_scenes["id"].tolist()
    for i in to_get:
        for j in temp_array:
            if (j==i):
                check_array.append(i)
    activated = []
    for scene in check_array:
        product_types = get_products(client,scene)
        for p in product_types:
            if p == "visual"or  p == "ortho_visual":
                print ("Activating {0} for scene {1}".format(p,scene))
                _,product = activate_product(client,scene,product=p)
                activated.append(product)
    time.sleep(60)   
    print ("ReActivation Done! ..Downloading again")
    downloadAfterScenes(activated, check_array) 

def activateScenesTime():
    sceneCount = -1
    for scene in to_get:
        # get the product
        sceneCount += 1
        product_types = get_products(client,scene)
        for p in product_types:
            # if there is a visual product
            if p == "visual" or  p == "ortho_visual":
                print ("Activating {0} for scene {1}".format(p,scene))
                # activate the product
                _,product = activate_product(client,scene,product=p)
                activated.append(product)
    logger.info('Activation Done for After images')            
    print ("Activation Done!")
logger.info("Scenes to activate : "+str(len(to_get)))   
activateScenesTime()


# In[88]:


tiff_files = []
#asset_type = "_3B_Visual"
os.chdir(os.path.join(os.path.join(orig_path,'tiffFiles'),'After_quake'))
# check if our scenes have been activated
#if True: #scenes_are_active(activated):
def downloadAfterScenes(activated, to_get):
    temp_array = []
    for to_download,name in zip(activated,to_get):
        # create the product name
        if (not to_download["status"] == "active"):
            temp_array.append(name)
        else:
            name = name + "_"+ sat_dict[sat_use] + ".tif"
            check_name_path = os.path.join(os.getcwd(),name)
            # if the product exists locally
            if(os.path.isfile(check_name_path)):
                # do nothing 
                print ("We have scene {0} already, skipping...".format(name))
                tiff_files.append(name)
            elif (to_download["status"] == "active" and os.path.isfile(name) == False):
                # otherwise download the product
                print ("Downloading {0}....".format(name))
                fname = download_and_save(client,to_download)
                tiff_files.append(fname)
                print ("Download done.")
            else:
                print ("Could not download, still activating and still to: ")
                print (to_download["_permissions"])
    if (not len(temp_array) == 0):
        reactivateScenes(temp_array)

downloadAfterScenes(activated, to_get)
print (tiff_files)
logger.info("DOWNLOAD COMPLETE!")
print ("DOWNLOAD COMPLETE!")


# # Finally let's process the scenes we just downloaded and make a gif.

# In[89]:


print(os.getcwd())


# In[90]:


with open(aoi_file,"w") as f:
    f.write(json.dumps(myAOI))
clip_names = [os.path.abspath(tiff[:-4]+"_clip"+".tif") for tiff in tiff_files]
full_tif_files = [os.path.abspath("./"+tiff) for tiff in tiff_files]

for in_file,out_file in zip(tiff_files,clip_names):
    commands = ["gdalwarp", # t
           "-t_srs","EPSG:3857",
           "-cutline",aoi_file,
           "-crop_to_cutline",
           "-tap",
            "-tr", "3", "3"
           "-overwrite"]
    subprocess.call(["rm",out_file])
    commands.append(in_file)
    commands.append(out_file)
    print (" ".join(commands))
    subprocess.call(commands)


# In[91]:


subprocess.call(["rm","merged.tif"])
commands = ["gdalwarp", # t
           "-t_srs","EPSG:3857",
           "-cutline",aoi_file,
           "-crop_to_cutline",
           "-tap",
            "-tr", "3", "3"
           "-overwrite"]
output_mosaic = "merged.tif"
for tiff in tiff_files[0:2]:
    commands.append(tiff)
commands.append(output_mosaic)
print (" ".join(commands))
subprocess.call(commands)


# In[92]:


os.chdir(os.path.join(os.path.join(orig_path,'tiffFiles'),'After_quake'))
import subprocess
tiff_files = sorted(tiff_files)
# Create a list of tif file names. 
for tiff in tiff_files:
    if( os.path.isfile(os.path.abspath(tiff[:-4]+"_clip"+".tif") == True )):
            print ("We have scene {0} already, skipping...".format(name))
    else:
        clip_names.append(os.path.abspath(tiff[:-4]+"_clip"+".tif"))

full_tif_files = []
for tiff in tiff_files:
    full_tif_files.append(os.path.abspath("./"+tiff))

    # Run GDAL to crop our file down.
for in_file,out_file in zip(tiff_files,clip_names):
    commands = ["gdalwarp", # t
           "-t_srs","EPSG:3857",
           "-cutline",aoi_file,
           "-crop_to_cutline",
           "-tap",
            "-tr", "3", "3"
           "-overwrite"]
    subprocess.call(["rm",out_file])
    commands.append(in_file)
    commands.append(out_file)
    print (" ".join(commands))
    subprocess.call(commands)
    


# In[93]:



temp_names = []
i = 0 
# use image magic convert to
for in_file in clip_names:
    temp_name = cityName+"_"+nationName+"_"+sat_use+"_img{0}.gif".format(i) 
    command = ["convert", in_file, "-sample", "30x30%",temp_name]
    temp_names.append(temp_name)
    i += 1 
    subprocess.call(command)
for in_file in clip_names:
    if (os.path.isfile(in_file)):
        os.remove(in_file)
logger.info("All done with the Gifs for after quake!")        
print("All done with the Gifs for after quake!")
      


# In[94]:


for i in tiff_files:
    os.remove(i)


# <img src="./XXX.gif">

# In[ ]:


#os.chdir(os.path.join((save_path),"Fire gifs"))
#magic = cityName+"_"+nationName+"_"+sat_use+"_"+".gif"
#last_call = ["convert","-delay", "40","-loop","0", cityName+"_"+nationName+"_"+sat_use+"_img*.gif",magic]
#subprocess.call(last_call)
#print ("done!")


# In[ ]:


os.chdir(orig_path)

