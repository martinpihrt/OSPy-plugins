# -*- coding: utf-8 -*-
# first author: Martin Pihrt
# Martin Pihrt add i18n language support
__author__ = u'Vaclav Hrabe' # Add netatmo function 

import datetime
from threading import Thread, Event
import traceback
import shutil
import json
import time
import re
import os
#import lnetatmo

import web
from time import strftime
from ospy.log import log
from ospy.options import options
from ospy.options import level_adjustments
from ospy.helpers import mkdir_p, is_python2
from ospy.webpages import ProtectedPage
from ospy.weather import weather
from plugins import PluginOptions, plugin_url, plugin_data_dir

import imghdr
import warnings

if is_python2():
    from urllib import urlencode
    import urllib2
else:
    import urllib.parse, urllib.request

NAME = 'Weather-based Water Level Netatmo'
MENU =  _(u'Package: Weather-based Water Level Netatmo')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {
        'enabled': False,
        'wl_min': 0,
        'wl_max': 200,
        'days_history': 3,
        'days_forecast': 3,
        'use_netatmo': False,
        'netatmo_id':'',
        'netatmo_secret':'',
        'netatmo_user':'',
        'netatmo_pass':'',
        'netatmomac': '',
        'netatmorain': '05:00:00:',
        'netatmo_days': 3,
        'netatmo_level': 4
    })


################################################################################
# Main function loop:                                                          #
################################################################################
class WeatherLevelChecker(Thread):
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
        weather.add_callback(self.update)
        self._sleep(10)  # Wait for weather callback before starting        
        while not self._stop_event.is_set():
            try:
                log.clear(NAME)
                if plugin_options['enabled']:
                    log.debug(NAME, _(u'Checking weather status') + '...')
                    
                    if plugin_options['use_netatmo']:
                        authorization = ClientAuth()
                        devList = WeatherStationData(authorization)
                        now = time.time()
                        begin = now - (plugin_options['days_history']) * 24 * 3600
                        mac2 = plugin_options['netatmomac']
                        rainmac2 = plugin_options['netatmorain']
                        resp =  (devList.getMeasure (mac2, '1hour', 'sum_rain', rainmac2, date_begin=begin, date_end=now, limit=None, optimize=False) )
                        result = [(time.ctime(int(k)),v[0]) for k,v in resp['body'].items()]
                        result.sort()
                        xdate, xrain = zip(*result)
                        zrain = 0
                        for yrain in xrain:
                            zrain = zrain + yrain
                    else:
                        zrain = 0

                    info = []
                    days = 0
                    total_info = {'rain_mm': 0.0}
                    for day in range(-plugin_options['days_history'], plugin_options['days_forecast']+1):
                        check_date = datetime.date.today() + datetime.timedelta(days=day)
                        hourly_data = weather.get_hourly_data(check_date)
                        if hourly_data:
                            days += 1
                        info += hourly_data

                        total_info['rain_mm'] += weather.get_rain(check_date)

                    log.info(NAME, _(u'Using') + ' %d ' % days + _(u'days of information.'))

                    total_info.update({
                        'temp_c': sum([val['temperature'] for val in info]) / len(info),
                        'wind_ms': sum([val['windSpeed'] for val in info]) / len(info),
                        'humidity': sum([val['humidity'] for val in info]) / len(info)
                    })  

                    # We assume that the default 100% provides 4mm water per day (normal need)
                    # We calculate what we will need to provide using the mean data of X days around today

                    water_needed = 4 * days                                     # 4mm per day
                    water_needed *= 1 + (total_info['temp_c'] - 20) / 15        # 5 => 0%, 35 => 200%
                    water_needed *= 1 + (total_info['wind_ms'] / 100)           # 0 => 100%, 20 => 120%
                    water_needed *= 1 - (total_info['humidity'] - 50) / 200     # 0 => 125%, 100 => 75%
                    water_needed = round(water_needed, 1)

                    water_left = water_needed - total_info['rain_mm']
                    water_left = round(max(0, min(100, water_left)), 1)

                    water_adjustment = round((water_left / (4 * days)) * 100, 1)

                    level_adjustments[NAME] = water_adjustment / 100

                    if plugin_options['use_netatmo']:
                        water_left = water_needed - zrain - total_info['rain_mm']
                        water_left = round(max(0, min(100, water_left)), 1)

                    else:
                        water_left = water_needed - total_info['rain_mm']
                        water_left = round(max(0, min(100, water_left)), 1)

                    water_adjustment = round((water_left / ((plugin_options['netatmo_level']) * days)) * 100, 1)

                    water_adjustment = float(
                        max(plugin_options['wl_min'], min(plugin_options['wl_max'], water_adjustment)))

                    log.info(NAME, _(u'Water needed') + '(%d ' %days +  _(u'days') + '): %.1fmm' % water_needed)
                    log.info(NAME, _(u'Total rainfall') + ': %.1fmm' % total_info['rain_mm'])
                    log.info(NAME, _(u'_______________________________'))
                    log.info(NAME, _(u'Irrigation needed') + ': %.1fmm' % water_left)
                    log.info(NAME, _(u'Weather Adjustment') + ': %.1f%%' % water_adjustment)
                    log.info(NAME, _(u'_______________________________'))
                    log.info(NAME, _(u'History rain by Netatmo') + ': %.1fmm' % zrain)

                    self._sleep(3600)

                else:
                    log.clear(NAME)
                    log.info(NAME, _(u'Plug-in is disabled.'))
                    if NAME in level_adjustments:
                        del level_adjustments[NAME]
                    self._sleep(24*3600)

            except Exception:
                log.error(NAME, _(u'Weather-based water level plug-in') + ':\n' + traceback.format_exc())
                self._sleep(3600)
        weather.remove_callback(self.update)

checker = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global checker
    if checker is None:
        checker = WeatherLevelChecker()

def stop():
    global checker
    if checker is not None:
        checker.stop()
        checker.join()
        checker = None
    if NAME in level_adjustments:
        del level_adjustments[NAME]


################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering weather-based irrigation adjustments"""

    def GET(self):
        return self.plugin_render.weather_based_water_level_netatmo(plugin_options, log.events(NAME))

    def POST(self):
        plugin_options.web_update(web.input())
        if checker is not None:
            checker.update()
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help page."""

    def GET(self):
        return self.plugin_render.weather_based_water_level_netatmo_help()        


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)


#########################################################################
#NetAtmo APi
#########################################################################

# Published Jan 2013
# Revised Jan 2014 (to add new modules data)
# Author : Philippe Larduinat, philippelt@users.sourceforge.net
# Public domain source code

#########################################################################


# Common definitions
_CLIENT_ID     = (plugin_options['netatmo_id'])   # Your client ID from Netatmo app registration at http://dev.netatmo.com/dev/listapps
_CLIENT_SECRET = (plugin_options['netatmo_secret'])   # Your client app secret   '     '
_USERNAME      = (plugin_options['netatmo_user'])   # Your netatmo account username
_PASSWORD      = (plugin_options['netatmo_pass'])   # Your netatmo account password
_BASE_URL       = "https://api.netatmo.com/"
_AUTH_REQ       = _BASE_URL + "oauth2/token"
_GETMEASURE_REQ = _BASE_URL + "api/getmeasure"
_GETSTATIONDATA_REQ = _BASE_URL + "api/getstationsdata"
_GETEVENTSUNTIL_REQ = _BASE_URL + "api/geteventsuntil"


class ClientAuth:
    """
    Request authentication and keep access token available through token method. Renew it automatically if necessary

    Args:
        clientId (str): Application clientId delivered by Netatmo on dev.netatmo.com
        clientSecret (str): Application Secret key delivered by Netatmo on dev.netatmo.com
        username (str)
        password (str)
        scope (Optional[str]): Default value is 'read_station'
            read_station: to retrieve weather station data (Getstationsdata, Getmeasure)
            read_camera: to retrieve Welcome data (Gethomedata, Getcamerapicture)
            access_camera: to access the camera, the videos and the live stream.
            Several value can be used at the same time, ie: 'read_station read_camera'
    """

    def __init__(self, clientId=_CLIENT_ID,
                       clientSecret=_CLIENT_SECRET,
                       username=_USERNAME,
                       password=_PASSWORD,
                       scope="read_station"):
        postParams = {
                "grant_type" : "password",
                "client_id" : clientId,
                "client_secret" : clientSecret,
                "username" : username,
                "password" : password,
                "scope" : scope
                }
        resp = postRequest(_AUTH_REQ, postParams)
        self._clientId = clientId
        self._clientSecret = clientSecret
        self._accessToken = resp['access_token']
        self.refreshToken = resp['refresh_token']
        self._scope = resp['scope']
        self.expiration = int(resp['expire_in'] + time.time())

    @property
    def accessToken(self):

        if self.expiration < time.time(): # Token should be renewed
            postParams = {
                    "grant_type" : "refresh_token",
                    "refresh_token" : self.refreshToken,
                    "client_id" : self._clientId,
                    "client_secret" : self._clientSecret
                    }
            resp = postRequest(_AUTH_REQ, postParams)
            self._accessToken = resp['access_token']
            self.refreshToken = resp['refresh_token']
            self.expiration = int(resp['expire_in'] + time.time())
        return self._accessToken


class User:
    """
    This class returns basic information about the user

    Args:
        authData (ClientAuth): Authentication information with a working access Token
    """
    def __init__(self, authData):
        postParams = {
                "access_token" : authData.accessToken
                }
        resp = postRequest(_GETSTATIONDATA_REQ, postParams)
        self.rawData = resp['body']
        self.devList = self.rawData['devices']
        self.ownerMail = self.rawData['user']['mail']

class WeatherStationData:
    """
    List the Weather Station devices (stations and modules)

    Args:
        authData (ClientAuth): Authentication information with a working access Token
    """
    def __init__(self, authData):
        self.getAuthToken = authData.accessToken
        postParams = {
                "access_token" : self.getAuthToken
                }
        resp = postRequest(_GETSTATIONDATA_REQ, postParams)
        self.rawData = resp['body']['devices']
        self.stations = { d['_id'] : d for d in self.rawData }
        self.modules = dict()
        for i in range(len(self.rawData)):
            for m in self.rawData[i]['modules']:
                self.modules[ m['_id'] ] = m
        self.default_station = list(self.stations.values())[0]['station_name']

    def modulesNamesList(self, station=None):
        res = [m['module_name'] for m in self.modules.values()]
        res.append(self.stationByName(station)['module_name'])
        return res

    def stationByName(self, station=None):
        if not station : station = self.default_station
        for i,s in self.stations.items():
            if s['station_name'] == station :
                return self.stations[i]
        return None

    def stationById(self, sid):
        return None if sid not in self.stations else self.stations[sid]

    def moduleByName(self, module, station=None):
        s = None
        if station :
            s = self.stationByName(station)
            if not s : return None
        for m in self.modules:
            mod = self.modules[m]
            if mod['module_name'] == module :
                if not s or mod['main_device'] == s['_id'] : return mod
        return None

    def moduleById(self, mid, sid=None):
        s = self.stationById(sid) if sid else None
        if mid in self.modules :
            if s:
                for module in s['modules']:
                    if module['_id'] == mid:
                        return module
            else:
                return self.modules[mid]

    def lastData(self, station=None, exclude=0):
        s = self.stationByName(station)
        if not s : return None
        lastD = dict()
        # Define oldest acceptable sensor measure event
        limit = (time.time() - exclude) if exclude else 0
        ds = s['dashboard_data']
        if ds['time_utc'] > limit :
            lastD[s['module_name']] = ds.copy()
            lastD[s['module_name']]['When'] = lastD[s['module_name']].pop("time_utc")
            lastD[s['module_name']]['wifi_status'] = s['wifi_status']
        for module in s["modules"]:
            ds = module['dashboard_data']
            if ds['time_utc'] > limit :
                lastD[module['module_name']] = ds.copy()
                lastD[module['module_name']]['When'] = lastD[module['module_name']].pop("time_utc")
                # For potential use, add battery and radio coverage information to module data if present
                for i in ('battery_vp', 'rf_status') :
                    if i in module : lastD[module['module_name']][i] = module[i]
        return lastD

    def checkNotUpdated(self, station=None, delay=3600):
        res = self.lastData(station)
        ret = []
        for mn,v in res.items():
            if time.time()-v['When'] > delay : ret.append(mn)
        return ret if ret else None

    def checkUpdated(self, station=None, delay=3600):
        res = self.lastData(station)
        ret = []
        for mn,v in res.items():
            if time.time()-v['When'] < delay : ret.append(mn)
        return ret if ret else None

    def getMeasure(self, device_id, scale, mtype, module_id=None, date_begin=None, date_end=None, limit=None, optimize=False, real_time=False):
        postParams = { "access_token" : self.getAuthToken }
        postParams['device_id']  = device_id
        if module_id : postParams['module_id'] = module_id
        postParams['scale']      = scale
        postParams['type']       = mtype
        if date_begin : postParams['date_begin'] = date_begin
        if date_end : postParams['date_end'] = date_end
        if limit : postParams['limit'] = limit
        postParams['optimize'] = "true" if optimize else "false"
        postParams['real_time'] = "true" if real_time else "false"
        return postRequest(_GETMEASURE_REQ, postParams)

    def MinMaxTH(self, station=None, module=None, frame="last24"):
        if not station : station = self.default_station
        s = self.stationByName(station)
        if not s :
            s = self.stationById(station)
            if not s : return None
        if frame == "last24":
            end = time.time()
            start = end - 24*3600 # 24 hours ago
        elif frame == "day":
            start, end = todayStamps()
        if module and module != s['module_name']:
            m = self.moduleByName(module, s['station_name'])
            if not m :
                m = self.moduleById(s['_id'], module)
                if not m : return None
            # retrieve module's data
            resp = self.getMeasure(
                    device_id  = s['_id'],
                    module_id  = m['_id'],
                    scale      = "max",
                    mtype      = "Temperature,Humidity",
                    date_begin = start,
                    date_end   = end)
        else : # retrieve station's data
            resp = self.getMeasure(
                    device_id  = s['_id'],
                    scale      = "max",
                    mtype      = "Temperature,Humidity",
                    date_begin = start,
                    date_end   = end)
        if resp:
            T = [v[0] for v in resp['body'].values()]
            H = [v[1] for v in resp['body'].values()]
            return min(T), max(T), min(H), max(H)
        else:
            return None

class DeviceList(WeatherStationData):
    """
    This class is now deprecated. Use WeatherStationData directly instead
    """
    warnings.warn("The 'DeviceList' class was renamed 'WeatherStationData'",
            DeprecationWarning )
    pass

# Utilities routines

def postRequest(url, params, json_resp=True, body_size=65535):
    # Netatmo response body size limited to 64k (should be under 16k)
    if is_python2():
        params = urlencode(params)
        headers = {"Content-Type" : "application/x-www-form-urlencoded;charset=utf-8"}
        req = urllib2.Request(url=url, data=params, headers=headers)
        resp = urllib2.urlopen(req).read(body_size)
    else:
        req = urllib.request.Request(url)
        req.add_header("Content-Type","application/x-www-form-urlencoded;charset=utf-8")
        params = urllib.parse.urlencode(params).encode('utf-8')
        resp = urllib.request.urlopen(req, params).read(body_size).decode("utf-8")
                
    if json_resp:
        return json.loads(resp)
    else:
        return resp

def toTimeString(value):
    return time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime(int(value)))

def toEpoch(value):
    return int(time.mktime(time.strptime(value,"%Y-%m-%d_%H:%M:%S")))

def todayStamps():
    today = time.strftime("%Y-%m-%d")
    today = int(time.mktime(time.strptime(today,"%Y-%m-%d")))
    return today, today+3600*24

# Global shortcut

def getStationMinMaxTH(station=None, module=None):
    authorization = ClientAuth()
    devList = DeviceList(authorization)
    if not station : station = devList.default_station
    if module :
        mname = module
    else :
        mname = devList.stationByName(station)['module_name']
    lastD = devList.lastData(station)
    if mname == "*":
        result = dict()
        for m in lastD.keys():
            if time.time()-lastD[m]['When'] > 3600 : continue
            r = devList.MinMaxTH(module=m)
            result[m] = (r[0], lastD[m]['Temperature'], r[1])
    else:
        if time.time()-lastD[mname]['When'] > 3600 : result = ["-", "-"]
        else : result = [lastD[mname]['Temperature'], lastD[mname]['Humidity']]
        result.extend(devList.MinMaxTH(station, mname))
    return result
