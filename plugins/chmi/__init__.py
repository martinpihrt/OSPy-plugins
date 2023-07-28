# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'

# LaskaKit map https://www.laskakit.cz/laskakit-interaktivni-mapa-cr-ws2812b/

import datetime
from datetime import timedelta
import time
import sys
import os
import mimetypes

from threading import Thread, Event
import traceback
import json

import web
from ospy.log import log
from ospy.options import options, rain_blocks
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string, stop_onrain
from plugins import PluginOptions, plugin_url, plugin_data_dir

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer

from PIL import Image
from PIL import ImageDraw
import requests
from io import BytesIO



NAME = 'CHMI'
MENU =  _(u'Package: CHMI radar')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {
        'enabled': False,
        'use_footer': False,         # Information in footer
        'USE_RAIN_DELAY': False,     # If the box is checked, a rain delay will be set if rain is detected. The location coordinates are obtained from the OSPy settings from the weather/location menu. For proper function, you need to enter your location in the settings (for example, Prague).
        'RAIN_DELAY': 1,             # In hours
        'LON_0': 11.2673442,         # TOP LEFT CORNER
        'LAT_0': 52.1670717,
        'LON_1': 20.7703153,         # LOWER RIGHT CORNER
        'LAT_1': 48.1,
        'IP_ADDR': '192.168.88.2',   # remote map IP address
        'HW_BOARD': '0'              # 0 = laskakit board, 1 = tmep board, 3 = pihrt board
    })

# We work in the WGS-84 coordinate system
# In order to be able to convert degrees of latitude and longitude into pixels,
# we need to know the coordinates of the upper left and lower right edges of the ČHMÚ radar image

################################################################################
# Main function loop:                                                          #
################################################################################
class CHMI_Checker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()

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
        while not self._stop_event.is_set():
            self._sleep(1)
            try:
                if plugin_options['enabled']:
                    chmi_mon = None
                    if plugin_options['use_footer']:
                        chmi_mon = showInFooter()                               # instantiate class to enable data in footer
                        chmi_mon.label = _('CHMI meteoradar')                   # label on footer
                        chmi_mon.button = "chmu/settings"                       # button redirect on footer
                        chmi_mon.val = '---'                                    # value on footer

                    log.clear(NAME)
                    dis_text = True
                    # Bitmap dimensions in degrees
                    degree_width  = float(plugin_options['LON_1']) - float(plugin_options['LON_0'])
                    degree_heigth = float(plugin_options['LAT_0']) - float(plugin_options['LAT_1'])

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
                            image_path = os.path.join(plugin_data_dir(), 'last.png')
                            watermark_path = os.path.join('plugins','chmi','static','images','cr_borders.png')
                            result_path = os.path.join(plugin_data_dir(),'result.png')
                            try:
                                bitmap.save(image_path)
                                # Merge images (radar and outline of the Czech Republic)
                                wmark = Image.open(watermark_path)
                                img = Image.open(image_path)
                                ia, wa = None, None
                                if len(img.getbands()) == 4:
                                    ir, ig, ib, ia = img.split()
                                    img = Image.merge('RGB', (ir, ig, ib))
                                if len(wmark.getbands()) == 4:
                                    wa = wmark.split()[-1]
                                img.paste(wmark, (0, 0), wmark)
                                if ia:
                                    if wa:
                                        # This seems to solve the contradiction, discard if unwanted
                                        ia = max_alpha(wa, ia)
                                    img.putalpha(ia)
                                img.save(result_path)
                                log.debug(NAME, datetime_string() + ' ' + _('The merging of the images (radar and outline of the Czech Republic) went OK.'))
                            except:
                                pass
                                log.error(NAME, datetime_string() + ' ' + _('Image cannot be saved.') + ':\n' + traceback.format_exc())

                            # The original image uses an indexed color palette. This can be useful, but for the simplicity of the example, we will convert the image to full RGB
                            log.debug(NAME, datetime_string() + ' ' + _('Converting the image to RGB...'))
                            bitmap = bitmap.convert("RGB")
                            screen = ImageDraw.Draw(bitmap)
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

                            log.debug(NAME, datetime_string() + ' ' + _('Loading cities database...'))
                            if plugin_options['HW_BOARD']   == "0":
                                city_table = 'laska_cities'
                            elif plugin_options['HW_BOARD'] == "1":
                                city_table = 'tmep_cities'
                            elif plugin_options['HW_BOARD'] == "2":
                                city_table = 'pihrt_cities'
                            else:
                                return

                            cities_with_rain = []
                            cities_path = os.path.join('plugins', 'chmi', 'static', city_table)
                            with open(cities_path, "r") as fi:
                                cities = fi.readlines()
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
                                        x = int((lon - plugin_options['LON_0']) / size_lon_pixel)
                                        y = int((plugin_options['LAT_0'] - lat) / size_lat_pixel)
                                        # We will find the RGB on the given coordinate, i.e. the possible color of the rain
                                        r,g,b = bitmap.getpixel((x, y))
                                        # If there is a non-zero color in a given location on the radar image, it is probably raining there
                                        # The intensity of the rain is determined by a specific color ranging from light blue to green, red to white
                                        # Right here we could also detect the strength of the rain, but for the simplicity of the example we will do with a simple color
                                        if r+g+b > 0:
                                            # If we activated drawing at the beginning of the program,
                                            # on the canvas we draw a square with dimensions of 10×10 px representing the city
                                            # The square will have the color of rain and a red outline
                                            screen.rectangle((x-5, y-5, x+5, y+5), fill=(r, g, b), outline=(255, 0, 0))
                                            # If logging is active, we will display colored text indicating that it is raining in the given city,
                                            # and we add the city to the list as a structure {"id":id, "r":r, "g":g, "b":b} 
                                            log.info(NAME, datetime_string() + ' ' + _('In city {} ({}) it is probably raining right now').format(name, idx))
                                            log.debug(NAME, 'msg R={} G={} B={}'.format(r, g, b))
                                            cities_with_rain.append({"id": idx, "r": r, "g": g, "b": b})
                                        else:
                                            # If it is not raining in the given city, we draw an empty square with a white outline in its coordinates
                                            screen.rectangle((x-5, y-5, x+5, y+5), fill=(0, 0, 0), outline=(255, 255, 255))
                            
                            # RAIND DELAY and FOOTER
                            tempText = ""
                            if plugin_options['USE_RAIN_DELAY']:
                                delaytime = int(plugin_options['RAIN_DELAY'])
                                if options.weather_lat and options.weather_lon:
                                    log.debug(NAME, datetime_string() + ' ' + _('My location latitude {}  longitude {}.').format(options.weather_lat, options.weather_lon))
                                    # TODO
                                    #rain_blocks[NAME] = datetime.datetime.now() + datetime.timedelta(hours=float(delaytime))
                                    #stop_onrain()
                                    if plugin_options['use_footer']:
                                        if chmi_mon is not None:
                                            tempText += _(u'CHMI detected Rain') + '. ' + _(u'Adding delay of') + ' ' + str(delaytime) + ' ' + _(u'hours') 
                                            chmi_mon.val = tempText.encode('utf8').decode('utf8')    # value on footer


                            # We ve gone through all the cities, so well see if we have any on the list that are raining
                            if len(cities_with_rain) > 0:
                                # we save the list of cities that had rain as JSON
                                # We then send the JSON form with the variable name "city" to the LaskaKit map of the Czech Republic via HTTP POST
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
                                    r = requests.post(addr, data=form_data)
                                    if r.status_code == 200:
                                        log.debug(NAME, datetime_string() + ' ' + _('HTTP {}').format(r.text))
                                    else:
                                        log.error(NAME, datetime_string() + ' ' + _('HTTP {}: I cannot connect to the board map of the Czech Republic at the URL http://{}/').format(r.status_code, plugin_options['IP_ADDR']))
                                except:
                                    pass
                                    log.debug(NAME, traceback.format_exc())
                                    log.error(NAME, datetime_string() + ' ' + _('I cannot connect to the map board of the Czech Republic at the URL http://{}/').format(plugin_options['IP_ADDR']))                                        
                            else:
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
        checker.join()
        checker = None

# Function to download bitmap with radar data from URL:
# https://www.chmi.cz/files/portal/docs/meteo/rad/inca-cz/data/czrad-z_max3d_masked/pacz2gmaps3.z_max3d.{datum_txt}.0.png
# date_txt must be in UTC YYYYMMDD.HHM0 format (ČHMÚ publishes images every full 10 minutes)
# If the URL is not valid (the image does not exist yet),
# I'll try to download a bitmap with a ten minute old timestamp
# The number of repetitions is determined by the variable trials 
def download_radar(date=None, trials=5):
    if date == None:
        date = datetime.datetime.utcnow()

    date_txt = date
    while trials > 0:
        date_txt = date.strftime("%Y%m%d.%H%M")[:-1] + "0"
        try:
            url = f"https://www.chmi.cz/files/portal/docs/meteo/rad/inca-cz/data/czrad-z_max3d_masked/pacz2gmaps3.z_max3d.{date_txt}.0.png"
            log.debug(NAME,datetime_string() + ' ' + _('Downloading a file: {}').format(url))
            r = requests.get(url)
            if r and r.status_code == 200:
                return True, r.content, date_txt
            else:
                log.error(NAME, _('HTTP {}: I can not download the file.').format(r.status_code))
                log.info(NAME, _('I will try to download a file that is 10 minutes older.'))
                date -= timedelta(minutes=10)
                trials -= 1
                time.sleep(1)
        except:
            log.debug(NAME, traceback.format_exc())
            pass
            return False, None, date_txt

    return False, None, date_txt


def rgb_msg(r,g,b, msg):
    return '\x1b[38;2;{};{};{}m{}\x1b[0m'.format(r, g, b, msg)


def max_alpha(a, b):
    # Assumption: 'a' and 'b' are of same size
    im_a = a.load()
    im_b = b.load()
    width, height = a.size

    alpha = Image.new('L', (width, height))
    im = alpha.load()
    for x in xrange(width):
        for y in xrange(height):
            im[x, y] = max(im_a[x, y], im_b[x, y])
    return alpha


################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering adjustments"""

    def GET(self):
        return self.plugin_render.chmi(plugin_options, log.events(NAME))

    def POST(self):
        plugin_options.web_update(web.input())
        if checker is not None:
            checker.update()
        raise web.seeother(plugin_url(settings_page), True)


class download_page(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        try:
            download_name = plugin_data_dir() + '/' + 'result.png'          
            if os.path.isfile(download_name):     # exists image? 
                content = mimetypes.guess_type(download_name)[0]
                web.header('Content-type', content)
                web.header('Content-Length', os.path.getsize(download_name))
                web.header('Content-Disposition', 'attachment; filename=last_map')
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
            pass
            log.error(NAME, _('CHMI plug-in') + ':\n' + traceback.format_exc())
            return self.plugin_render.chmi(plugin_options, log.events(NAME))


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.chmi_help()


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)