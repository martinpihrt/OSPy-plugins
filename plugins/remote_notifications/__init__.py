# !/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# this plugins send GET data to remote web server

import json
import time
import os
import os.path
import traceback
import urllib2             
import re
from threading import Thread, Event

import web
from ospy.webpages import ProtectedPage
from plugins import PluginOptions, plugin_url
from ospy.options import options
from ospy.stations import stations
from ospy.inputs import inputs
from ospy.log import log, EVENT_FILE
from ospy.helpers import datetime_string, get_input

import i18n


NAME = 'Remote Notifications'
LINK = 'settings_page'

remote_options = PluginOptions(
    NAME,
    {
        'use': False,
        'rem_adr': "your web server",
        'api': "123456789"
    }
)


################################################################################
# Main function loop:                                                          #
################################################################################
class RemoteSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop = Event()

        self._sleep_time = 0
        self.start()

    def stop(self):
        self._stop.set()

    def update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def try_send(self, text):
        log.clear(NAME)
        try:
            send_data(text)  # send get data
            log.info(NAME, _('Remote was sent') + ':\n' + text)
        except Exception:
            log.error(NAME, _('Remote was not sent') + '!\n' + traceback.format_exc())

    def run(self):
        send_msg = False  # send get data if change (rain, end program ....
        last_rain = False 
        en_rain = True
        en_line = True
        en_line2 = True
  
        # ex: tank=100&rain=1&humi=55&line=1&lastrun=15.4.2016&station=kurnik&duration=5min 3sec&api=a1b2v5f4  
        rain = 0          # rain status for rain=0 or rain=1 in get data
        lastrun = ""      # date and time for lastrun=xxxxx in get data
        tank = ""         # actual %0-100 in water tank for tank=xx in get data
        duration = ""     # duration in last program for duration=xx:yy in get data
        station = ""      # name end station for station=abcde in get data
        humi = ""         # humidity in station for humi=xx in get data
        line = ""         # actual state from UPS plugin for line=0 or line=1 in get data

        finished_count = len([run for run in log.finished_runs() if not run['blocked']]) 

        while not self._stop.is_set():
            try:
               
                # Send data if rain detected, power line state a new finished run is found
                if remote_options["use"]:   
                    ### water tank level ###
                    try:
                       from plugins import tank_humi_monitor
                       tank = tank_humi_monitor.get_tank()
                       if tank < 0: # -1 is error I2C device for ping not found in tank_humi_monitor
                         tank = ""
                    except Exception:
                       tank = ""

                    ### power line state ###
                    try:
                       from plugins import ups_adj
                       lin = ups_adj.get_check_power() # read state power line from plugin
                       if lin==1: 
                          if en_line:  # send only if change 
                              send_msg = True 
                              en_line = False
                              en_line2 = True 
                          line = 0 # no power on web
                           
                       if lin==0:
                          if en_line2: # send only if change
                             send_msg = True
                             en_line2 = False
                             en_line = True
                          line = 1 # power ok on web
       
                    except Exception:
                       line = ""

                    ### rain state ###
                    if inputs.rain_sensed() and not last_rain:
                        send_msg = True
                        last_rain = inputs.rain_sensed()
                    if inputs.rain_sensed():
                        rain = 1
                        en_rain = True
                    else:
                        rain = 0 
                        if en_rain: # send data if no rain (only if change rain/norain...)
                           send_msg = True
                           en_rain = False

                    if not options.rain_sensor_enabled: # if rain sensor not used
                        rain = ""
                                        
                    ### program and station ###
                    finished = [run for run in log.finished_runs() if not run['blocked']]                    
                    if len(finished) > finished_count:
                        las = datetime_string()
                        lastrun = re.sub(" ", "_", las) # eliminate gap in the title to _
                        send_msg = True
                        ### humidity in station ###
                        try:
                            from plugins import tank_humi_monitor
                            humi = int(tank_humi_monitor.get_humidity((stations.get(run['station']).index)+1)) # 0-7 to 1-8 humidity  
                            if humi < 0:
                               humi = "" 
                                
                        except Exception:
                            humi = ""
   
                        for run in finished[finished_count:]:
                            dur = (run['end'] - run['start']).total_seconds()
                            minutes, seconds = divmod(dur, 60)
                            sta = "%s" % stations.get(run['station']).name 
                            station = re.sub(" ", "_", sta)  # eliminate gap in the title to _
                            duration = "%02d:%02d" % (minutes, seconds)                       

                    finished_count = len(finished)

                if (send_msg): # if enabled send data
                    body = ('tank=' + str(tank))
                    body += ('&rain=' + str(rain))
                    body += ('&humi=' + str(humi))
                    body += ('&line=' + str(line))
                    body += ('&lastrun=' + str(lastrun)) 
                    body += ('&station=' + str(station))
                    body += ('&duration=' + str(duration))
                    body += ('&api=' + remote_options['api'])  # API password
                    self.try_send(body)                        # Send GET data to remote server 
                    send_msg = False                           # Disable send data    
                    
                self._sleep(2)

            except Exception:
                log.error(NAME, _('Remote plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)


remote_sender = None


################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global remote_sender
    if remote_sender is None:
        remote_sender = RemoteSender()


def stop():
    global remote_sender
    if remote_sender is not None:
        remote_sender.stop()
        remote_sender.join()
        remote_sender = None


def send_data(text):
    """Send GET data"""
    if remote_options['use'] != '' and remote_options['api'] != '' and remote_options['rem_adr'] != '':
        req = urllib2.Request(url=remote_options['rem_adr']+'save.php/?' + text)
        req.add_header('Referer', 'OSPy sprinkler') 
        f = urllib2.urlopen(req)
        log.info(NAME, _('Remote server reply') + ':\n' + f.read())
    else:
        raise Exception(_('Remote plug-in is not properly configured') + '!')


################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering remote adjustments."""

    def GET(self):
        return self.plugin_render.remote_notifications(remote_options, log.events(NAME))

    def POST(self):
        remote_options.web_update(web.input())
        qdict = web.input()
        test = get_input(qdict, 'test', False, lambda x: True)

        if remote_sender is not None:
            remote_sender.update()

            if test:
                body = ('tank=')
                body += ('&rain=')
                body += ('&humi=')
                body += ('&line=')
                body += ('&lastrun=')
                body += ('&station=')
                body += ('&duration=')
                body += ('&program=')
                body += ('&api=' + remote_options['api'])  # API password
                remote_sender.try_send(body)

        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(remote_options)
