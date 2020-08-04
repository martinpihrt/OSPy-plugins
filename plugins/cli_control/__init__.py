# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import time
import traceback
import web
import subprocess


from blinker import signal

from ospy.stations import stations
from ospy.options import options
from ospy.helpers import datetime_string 
from ospy.log import log
from threading import Thread, Event
from plugins import PluginOptions, plugin_url
from ospy.webpages import ProtectedPage

NAME = 'CLI Control'         ### name for plugin in plugin manager ###
MENU =  _('Package: CLI Control')
LINK = 'settings_page'       ### link for page in plugin manager ###
 
plugin_options = PluginOptions(
    NAME,
    {u'use_control': False,
     u'on':  [u"echo 'example start command for station 1'",u"",u"",u"",u"",u"",u"",u""], 
     u'off': [u"echo 'example stop command for station 1'",u"",u"",u"",u"",u"",u"",u""]  
    }
)


################################################################################
# Main function loop:                                                          #
################################################################################

class Sender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop = Event()

        self.status = {}

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
        if plugin_options['use_control']:  # if plugin is enabled   
           log.clear(NAME)
           log.info(NAME, _('CLI Control is enabled.'))
           
           try:
              zones = signal('zone_change')
              zones.connect(on_zone_change)
              
           except Exception:
              log.error(NAME, _('CLI Control plug-in') + ':\n' + traceback.format_exc())
              pass
                     
        else:
           log.clear(NAME)
           log.info(NAME, _('CLI Control is disabled.'))
         
sender = None

################################################################################
# Helper functions:                                                            #
################################################################################

### start ###
def start():
    global sender
    if sender is None:
        sender = Sender()
 
### stop ###
def stop():
    global sender
    if sender is not None:
       sender.stop()
       sender.join()
       sender = None 

def run_command(cmd):
    """run command"""
    if plugin_options['use_control']:  # if plugin is enabled   
       proc = subprocess.Popen(
          cmd,
          stderr=subprocess.STDOUT, # merge stdout and stderr
          stdout=subprocess.PIPE,
          shell=True)
       output = proc.communicate()[0]
       log.info(NAME, '{0!r}'.format(output)) 

       
def on_zone_change(name, **kw):
    """ Switch relays when core program signals a change in station state."""
    #   command = "wget http://xxx.xxx.xxx.xxx/relay1on"
    log.clear(NAME)
    log.info(NAME, _('Zone change signaled...'))

    for station in stations.get():
       if station.active:
          command = plugin_options['on'] 
          data = command[station.index]
          if data:
             #print 'data:', data
             run_command(data)
       else:
          command = plugin_options['off']
          data = command[station.index]
          if data:
             #print 'data:', data
             run_command(data)
                               
    return       

################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        return self.plugin_render.cli_control(plugin_options, log.events(NAME))

    def POST(self):
        qdict = web.input()
        #print 'qdict: ', qdict
        
        try:
           ### add code to update commands ###
           if 'use_control' in qdict:
              if qdict['use_control']=='on':
                 plugin_options.__setitem__('use_control', True) #__setitem__(self, key, value)

           else:  
              plugin_options.__setitem__('use_control', False) 

           commands = {u'on': [], u'off': []} 

           for i in range(options.output_count):
              commands['on'].append(qdict['con'+str(i)])
              commands['off'].append(qdict['coff'+str(i)])
           #print 'commands: ', commands

           plugin_options.__setitem__('on', commands['on']) 
           plugin_options.__setitem__('off', commands['off'])
           #print 'plugin_options:', plugin_options
           
           if sender is not None:
             sender.update()    
       
        except Exception:
           log.error(NAME, _('CLI Control plug-in') + ':\n' + traceback.format_exc())
     
        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage): 
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)
