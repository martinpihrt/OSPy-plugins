# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt' # www.pihrt.com

# System imports
import datetime
import time
from threading import Thread, Event
import traceback
import json
import web

# Local imports
from ospy.log import log
from ospy.options import options
from ospy.options import rain_blocks
from ospy.scheduler import predicted_schedule
from ospy.stations import stations
from ospy.inputs import inputs
from ospy.outputs import outputs
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string
from plugins import PluginOptions, plugin_url

from blinker import signal

pressurizer_master_relay_on = signal('pressurizer_master_relay_on')   # send signal relay on for others in OSPy system
pressurizer_master_relay_off = signal('pressurizer_master_relay_off') # send signal relay off for others in OSPy system


NAME = 'Pressurizer'
MENU =  _('Package: Pressurizer')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {
        'enabled': False,               # default is OFF
        'pre_time': 20,                 # how many seconds before turning on station has turning on master station 0-999s
        'run_time': 5,                  # for what time will turn on the master station (5 sec) 0-999s
        'mm':       60,                 # How long after the relay is activated wait for another stations (in order not to activate the pressurizer before each switch is stations on) 0-999 min
        'ss':       0,                  # 0-59 sec                  
        'relay': False,                 # activated master relay?
    })


################################################################################
# Main function loop:                                                          #
################################################################################
class Checker(Thread):
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

    def run(self):
        log.clear(NAME)
      
        if not plugin_options['enabled']:
            log.info(NAME, _('Pressurizer is disabled.'))
        else:
            log.info(NAME, _('Pressurizer is enabled.'))

        start_master = False                      # for master station ON/OFF  
        pressurizer_master_relay_off.send()       # send signal relay off from this plugin
     
        while not self._stop.is_set():
            try: 
                if plugin_options['enabled']:     # plugin is enabled
                    current_time  = datetime.datetime.now()
                    user_pre_time = current_time + datetime.timedelta(seconds=int(plugin_options['pre_time']))
                    check_start   = current_time - datetime.timedelta(days=1)
                    check_end     = current_time + datetime.timedelta(days=1)

                    schedule = predicted_schedule(check_start, check_end)
                    rain = not options.manual_mode and (rain_blocks.block_end() > datetime.datetime.now() or inputs.rain_sensed())                                   
       
                    if stations.master is None:
                        start_master = False
                        log.clear(NAME)
                        log.info(NAME, datetime_string() + ' ' + _('This plugin requires setting master station to enabled. Setup this in options! And also enable the relay as master station in options!'))
                        self._sleep(10)

                    for entry in schedule:
                        if entry['start'] <= user_pre_time < entry['end']:       # is possible program in this interval?
                           if not rain and not entry['blocked']:                 # is not blocked and not ignored rain?  
                                if stations.master is not None:
                                    log.clear(NAME)
                                    log.info(NAME, datetime_string() + ' ' + _('Is time for pump running...')) 
                                    start_master = True


                    if start_master:  # is time for run relay
                        pname = _('Pressurizer plug-in')
                        program_name = "%s " % pname.encode("utf-8", errors="ignore") # program name

                        sname = 0 
                        
                        for station in stations.get():
                            if station.is_master:
                                sname = station.index                                 # master pump index

                        pend = current_time + datetime.timedelta(seconds=int(plugin_options['run_time']))

                        _entry = {
                            'active': None,
                            'program': -1,
                            'program_name': program_name,
                            'fixed': True,
                            'cut_off': 0,
                            'manual': True,
                            'blocked': False,
                            'start': datetime.datetime.now(),
                            'original_start': datetime.datetime.now(),
                            'end': pend,
                            'uid': '%s-%s-%d' % (datetime.datetime.now(), str(program_name), sname),
                            'usage': 2.0,
                            'station': sname
                        }


                        if plugin_options['relay']:  
                            pressurizer_master_relay_on.send()                  # send signal relay on from this plugin
                            self._sleep(0.5) 
                            outputs.relay_output = True                         # activate relay
                            log.info(NAME,  _('Activating relay.')) 
                            log.start_run(_entry) 
 
                            wait_for_run = plugin_options['run_time']           # pump run time
                            if wait_for_run > plugin_options['pre_time']:       # is not run time > pre run time?
                                wait_for_run = plugin_options['pre_time']       # scheduller tick is 1 second 

                            log.info(NAME, datetime_string() + ' ' + _('Waiting') + ' ' + str(wait_for_run)  + ' ' +  _('second.')) 
                            self._sleep(int(wait_for_run))                      # waiting on run time
  
                            pressurizer_master_relay_off.send()                 # send signal relay off from this plugin
                            self._sleep(0.5)
                            outputs.relay_output = False                        # deactivate relay 
                            log.info(NAME, _('Deactivating relay.')) 
                            log.finish_run(_entry)

                            log.info(NAME, datetime_string() + ' ' + _('Ready.'))
                            start_master = False 

                            seconds = int(plugin_options['mm'] or 0) * 60 + int(plugin_options['ss'] or 0) # (mm:ss)
                            log.info(NAME, datetime_string() + ' ' + _('Waiting') + ' ' + str(seconds)  + ' ' +  _('second.')) 
                            self._sleep(seconds) # How long after the relay is activated wait for another stations 

                    else:
                        self._sleep(2)        

                else:
                    self._sleep(5)                   

                self._sleep(1)    
                                             
            except Exception:
                log.error(NAME, _('Pressurizer plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)


checker = None


################################################################################
# Helper functions:                                                            #
################################################################################
  
def start():
    global checker
    if checker is None:
        checker = Checker()


def stop():
    global checker
    if checker is not None:
        checker.stop()
        checker.join()
        checker = None       


################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering voice notification adjustments"""

    def GET(self):
        return self.plugin_render.pressurizer(plugin_options, log.events(NAME))

    def POST(self):
        plugin_options.web_update(web.input())

        if checker is not None:
            checker.update()

        if plugin_options['enabled']:
            log.clear(NAME) 
            log.info(NAME, _('Pressurizer is enabled.'))
        else:
            log.clear(NAME)
            log.info(NAME, _('Pressurizer is disabled.'))

        log.info(NAME, _('Options has updated.'))
        raise web.seeother(plugin_url(settings_page), True) 


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)
