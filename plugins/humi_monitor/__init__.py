# this plugins check humidity 

__author__ = 'Martin Pihrt'

import json
import time
import datetime
import sys
import traceback

from threading import Thread, Event

import smbus
import web
from ospy.options import level_adjustments
from ospy.stations import stations
from ospy.options import options
from ospy.log import log, logEM
from plugins import PluginOptions, plugin_url
from ospy.helpers import get_rpi_revision
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string

import i18n


NAME = 'Humidity Monitor'
LINK = 'settings_page'

tank_options = PluginOptions(
    NAME,
    {
       'use_freq_1': False,    # default not use freq sensor 1
       'use_freq_2': False,    # default not use freq sensor 2
       'use_freq_3': False,    # default not use freq sensor 3
       'use_freq_4': False,    # default not use freq sensor 4
       'use_freq_5': False,    # default not use freq sensor 5
       'use_freq_6': False,    # default not use freq sensor 6
       'use_freq_7': False,    # default not use freq sensor 7
       'use_freq_8': False,    # default not use freq sensor 8
       'minimum_freq': 400000, # default freq from sensor for 0% humi
       'maximum_freq': 100000 # default freq from sensor for 100% humi
    }
)

bus = smbus.SMBus(1 if get_rpi_revision() >= 2 else 0)

address_humi = 0x05 # device address for humidity HW board

################################################################################
# Main function loop:                                                          #
################################################################################

class Sender(Thread):
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
        once_text = True
        two_text = True
        send = False
        mini = True
        
        while not self._stop.is_set():
            try:
                
# todo better humidity - change plugin! 
                log.info(NAME, 'Plugin is not ready!!! not use.')
                if tank_options['use_freq_1']:
                    humi1 = get_freq(1)
                    if humi1 >= 0:
                       humi1_lvl = maping(humi1,int(tank_options['minimum_freq']),int(tank_options['maximum_freq']),0,100) 
                       if humi1_lvl >= 100:
                          humi1_lvl = 100 
                       log.info(NAME, datetime_string() + ' F1: ' + str(humi1) + 'Hz H: ' + str(humi1_lvl) + '%.' )
                    else:
                       log.info(NAME, datetime_string() + ' F1: ' + _('Error I2C device not found.'))
                      
                if tank_options['use_freq_2']:
                    humi2 = get_freq(2)
                    if humi2 >= 0:
                       humi2_lvl = maping(humi2,int(tank_options['minimum_freq']),int(tank_options['maximum_freq']),0,100) 
                       if humi2_lvl >= 100:
                          humi2_lvl = 100
                       log.info(NAME, datetime_string() + ' F2: ' + str(humi2) + 'Hz H: ' + str(humi2_lvl) + '%.' )
                    else:
                       log.info(NAME, datetime_string() + ' F2: ' + _('Error I2C device not found.'))
  
                if tank_options['use_freq_3']:
                    humi3 = get_freq(3)
                    if humi3 >= 0:
                       humi3_lvl = maping(humi3,int(tank_options['minimum_freq']),int(tank_options['maximum_freq']),0,100) 
                       if humi3_lvl >= 100:
                          humi3_lvl = 100
                       log.info(NAME, datetime_string() + ' F3: ' + str(humi3) + 'Hz H: ' + str(humi3_lvl) + '%.' )
                    else:
                       log.info(NAME, datetime_string() + ' F3: ' + _('Error I2C device not found.'))

                if tank_options['use_freq_4']:
                    humi4 = get_freq(4)
                    if humi4 >= 0:
                       humi4_lvl = maping(humi4,int(tank_options['minimum_freq']),int(tank_options['maximum_freq']),0,100) 
                       if humi4_lvl >= 100:
                          humi4_lvl = 100
                       log.info(NAME, datetime_string() + ' F4: ' + str(humi4) + 'Hz H: ' + str(humi4_lvl) + '%.' )
                    else:
                       log.info(NAME, datetime_string() + ' F4: ' + _('Error I2C device not found.'))

                if tank_options['use_freq_5']:
                    humi5 = get_freq(5)
                    if humi5 >= 0:
                       humi5_lvl = maping(humi5,int(tank_options['minimum_freq']),int(tank_options['maximum_freq']),0,100) 
                       if humi5_lvl >= 100:
                          humi5_lvl = 100
                       log.info(NAME, datetime_string() + ' F5: ' + str(humi5) + 'Hz H: ' + str(humi5_lvl) + '%.' )
                    else:
                       log.info(NAME, datetime_string() + ' F5: ' + _('Error I2C device not found.'))

                if tank_options['use_freq_6']:
                    humi6 = get_freq(6)
                    if humi6 >= 0:
                       humi6_lvl = maping(humi6,int(tank_options['minimum_freq']),int(tank_options['maximum_freq']),0,100) 
                       if humi6_lvl >= 100:
                          humi6_lvl = 100
                       log.info(NAME, datetime_string() + ' F6: ' + str(humi6) + 'Hz H: ' + str(humi6_lvl) + '%.' )
                    else:
                       log.info(NAME, datetime_string() + ' F6: ' + _('Error I2C device not found.'))

                if tank_options['use_freq_7']:
                    humi7 = get_freq(7)
                    if humi7 >= 0:
                       humi7_lvl = maping(humi7,int(tank_options['minimum_freq']),int(tank_options['maximum_freq']),0,100) 
                       if humi7_lvl >= 100:
                          humi7_lvl = 100
                       log.info(NAME, datetime_string() + ' F7: ' + str(humi7) + 'Hz H: ' + str(humi7_lvl) + '%.' )
                    else:
                       log.info(NAME, datetime_string() + ' F7: ' + _('Error I2C device not found.'))

                if tank_options['use_freq_8']:
                    humi8 = get_freq(8)
                    if humi8 >= 0:
                       humi8_lvl = maping(humi8,int(tank_options['minimum_freq']),int(tank_options['maximum_freq']),0,100) 
                       if humi8_lvl >= 100:
                          humi8_lvl = 100
                       log.info(NAME, datetime_string() + ' F8: ' + str(humi8) + 'Hz H: ' + str(humi8_lvl) + '%.' )
                    else:
                       log.info(NAME, datetime_string() + ' F8: ' + _('Error I2C device not found.'))

        
                self._sleep(10) 
                log.clear(NAME)

            except Exception:
                log.error(NAME, _('Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)


sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global sender
    if sender is None:
        sender = Sender()

def stop():
    global sender
    if sender is not None:
        sender.stop()
        sender.join()
        sender = None
        if NAME in level_adjustments:
           del level_adjustments[NAME]


def try_io(call, tries=10):
    assert tries > 0
    error = None
    result = None

    while tries:
        try:
            result = call()
        except IOError as e:
            error = e
            tries -= 1
        else:
            break

    if not tries:
        raise error

    return result



def get_freq(freq_no):
    try:
        data = [24]
        data = try_io(lambda: bus.read_i2c_block_data(address_humi,24))
        if freq_no == 1:
           f = data[2] + (data[1]<<8) + (data[0]<<16)    # freq 1
           #print  data[2], data[1], data[0]

        elif freq_no == 2:
           f = data[5] + (data[4]<<8) + (data[3]<<16)    # freq 2

        elif freq_no == 3:
           f = data[8] + (data[7]<<8) + (data[6]<<16)    # freq 3

        elif freq_no == 4:
           f = data[11] + (data[10]<<8) + (data[9]<<16)  # freq 4

        elif freq_no == 5:
           f = data[14] + (data[13]<<8) + (data[12]<<16) # freq 5

        elif freq_no == 6:
           f = data[17] + (data[16]<<8) + (data[15]<<16) # freq 6

        elif freq_no == 7:
           f = data[20] + (data[19]<<8) + (data[18]<<16) # freq 7

        elif freq_no == 8:
           f = data[23] + (data[22]<<8) + (data[21]<<16) # freq 8

        else:
           f = -2
        return f  # if channel freq >8 or <1 not exists 

    except:
        return -1 # if I2C device not exists   


def get_humidity(channel): # return humidity 0-100% for channel 1-8
    hum = get_freq(channel)
    if hum < 0:
       return -1 # if I2C device not exists
    else:
       hum_lvl = maping(hum,int(tank_options['minimum_freq']),int(tank_options['maximum_freq']),0,100) 
       if hum_lvl >= 100: # max value
          hum_lvl = 100 
       if hum_lvl <= 0:   # min value
          hum_lvl = 0 
       return hum_lvl



def maping(x, in_min, in_max, out_min, out_max):
    # return value from map. example (x=1023,0,1023,0,100) -> x=1023 return 100
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

 
def get_station_is_on():
        for station in stations.get():
            if station.active:                                              
                return True
            else:
                return False


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        return self.plugin_render.humi_monitor(tank_options, log.events(NAME))

    def POST(self):
        tank_options.web_update(web.input())

        if sender is not None:
            sender.update()
        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(tank_options)

