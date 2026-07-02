# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

# LaskaKit map https://www.laskakit.cz/laskakit-interaktivni-mapa-cr-ws2812b/

import datetime
from datetime import timedelta
import time
import sys
import os
import mimetypes
import re
import subprocess
import shutil
import importlib.util
import math

from threading import Thread, Event, Lock
import traceback
import json
import tarfile

import web
from ospy.log import log
from ospy.options import options, rain_blocks
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string, stop_onrain, get_input, verify_csrf
from plugins import PluginOptions, plugin_url, plugin_data_dir

from ospy.webpages import showInFooter, pluginScripts # Enable plugin to display readings in UI footer

from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO



NAME = 'CHMI'
MENU =  _('Package: CHMI radar')
LINK = 'settings_page'
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

plugin_options = PluginOptions(
    NAME,
    {
        'enabled': False,
        'DATA_SOURCE': 'chmi',        # chmi = Czech CHMI PNG radar, shmu = Slovak SHMU HDF radar
        'use_footer': False,         # Information in footer
        'enable_log': False,         # Enable log
        'log_records': 0,            # Number of max logs (0=unlimited)
        'USE_RAIN_DELAY': False,     # If the box is checked, a rain delay will be set if rain is detected. The location coordinates are obtained from the OSPy settings from the weather/location menu. For proper function, you need to enter your location in the settings (for example, Prague).
        'RAIN_DELAY': 1,             # In hours
        'LON_0': 11.2673442,         # TOP LEFT CORNER
        'LAT_0': 52.1670717,
        'LON_1': 20.7703153,         # LOWER RIGHT CORNER
        'LAT_1': 48.1,
        'SEND_TO_HW': True,          # Send detected rainy cities to the external hardware map
        'ANIMATE': False,            # Animate the radar map from recent images kept in RAM
        'HOME_WIDGET': False,        # Show a small animated radar widget on the OSPy home page
        'IP_ADDR': '192.168.88.2',   # remote map IP address
        'HW_BOARD': '0',             # 0 = laskakit board, 1 = tmep board, 3 = pihrt board
        'R_DETECT': True,            # Use red channel for rain detection
        'G_DETECT': True,            # Use green channel for rain detection
        'B_DETECT': True,            # Use blue channel for rain detection
        'R_INTENS' : 0,              # R intensity threshold for activate rain delay
        'G_INTENS' : 0,              # G intensity threshold for activate rain delay
        'B_INTENS' : 0,              # B intensity threshold for activate rain delay
        'DETECTION_RADIUS': 6,       # Pixel radius around my location for rain detection
        'MIN_RAIN_PIXELS': 10,       # Minimum percent of rainy pixels in the detection area
    })

RADAR_URL = 'https://opendata.chmi.cz/meteorology/weather/radar/composite/maxz/png_masked/pacz2gmaps3.z_max3d.{}.0.png'
FORECAST_URL = 'https://opendata.chmi.cz/meteorology/weather/radar/composite/fct_pseudocappi2km/png/pacz2gmaps3.fct_z_cappi020.{}.ft60s10.tar'
SHMU_RADAR_URL = 'https://opendata.shmu.sk/meteorology/weather/radar/composite/skcomp/{product}/{day}/'
SHMU_DEFAULT_PRODUCT = 'zmax'
SHMU_BOUNDS = {
    'LON_0': 13.6,
    'LAT_0': 50.7,
    'LON_1': 23.804495372410756,
    'LAT_1': 46.04688049237037,
}
SHMU_BORDERS_PATH = os.path.join(PLUGIN_DIR, 'static', 'images', 'shmu_borders.png')
RADAR_HEADERS = {'User-Agent': 'OSPy CHMI radar monitor/1.0'}
animation_lock = Lock()
animation_frames = []
dependency_install_lock = Lock()
dependency_install_running = False

HOME_WIDGET_SCRIPT = 'chmi/script/home_widget.js'

def update_home_widget_script():
    if plugin_options['HOME_WIDGET']:
        if HOME_WIDGET_SCRIPT not in pluginScripts:
            pluginScripts.append(HOME_WIDGET_SCRIPT)
    else:
        while HOME_WIDGET_SCRIPT in pluginScripts:
            pluginScripts.remove(HOME_WIDGET_SCRIPT)

update_home_widget_script()

# We work in the WGS-84 coordinate system
# In order to be able to convert degrees of latitude and longitude into pixels,
# we need to know the coordinates of the upper left and lower right edges of the ÄŚHMĂš radar image

################################################################################
# Main function loop:                                                          #
################################################################################
class CHMI_Checker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()

        self.status = {}
        self.status['red'] = 0
        self.status['green'] = 0
        self.status['blue'] = 0
        self.status['state'] = 0

        self._sleep_time = 0
        self.start()

    def stop(self):
        self._stop_event.set()

    def update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def run(self):
        dis_text = True
        chmi_mon = None
        if plugin_options['enabled']:
            if plugin_options['use_footer']:
                chmi_mon = showInFooter()                               # instantiate class to enable data in footer
                chmi_mon.label = _('CHMI meteoradar')                   # label on footer
                chmi_mon.button = "chmi/settings"                       # button redirect on footer
                chmi_mon.val = '---'                                    # value on footer
        while not self._stop_event.is_set():
            self._sleep(1)
            try:
                if plugin_options['enabled']:
                    log.clear(NAME)
                    dis_text = True
                    # Bitmap dimensions in degrees
                    bounds = radar_bounds()
                    degree_width  = float(bounds['LON_1']) - float(bounds['LON_0'])
                    degree_heigth = float(bounds['LAT_0']) - float(bounds['LAT_1'])

                    # I will try to download the bitmap with the radar data
                    # If successful, ok = True, bytes = HTTP data of response (image), txt_date = YYYYMMDD.HHM0 of downloaded image
                    ok, byte, txt_date = download_radar()
                    if not ok:
                        log.info(NAME, datetime_string() + ' ' + _('Failed to download radar data.'))
                    else:
                        # We will create a bitmap object in PIL/Pillow format from the HTTP data
                        try:
                            bitmap = Image.open(BytesIO(byte))
                            
                            # Save radar img to local file
                            image_path = os.path.join(plugin_data_dir(), 'last.png')                              # last radar image
                            result_path = os.path.join(plugin_data_dir(),'result.png')                            # merge radar + borders image
                            corner_path = os.path.join(plugin_data_dir(),'corner.png')                            # draw corner to result
                            try:
                                bitmap.save(image_path)
                                img = compose_radar_image(Image.open(image_path))
                                img.save(result_path)
                                log.debug(NAME, datetime_string() + ' ' + _('The merging of the images (radar and outline of the Czech Republic) went OK.'))
                            except:
                                pass
                                log.error(NAME, datetime_string() + ' ' + _('Image cannot be saved.') + ':\n' + traceback.format_exc())

                            # The original image uses an indexed color palette. This can be useful, but for the simplicity of the example, we will convert the image to full RGB
                            log.debug(NAME, datetime_string() + ' ' + _('Converting the image to RGB...'))
                            bitmap = bitmap.convert("RGB")
                            # We calculate the step size of the vertical from the pixel dimension of the bitmap
                            # and horizontal pixel for further conversions between degrees and pixels
                            size_lat_pixel = degree_heigth / bitmap.height
                            size_lon_pixel = degree_width / bitmap.width

                            log.debug(NAME, _('Image width: {} px ({} degrees of longitude)').format(bitmap.width, degree_width))
                            log.debug(NAME, _('Image height: {} px ({} degrees of latitude)').format(bitmap.height, degree_heigth))
                            log.debug(NAME, _('1 vertical pixel is equal {} degrees of longitude').format(size_lat_pixel))
                            log.debug(NAME, _('1 horizontal pixel is equal {} degrees of latitude').format(size_lon_pixel))

                            # In the cities.csv file, we have all the municipalities on the map by line
                            # The line has the format: ID;name;country. width; ground length
                            # ID represents the order of RGB LEDs on the LaskaKit map of the Czech Republic

                            cities_with_rain = []
                            cities = []
                            if radar_source() == 'chmi':
                                log.debug(NAME, datetime_string() + ' ' + _('Loading cities database...'))
                                if plugin_options['HW_BOARD']   == "0":
                                    city_table = 'laska_cities'
                                elif plugin_options['HW_BOARD'] == "1":
                                    city_table = 'tmep_cities'
                                elif plugin_options['HW_BOARD'] == "2":
                                    city_table = 'pihrt_cities'
                                else:
                                    return
                                cities_path = os.path.join('plugins', 'chmi', 'static', city_table)
                                with open(cities_path, "r") as fi:
                                    cities = fi.readlines()
                            else:
                                log.info(NAME, datetime_string() + ' ' + _('City and hardware map processing is disabled for the SHMU radar source.'))

                            corner_img = Image.open(result_path)
                            c_img = img.convert("RGBA")
                            draw = ImageDraw.Draw(c_img) 
                            draw.rectangle((0,0,680,25), fill=(0, 0, 0), outline=(0, 0, 0))
                            drawtext = datetime_string()
                            font_path = os.path.join('plugins', 'chmi', 'static', 'font', 'Roboto-Bold.ttf')
                            font_size = 18
                            font = ImageFont.truetype(font_path, font_size)
                            draw.text((5, 5), drawtext, font=font, fill="white")

                            if cities:
                                log.debug(NAME, datetime_string() + ' ' + _('Analyzing if is raining in the cities...'))
                                log.debug(NAME, '-' * 40)
                                # We go through the list city by city
                                for city in cities:
                                    cell = city.split(";")
                                    if len(cell) == 4:
                                        idx = int(cell[0])
                                        name = cell[1]
                                        lat = float(cell[2])
                                        lon = float(cell[3])
                                        # We calculate the pixel coordinates of the city on the radar image
                                        x, y = radar_pixel_xy(lat, lon, bitmap.width, bitmap.height, bounds)
                                        if x < 0 or y < 0 or x >= bitmap.width or y >= bitmap.height:
                                            continue
                                        # We will find the RGB on the given coordinate, i.e. the possible color of the rain
                                        r,g,b = bitmap.getpixel((x, y))
                                        # If there is a non-zero color in a given location on the radar image, it is probably raining there
                                        # The intensity of the rain is determined by a specific color ranging from light blue to green, red to white
                                        # Right here we could also detect the strength of the rain, but for the simplicity of the example we will do with a simple color
                                        if r+g+b > 0:
                                            # If we activated drawing at the beginning of the program,
                                            # on the canvas we draw a square with dimensions of 10Ă—10 px representing the city
                                            # The square will have the color of rain and a red outline
                                            draw.rectangle((x-5, y-5, x+5, y+5), fill=(r, g, b), outline=(255, 0, 0))
                                            # If logging is active, we will display colored text indicating that it is raining in the given city,
                                            # and we add the city to the list as a structure {"id":id, "r":r, "g":g, "b":b} 
                                            log.info(NAME, datetime_string() + ' ' + _('In city {} ({}) it is probably raining right now').format(name, idx))
                                            log.debug(NAME, 'msg R={} G={} B={}'.format(r, g, b))
                                            cities_with_rain.append({"id": idx, "r": r, "g": g, "b": b})
                                        else:
                                            # If it is not raining in the given city, we draw an empty square with a white outline in its coordinates
                                            draw.rectangle((x-5, y-5, x+5, y+5), fill=(0, 0, 0), outline=(255, 255, 255))

                            # MY LOCATION
                            tempText = ""
                            is_lat_lon = None
                            r=g=b=rad=0
                            rain_area = None

                            if options.weather_lat and options.weather_lon:
                                lat = float(options.weather_lat)
                                lon = float(options.weather_lon)
                                is_lat_lon = True
                                # We calculate the pixel coordinates my location on the radar image
                                x, y = radar_pixel_xy(lat, lon, bitmap.width, bitmap.height, bounds)
                                rain_area = analyze_location_rain(bitmap, x, y)
                                r = rain_area['red']
                                g = rain_area['green']
                                b = rain_area['blue']
                                rad = 8
                            else:
                                lat = 0.0
                                lon = 0.0

                            if is_lat_lon is not None:
                                drawtext =  _('RGB in my location is R:{}, G:{}, B:{}').format(r,g,b)
                                draw.text((300, 5), drawtext, font=font, fill="white")
                                if rain_area['rain']:
                                    draw.ellipse((x-rad, y-rad, x+rad, y+rad), fill=(r, g, b), outline=(255, 0, 0), width=2)
                                    log.info(NAME, datetime_string() + ' ' + _('In my location latitude {} longitude {} it is probably raining right now.').format(options.weather_lat, options.weather_lon))
                                    log.info(NAME, datetime_string() + ' ' + _('Rain detection area: {} of {} pixels ({}%) are above the threshold.').format(rain_area['rainy_pixels'], rain_area['total_pixels'], rain_area['rainy_percent']))
                                    self.status['red'] = r
                                    self.status['green'] = g
                                    self.status['blue'] = b
                                    self.status['state'] = 1
                                    # LOG
                                    if plugin_options['enable_log']:
                                        update_log(self.status)
                                    # RAIND DELAY and FOOTER
                                    if plugin_options['USE_RAIN_DELAY']:
                                        delaytime = int(plugin_options['RAIN_DELAY'])
                                        rain_blocks[NAME] = datetime.datetime.now() + datetime.timedelta(hours=float(delaytime))
                                        stop_onrain()
                                        tempText += _('Detected Rain') + '. ' + _('Adding delay of') + ' ' + str(delaytime) + ' ' + _('hours')
                                    else:
                                        tempText += _('Probably raining right now')
                                else:
                                    draw.ellipse((x-rad, y-rad, x+rad, y+rad), fill=(0, 0, 0), outline=(255, 255, 255))
                                    log.info(NAME, datetime_string() + ' ' + _('In my location latitude {} longitude {} it is probably not rain.').format(options.weather_lat, options.weather_lon))
                                    log.info(NAME, datetime_string() + ' ' + _('Rain detection area: {} of {} pixels ({}%) are above the threshold.').format(rain_area['rainy_pixels'], rain_area['total_pixels'], rain_area['rainy_percent']))
                                    tempText += _('Probably not rain')
                                    self.status['state'] = 0
                            else:
                                tempText += _('Location is not set!')

                            if plugin_options['use_footer']:
                                if chmi_mon is not None:
                                    chmi_mon.val = tempText.encode('utf8').decode('utf8')    # value on footer

                            c_img.save(corner_path)
                            update_animation_cache()


                            # We ve gone through all the cities, so well see if we have any on the list that are raining
                            if len(cities_with_rain) > 0:
                                # we save the list of cities that had rain as JSON
                                # We then send the JSON form with the variable name "city" to the LaskaKit map of the Czech Republic via HTTP POST
                                if plugin_options['SEND_TO_HW']:
                                    if plugin_options['HW_BOARD']   == "0":
                                        map_name = _('Laskakit')
                                    if plugin_options['HW_BOARD']   == "1":
                                        map_name = _('TMEP')
                                    if plugin_options['HW_BOARD']   == "2":
                                        map_name = _('Pihrt')
                                    log.info(NAME, datetime_string() + ' ' + _('I am sending JSON with cities to the {} map of the Czech Republic...').format(map_name))
                                    form_data = {"mesta": json.dumps(cities_with_rain)}
                                    try:
                                        addr = 'http://{}/'.format(plugin_options['IP_ADDR'])
                                        log.debug(NAME, datetime_string() + ' ' + _('I will try to send to {} post data {}').format(addr, form_data))
                                        r = requests.post(addr, data=form_data, timeout=10)
                                        if r.status_code == 200:
                                            log.debug(NAME, datetime_string() + ' ' + _('HTTP {}').format(r.text))
                                        else:
                                            log.error(NAME, datetime_string() + ' ' + _('HTTP {}: I cannot connect to the board map of the Czech Republic at the URL http://{}/').format(r.status_code, plugin_options['IP_ADDR']))
                                    except:
                                        pass
                                        log.debug(NAME, traceback.format_exc())
                                        log.error(NAME, datetime_string() + ' ' + _('I cannot connect to the map board of the Czech Republic at the URL http://{}/').format(plugin_options['IP_ADDR']))
                                else:
                                    log.debug(NAME, datetime_string() + ' ' + _('Sending data to the hardware map is disabled.'))
                            elif radar_source() == 'chmi':
                                log.info(NAME, datetime_string() + ' ' + _('Looks like it is not raining in any city.'))
                            
                            log.info(NAME, datetime_string() + ' ' + _('Waiting 10 minutes for next update...'))
                            self._sleep(60 * 10)  # 60 seconds * 10 = 600 -> 10 minutes

                        except:
                            log.info(NAME, datetime_string() + ' ' + _('Failed to load rain radar bitmap.') + ':\n' + traceback.format_exc())
                            pass

                else:
                    if dis_text:
                        log.clear(NAME)
                        log.info(NAME, _('Plug-in is disabled.'))
                        dis_text = False

            except Exception:
                log.error(NAME, datetime_string() + ' ' + _('CHMI plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)


checker = None


################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global checker
    if checker is None:
        checker = CHMI_Checker()


def stop():
    global checker
    if checker is not None:
        checker.stop()
        checker.join(15)
        checker = None

def radar_date_txt(date):
    return date.strftime("%Y%m%d.%H%M")[:-1] + "0"

def forecast_date_txt(date):
    return date.strftime("%Y%m%d.%H%M")

def local_datetime_from_utc_text(date_txt):
    utc_date = datetime.datetime.strptime(date_txt, "%Y%m%d.%H%M")
    local_offset = datetime.datetime.now() - datetime.datetime.utcnow()
    return utc_date + local_offset

def radar_source():
    source = str(plugin_options.get('DATA_SOURCE', 'chmi')).lower()
    if source not in ('chmi', 'shmu'):
        source = 'chmi'
    return source

def radar_bounds():
    if radar_source() == 'shmu':
        return SHMU_BOUNDS
    return {
        'LON_0': float(plugin_options['LON_0']),
        'LAT_0': float(plugin_options['LAT_0']),
        'LON_1': float(plugin_options['LON_1']),
        'LAT_1': float(plugin_options['LAT_1']),
    }

def radar_pixel_xy(lat, lon, width, height, bounds=None):
    if bounds is None:
        bounds = radar_bounds()

    if radar_source() == 'shmu':
        def merc_y(value):
            rad = math.radians(value)
            return math.log(math.tan((math.pi / 4.0) + (rad / 2.0)))

        lon_0 = float(bounds['LON_0'])
        lon_1 = float(bounds['LON_1'])
        lat_0 = float(bounds['LAT_0'])
        lat_1 = float(bounds['LAT_1'])
        x = int(round(((lon - lon_0) / (lon_1 - lon_0)) * width))
        y = int(round(((merc_y(lat_0) - merc_y(lat)) / (merc_y(lat_0) - merc_y(lat_1))) * height))
        return x, y

    degree_width = float(bounds['LON_1']) - float(bounds['LON_0'])
    degree_height = float(bounds['LAT_0']) - float(bounds['LAT_1'])
    size_lat_pixel = degree_height / height
    size_lon_pixel = degree_width / width
    x = int((lon - bounds['LON_0']) / size_lon_pixel)
    y = int((bounds['LAT_0'] - lat) / size_lat_pixel)
    return x, y

def compose_radar_image(radar_img):
    if radar_source() == 'shmu':
        img = radar_img.convert("RGBA")
        base = Image.new("RGBA", img.size, (224, 229, 220, 255))
        base.alpha_composite(img)
        if os.path.isfile(SHMU_BORDERS_PATH):
            borders = Image.open(SHMU_BORDERS_PATH).convert("RGBA")
            if borders.size == img.size:
                base.alpha_composite(borders)
        return base

    borders_path = os.path.join('plugins','chmi','static','images','cr_borders.png')
    img = radar_img
    ia, wa = None, None
    if len(img.getbands()) == 4:
        ir, ig, ib, ia = img.split()
        img = Image.merge('RGB', (ir, ig, ib))
    wmark = Image.open(borders_path)
    if wmark.size == img.size:
        if len(wmark.getbands()) == 4:
            wa = wmark.split()[-1]
        img.paste(wmark, (0, 0), wmark)
        if ia:
            if wa:
                ia = max_alpha(wa, ia)
            img.putalpha(ia)
    return img

def shmu_missing_dependencies():
    missing = []
    for module_name in ('h5py', 'numpy'):
        if importlib.util.find_spec(module_name) is None:
            missing.append(module_name)
    return missing

def shmu_dependencies_installing():
    with dependency_install_lock:
        return dependency_install_running

def start_shmu_dependency_install():
    global dependency_install_running
    with dependency_install_lock:
        if dependency_install_running:
            log.info(NAME, datetime_string() + ' ' + _('SHMU dependency installation is already running.'))
            return
        dependency_install_running = True

    install_thread = Thread(target=install_shmu_dependencies)
    install_thread.daemon = True
    install_thread.start()

def install_shmu_dependencies():
    global dependency_install_running
    try:
        missing = shmu_missing_dependencies()
        if not missing:
            log.info(NAME, datetime_string() + ' ' + _('SHMU radar dependencies are already installed.'))
            return

        log.info(NAME, datetime_string() + ' ' + _('Installing SHMU radar dependencies. This operation can take several minutes.'))
        if os.name == 'posix' and shutil.which('apt-get'):
            cmd = ['sudo', 'apt-get', 'install', '-y', 'python3-h5py', 'python3-numpy', 'python3-pillow']
            log.info(NAME, datetime_string() + ' ' + _('Running command') + ': ' + ' '.join(cmd))
        else:
            cmd = [sys.executable, '-m', 'pip', 'install', 'h5py', 'numpy', 'Pillow']
            log.info(NAME, datetime_string() + ' ' + _('Running command') + ': ' + ' '.join(cmd))

        proc = subprocess.run(cmd, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, timeout=900)
        output = proc.stdout.decode('utf-8', 'replace').strip()
        if output:
            log.info(NAME, output[-4000:])

        missing = shmu_missing_dependencies()
        if proc.returncode == 0 and not missing:
            log.info(NAME, datetime_string() + ' ' + _('SHMU radar dependencies were installed successfully.'))
            log.info(NAME, datetime_string() + ' ' + _('Set your location coordinates in the OSPy options so rain detection works correctly.'))
        else:
            log.error(NAME, datetime_string() + ' ' + _('SHMU radar dependency installation failed. Missing modules') + ': ' + ', '.join(missing))
    except:
        log.error(NAME, _('CHMI plug-in') + ':\n' + traceback.format_exc())
    finally:
        with dependency_install_lock:
            dependency_install_running = False

def animation_label(date_txt, frame_type, relative_minutes):
    local_date = local_datetime_from_utc_text(date_txt)
    label = local_date.strftime("%d.%m. %H:%M")
    if frame_type == 'forecast':
        return '{} ({})'.format(label, _('forecast +{} min').format(relative_minutes))
    if relative_minutes < 0:
        return '{} ({} min)'.format(label, relative_minutes)
    return '{} ({})'.format(label, _('now'))

def download_radar_frame(date):
    if radar_source() == 'shmu':
        return download_shmu_radar(date=date, trials=1)

    date_txt = radar_date_txt(date)
    url = RADAR_URL.format(date_txt)
    r = requests.get(url, timeout=15, headers=RADAR_HEADERS)
    if r and r.status_code == 200 and r.content.startswith(b'\x89PNG\r\n\x1a\n'):
        return True, r.content, date_txt
    return False, None, date_txt

def shmu_date_txt(date):
    return date.strftime("%Y%m%d.%H%M")

def shmu_hdf_to_png(byte):
    try:
        import h5py
        import numpy
    except ImportError:
        log.error(NAME, _('SHMU radar source requires python3-h5py and python3-numpy. Install them and restart OSPy.'))
        return False, None

    with h5py.File(BytesIO(byte), 'r') as hdf:
        data = hdf['dataset1/data1/data'][:]
        gain = float(hdf['dataset1/what'].attrs.get('gain', 0.5))
        offset = float(hdf['dataset1/what'].attrs.get('offset', -32.5))

    dbz = data.astype('float32') * gain + offset
    valid = (data > 0) & (data < 255) & (dbz >= 5)
    image = numpy.zeros((data.shape[0], data.shape[1], 4), dtype=numpy.uint8)

    color_steps = [
        (5,  (70,  120, 255, 180)),
        (15, (0,   190, 255, 205)),
        (25, (0,   180, 60,  220)),
        (35, (255, 220, 0,   230)),
        (45, (255, 130, 0,   235)),
        (55, (230, 0,   0,   240)),
        (65, (180, 0,   180, 245)),
        (99, (255, 255, 255, 250)),
    ]
    for limit, color in color_steps:
        mask = valid & (dbz <= limit)
        image[mask] = color
        valid = valid & (dbz > limit)

    radar_img = Image.fromarray(image, 'RGBA')
    output = BytesIO()
    radar_img.save(output, format='PNG')
    return True, output.getvalue()

def shmu_latest_hdf_url(date, product=SHMU_DEFAULT_PRODUCT):
    day = date.strftime('%Y%m%d')
    index_url = SHMU_RADAR_URL.format(product=product, day=day)
    log.debug(NAME, datetime_string() + ' ' + _('Downloading a file: {}').format(index_url))
    requests.packages.urllib3.disable_warnings()
    r = requests.get(index_url, timeout=15, headers=RADAR_HEADERS, verify=False)
    if not r or r.status_code != 200:
        return None, None

    files = re.findall(r'href="([^"]+\.hdf)"', r.text)
    if not files:
        return None, None

    if date is not None:
        wanted = date.strftime('%Y%m%d%H%M')
        usable = [name for name in files if wanted in name]
        if usable:
            filename = usable[-1]
        else:
            older = [name for name in files if re.search(r'_(\d{12})00\.hdf$', name) and re.search(r'_(\d{12})00\.hdf$', name).group(1) <= wanted]
            filename = older[-1] if older else files[-1]
    else:
        filename = files[-1]

    match = re.search(r'_(\d{8})(\d{4})00\.hdf$', filename)
    date_txt = '{}.{}'.format(match.group(1), match.group(2)) if match else shmu_date_txt(date)
    return index_url + filename, date_txt

def download_shmu_radar(date=None, trials=3):
    if date is None:
        date = datetime.datetime.utcnow() - timedelta(minutes=10)

    while trials > 0:
        try:
            url, date_txt = shmu_latest_hdf_url(date)
            if not url:
                date -= timedelta(minutes=10)
                trials -= 1
                continue

            log.debug(NAME, datetime_string() + ' ' + _('Downloading a file: {}').format(url))
            requests.packages.urllib3.disable_warnings()
            r = requests.get(url, timeout=20, headers=RADAR_HEADERS, verify=False)
            if r and r.status_code == 200 and r.content.startswith(b'\x89HDF\r\n\x1a\n'):
                ok, content = shmu_hdf_to_png(r.content)
                return ok, content, date_txt

            log.debug(NAME, _('HTTP {}: I can not download the file.').format(r.status_code if r else '---'))
        except requests.RequestException:
            log.debug(NAME, traceback.format_exc())
        except:
            log.debug(NAME, traceback.format_exc())
            return False, None, shmu_date_txt(date)

        date -= timedelta(minutes=10)
        trials -= 1
        time.sleep(1)

    return False, None, shmu_date_txt(date)

def pixel_matches_rain_threshold(r, g, b):
    checks = []
    if plugin_options.get('R_DETECT', True):
        checks.append(r > int(plugin_options['R_INTENS']))
    if plugin_options.get('G_DETECT', True):
        checks.append(g > int(plugin_options['G_INTENS']))
    if plugin_options.get('B_DETECT', True):
        checks.append(b > int(plugin_options['B_INTENS']))
    return any(checks)

def analyze_location_rain(bitmap, x, y):
    radius = max(0, int(plugin_options['DETECTION_RADIUS']))
    min_percent = max(0, min(100, int(plugin_options['MIN_RAIN_PIXELS'])))
    rainy_pixels = 0
    total_pixels = 0
    red_sum = 0
    green_sum = 0
    blue_sum = 0

    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            if dx * dx + dy * dy > radius * radius:
                continue
            px = x + dx
            py = y + dy
            if px < 0 or py < 0 or px >= bitmap.width or py >= bitmap.height:
                continue

            r, g, b = bitmap.getpixel((px, py))
            total_pixels += 1
            if pixel_matches_rain_threshold(r, g, b):
                rainy_pixels += 1
                red_sum += r
                green_sum += g
                blue_sum += b

    rainy_percent = int(round((rainy_pixels * 100.0) / total_pixels)) if total_pixels else 0
    if rainy_pixels:
        red = int(round(red_sum / rainy_pixels))
        green = int(round(green_sum / rainy_pixels))
        blue = int(round(blue_sum / rainy_pixels))
    else:
        red = green = blue = 0

    return {
        'rain': rainy_percent >= min_percent,
        'red': red,
        'green': green,
        'blue': blue,
        'rainy_pixels': rainy_pixels,
        'total_pixels': total_pixels,
        'rainy_percent': rainy_percent,
        'radius': radius,
        'min_percent': min_percent,
    }

def create_animation_image(byte, date_txt, frame_type, relative_minutes):
    radar_img = Image.open(BytesIO(byte))
    detection_img = radar_img.convert("RGB")
    frame_img = compose_radar_image(radar_img).convert("RGBA")
    draw = ImageDraw.Draw(frame_img)
    draw.rectangle((0, 0, 680, 25), fill=(0, 0, 0), outline=(0, 0, 0))
    font_path = os.path.join('plugins', 'chmi', 'static', 'font', 'Roboto-Bold.ttf')
    font = ImageFont.truetype(font_path, 18)
    draw.text((5, 5), animation_label(date_txt, frame_type, relative_minutes), font=font, fill="white")
    rgb_info = None

    if options.weather_lat and options.weather_lon:
        try:
            lat = float(options.weather_lat)
            lon = float(options.weather_lon)
            x, y = radar_pixel_xy(lat, lon, detection_img.width, detection_img.height)
            if 0 <= x < frame_img.width and 0 <= y < frame_img.height:
                rgb_info = analyze_location_rain(detection_img, x, y)
                radius = 8
                draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=(255, 255, 0), outline=(0, 0, 0), width=2)
                draw.ellipse((x-3, y-3, x+3, y+3), fill=(0, 0, 0), outline=(255, 255, 255))
        except:
            log.debug(NAME, traceback.format_exc())

    output = BytesIO()
    frame_img.save(output, format='PNG')
    return output.getvalue(), rgb_info

def download_forecast_frames(base_date):
    frames = []
    forecast_date = datetime.datetime.utcnow()
    forecast_date -= timedelta(minutes=forecast_date.minute % 5,
                               seconds=forecast_date.second,
                               microseconds=forecast_date.microsecond)
    for attempt in range(0, 35, 5):
        date_txt = forecast_date_txt(forecast_date - timedelta(minutes=attempt))
        url = FORECAST_URL.format(date_txt)
        try:
            r = requests.get(url, timeout=15, headers=RADAR_HEADERS)
            if not r or r.status_code != 200:
                continue
            forecast_tar = tarfile.open(fileobj=BytesIO(r.content), mode='r:*')
            members = [member for member in forecast_tar.getmembers() if member.isfile() and member.name.endswith('.png')]
            members.sort(key=lambda member: member.name)
            for member in members:
                try:
                    parts = os.path.basename(member.name).split('.')
                    member_date_txt = '{}.{}'.format(parts[2], parts[3])
                    relative_minutes = int(parts[4])
                    extracted = forecast_tar.extractfile(member)
                    if extracted is None:
                        continue
                    byte = extracted.read()
                    if byte.startswith(b'\x89PNG\r\n\x1a\n'):
                        content, rgb_info = create_animation_image(byte, member_date_txt, 'forecast', relative_minutes)
                        frames.append({
                            'date': member_date_txt,
                            'label': animation_label(member_date_txt, 'forecast', relative_minutes),
                            'type': 'forecast',
                            'relative': relative_minutes,
                            'content': content,
                            'rgb': rgb_info,
                        })
                except:
                    log.debug(NAME, traceback.format_exc())
            if frames:
                break
        except:
            log.debug(NAME, traceback.format_exc())

    return frames

def update_animation_cache():
    global animation_frames
    if not plugin_options['ANIMATE'] and not plugin_options['HOME_WIDGET']:
        with animation_lock:
            animation_frames = []
        return

    base_date = datetime.datetime.utcnow() - timedelta(minutes=20)
    base_date -= timedelta(minutes=base_date.minute % 10,
                           seconds=base_date.second,
                           microseconds=base_date.microsecond)

    frames = []
    for offset in range(60, -1, -10):
        frame_date = base_date - timedelta(minutes=offset)
        ok, byte, date_txt = download_radar_frame(frame_date)
        if ok:
            try:
                content, rgb_info = create_animation_image(byte, date_txt, 'history', -offset)
                frames.append({
                    'date': date_txt,
                    'label': animation_label(date_txt, 'history', -offset),
                    'type': 'history',
                    'relative': -offset,
                    'content': content,
                    'rgb': rgb_info,
                })
            except:
                log.debug(NAME, traceback.format_exc())
        time.sleep(0.2)

    if radar_source() == 'chmi':
        frames += download_forecast_frames(base_date)
    frames.sort(key=lambda frame: frame['relative'])

    with animation_lock:
        animation_frames = frames

    log.debug(NAME, datetime_string() + ' ' + _('Radar animation cache contains {} frame(s).').format(len(frames)))

# Function to download bitmap with radar data from URL:
# https://opendata.chmi.cz/meteorology/weather/radar/composite/maxz/png_masked/pacz2gmaps3.z_max3d.{date_txt}.0.png
# date_txt must be in UTC YYYYMMDD.HHM0 format (CHMI publishes images every full 10 minutes)
# If the URL is not valid (the image does not exist yet),
# I'll try to download a bitmap with a ten minute old timestamp
# The number of repetitions is determined by the variable trials
def download_radar(date=None, trials=3):
    if radar_source() == 'shmu':
        return download_shmu_radar(date, trials)

    if date == None:
        date = datetime.datetime.utcnow() - timedelta(minutes=20)

    date_txt = date
    while trials > 0:
        date_txt = radar_date_txt(date)
        try:
            url = RADAR_URL.format(date_txt)
            log.debug(NAME,datetime_string() + ' ' + _('Downloading a file: {}').format(url))
            r = requests.get(url, timeout=15, headers=RADAR_HEADERS)
            if r and r.status_code == 200 and r.content.startswith(b'\x89PNG\r\n\x1a\n'):
                return True, r.content, date_txt
            else:
                if r and r.status_code == 200:
                    log.error(NAME, _('HTTP {}: downloaded file is not a valid PNG image.').format(r.status_code))
                else:
                    log.debug(NAME, _('HTTP {}: I can not download the file.').format(r.status_code if r else '---'))
                log.debug(NAME, _('I will try to download a file that is 10 minutes older.'))
                date -= timedelta(minutes=10)
                trials -= 1
                time.sleep(1)
        except requests.RequestException:
            log.debug(NAME, traceback.format_exc())
            log.debug(NAME, _('I will try to download a file that is 10 minutes older.'))
            date -= timedelta(minutes=10)
            trials -= 1
            time.sleep(1)
        except:
            log.debug(NAME, traceback.format_exc())
            return False, None, date_txt

    return False, None, date_txt


def rgb_msg(r,g,b, msg):
    return '\x1b[38;2;{};{};{}m{}\x1b[0m'.format(r, g, b, msg)


def max_alpha(a, b):
    """Assumption: 'a' and 'b' are of same size"""
    im_a = a.load()
    im_b = b.load()
    width, height = a.size

    alpha = Image.new('L', (width, height))
    im = alpha.load()
    for x in xrange(width):
        for y in xrange(height):
            im[x, y] = max(im_a[x, y], im_b[x, y])
    return alpha


def read_log():
    """Read log data from json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'log.json')) as logf:
            return json.load(logf)
    except IOError:
        return []


def write_log(json_data):
    """Write data to log json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'log.json'), 'w') as outfile:
            json.dump(json_data, outfile)
    except:
        log.error(NAME, datetime_string() + ' ' + _('CHMI plug-in') + ':\n' + traceback.format_exc())
        pass

def update_log(status):
    """Update data in json files.""" 
    try:
        log_data = read_log()
    except:
        write_log([])
        log_data = read_log()

    from datetime import datetime 

    data = {'datetime': datetime_string()}
    data['date'] = str(datetime.now().strftime('%d.%m.%Y'))
    data['time'] = str(datetime.now().strftime('%H:%M:%S'))
    data['red'] = str(status['red'])
    data['green'] = str(status['green'])
    data['blue'] = str(status['blue'])

    log_data.insert(0, data)
    if plugin_options['log_records'] > 0:
        log_data = log_data[:plugin_options['log_records']]
    write_log(log_data)

################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering adjustments"""

    def GET(self):
        try:
            global checker
            qdict  = web.input()

            del_rain = get_input(qdict, 'del_rain', False, lambda x: True)
            refresh = get_input(qdict, 'refresh', False, lambda x: True)
            delete = get_input(qdict, 'delete', False, lambda x: True)
            install_deps = get_input(qdict, 'install_deps', False, lambda x: True)
            show = get_input(qdict, 'show', False, lambda x: True)

            if checker is not None and del_rain:
                verify_csrf(qdict)
                if NAME in rain_blocks:
                    del rain_blocks[NAME]
                    log.info(NAME, datetime_string() + ': ' + _('Removing Rain Delay') + '.')

            if checker is not None and refresh:
                verify_csrf(qdict)
                checker.update()

            if install_deps:
                verify_csrf(qdict)
                start_shmu_dependency_install()
                raise web.seeother(plugin_url(settings_page), True)

            if checker is not None and delete:
                verify_csrf(qdict)
                write_log([])
                log.info(NAME, datetime_string() + ': ' + _('Deleted all log files OK'))

            if checker is not None and show:
                raise web.seeother(plugin_url(log_page), True)

            missing_dependencies = shmu_missing_dependencies()
            return self.plugin_render.chmi(
                plugin_options,
                log.events(NAME),
                missing_dependencies,
                shmu_dependencies_installing(),
                ', '.join(missing_dependencies),
            )

        except:
            log.error(NAME, _('CHMI plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('chmi -> settings_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            qdict = web.input()
            verify_csrf(qdict)
            plugin_options.web_update(qdict)
            update_home_widget_script()
            if checker is not None:
                checker.update()
            raise web.seeother(plugin_url(settings_page), True)
        except:
            log.error(NAME, _('CHMI plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('chmi -> settings_page POST')
            return self.core_render.notice('/', msg)

class download_page(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        try:
            download_name = plugin_data_dir() + '/' + 'corner.png'
            if os.path.isfile(download_name):     # exists image? 
                content = mimetypes.guess_type(download_name)[0]
                web.header('Content-type', content)
                web.header('Content-Length', os.path.getsize(download_name))
                web.header('Content-Disposition', 'attachment; filename=meteomap')
                img = open(download_name,'rb')
                return img.read()
            else:
                download_name = os.path.join('plugins', 'chmi', 'static', 'images', 'none.png')  
                content = mimetypes.guess_type(download_name)[0]
                web.header('Content-type', content)
                web.header('Content-Length', os.path.getsize(download_name))
                web.header('Content-Disposition', 'attachment; filename=none_map')
                img = open(download_name,'rb')
                return img.read()
        except:
            log.error(NAME, _('CHMI plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('chmi -> download_page GET')
            return self.core_render.notice('/', msg)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            return self.plugin_render.chmi_help()
        except:
            log.error(NAME, _('CHMI plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('chmi -> help_page GET')
            return self.core_render.notice('/', msg)

class log_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            return self.plugin_render.chmi_log(read_log(), plugin_options)
        except:
            log.error(NAME, _('CHMI plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('chmi -> log_page GET')
            return self.core_render.notice('/', msg)

class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(plugin_options)
        except:
            return {}

class log_json(ProtectedPage):
    """Returns data in JSON format."""
    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(read_log())
        except:
            return {}

class status_json(ProtectedPage):
    """Returns the current plugin status log in JSON format."""
    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps({'events': log.events(NAME)})
        except:
            return {}

class dependency_json(ProtectedPage):
    """Returns SHMU dependency state in JSON format."""
    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps({
                'missing': shmu_missing_dependencies(),
                'installing': shmu_dependencies_installing(),
            })
        except:
            return {}

class animation_json(ProtectedPage):
    """Returns radar animation frame metadata in JSON format."""
    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            with animation_lock:
                frames = [
                    {
                        'index': index,
                        'date': frame['date'],
                        'label': frame['label'],
                        'type': frame['type'],
                        'relative': frame['relative'],
                        'rgb': frame.get('rgb'),
                        'url': plugin_url(animation_frame) + '?i={}&ts={}'.format(index, frame['date']),
                    }
                    for index, frame in enumerate(animation_frames)
                ]
            return json.dumps({'enabled': plugin_options['enabled'] and (plugin_options['ANIMATE'] or plugin_options['HOME_WIDGET']), 'frames': frames})
        except:
            log.error(NAME, _('CHMI plug-in') + ':\n' + traceback.format_exc())
            return {}

class animation_frame(ProtectedPage):
    """Returns one radar animation frame from RAM."""
    def GET(self):
        try:
            qdict = web.input()
            index = int(qdict.get('i', 0))
            with animation_lock:
                if index < 0 or index >= len(animation_frames):
                    raise IndexError()
                frame = animation_frames[index]
                content = frame['content']
            web.header('Content-type', 'image/png')
            web.header('Content-Length', len(content))
            web.header('Cache-Control', 'no-store')
            return content
        except:
            download_name = os.path.join('plugins', 'chmi', 'static', 'images', 'none.png')
            content = mimetypes.guess_type(download_name)[0]
            web.header('Content-type', content)
            web.header('Content-Length', os.path.getsize(download_name))
            img = open(download_name,'rb')
            return img.read()

class log_csv(ProtectedPage):  # save log file from web as csv file type
    """Simple Log API"""
    def GET(self):
        data = {}
        try:
            log_file = read_log()
            data = "Date/Time; Date; Time; Red; Green; Blue\n"
            for interval in log_file:
                data += '; '.join([
                    interval['datetime'],
                    interval['date'],
                    interval['time'],
                    '{}'.format(interval['red']),
                    '{}'.format(interval['green']),
                    '{}'.format(interval['blue']),
                ]) + '\n'

            content = mimetypes.guess_type(os.path.join(plugin_data_dir(), 'log.json')[0])
            web.header('Access-Control-Allow-Origin', '*')
            web.header('Content-type', content) 
            web.header('Content-Disposition', 'attachment; filename="meteo_log.csv"')
            return data

        except:
            log.error(NAME, _('CHMI plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('chmi -> settings_page GET')
            return self.core_render.notice('/', msg)


class state_json(ProtectedPage):
    """Returns seconds location state in JSON format."""
    def GET(self):
        global checker
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data = {}
        try:
            if checker.status['state']:
               data['state'] = _('RAIN IN LOCATION')
            else:
                if options.weather_lat and options.weather_lon:
                    data['state'] = _('NOT RAIN IN LOCATION')
                else:
                    data['state'] = _('MY LOCATION IS NOT SET')
            return json.dumps(data)
        except:
            return {}
