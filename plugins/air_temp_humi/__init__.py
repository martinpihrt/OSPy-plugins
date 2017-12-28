#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# This plugin read data from probe DHT11 (temp and humi). # Raspberry Pi pin 19 as GPIO 10
# This plugin read data from DS18B20 hw I2C board (temp). # Raspberry Pi I2C pin

import json
import time
import traceback
import os
from threading import Thread, Event

import web

from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import get_rpi_revision
from ospy.helpers import datetime_string
from ospy.stations import stations

import RPi.GPIO as GPIO

import i18n

NAME = 'Air Temperature and Humidity Monitor'
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {'enabled': False,
     'enable_log': False,
     'log_interval': 1,
     'log_records': 0,
     'label': 'Air Probe',
     'enabled_reg': False,
     'hysteresis': 5,       # %rv hysteresis 5 is +-2,5
     'humidity_on': 60,     # %rv for on
     'humidity_off': 50,    # %rv for off
     'control_output': 9,   # station 10 if exist else station 1
     'ds_enabled': False,   # enable DS18B20 I2C support
     'ds_used': 1           # count DS18b20, default 1x max 6x
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
        self.status['temp'] = 0
        self.status['humi'] = 0
        self.status['outp'] = 0
        self.status['DS0']  = 0
        self.status['DS1']  = 0
        self.status['DS2']  = 0
        self.status['DS3']  = 0
        self.status['DS4']  = 0
        self.status['DS5']  = 0

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
        Temperature = 0
        Humidity = 0  

        last_millis = 0 # timer for save log
        var1 = True     # Auxiliary variable for once on
        var2 = True     # Auxiliary variable for once off

        while not self._stop.is_set():
            try:
                if plugin_options['enabled']:  # if plugin is enabled   
                    try:
                       Temperature, Humidity = DHT11_read_data()
                    except:
                       self._sleep(0.3)                                     
                      
                    if Humidity and Temperature != 0:
                       log.clear(NAME)
                       self.status['temp'] = Temperature
                       self.status['humi'] = Humidity
                       log.info(NAME, datetime_string())
                       log.info(NAME, _('Temperature') + ' DHT: ' + u'%.1f \u2103' % Temperature)
                       log.info(NAME, _('Humidity') + ' DHT: ' + u'%.1f' % Humidity + ' %RH')
                       if plugin_options['enabled_reg']:
                          OT = _('ON') if self.status['outp'] is 1 else _('OFF') 
                          log.info(NAME, _('Output') + ': ' + u'%s' % OT)

                       if plugin_options['enable_log']:
                          millis = int(round(time.time() * 1000))
                          interval = (plugin_options['log_interval'] * 60000)
                          if (millis - last_millis) > interval:
                             last_millis = millis
                             update_log(self.status)

                       station = stations.get(plugin_options['control_output'])

                       if plugin_options['enabled_reg']:  # if regulation is enabled
                          if Humidity > (plugin_options['humidity_on'] + plugin_options['hysteresis']/2) and var1 is True:  
                             station.active = True
                             var1 = False
                             var2 = True
                             self.status['outp'] = 1
                             log.debug(NAME, _('Station output was turned on.'))
                             update_log(self.status)
                             
                          if Humidity < (plugin_options['humidity_off'] - plugin_options['hysteresis']/2) and var2 is True:  
                             station.active = False
                             var1 = True
                             var2 = False 
                             self.status['outp'] = 0
                             log.debug(NAME, _('Station output was turned off.'))
                             update_log(self.status)    

                       # Activate again if needed:
                       if station.remaining_seconds != 0:
                          station.active = True

 
                    if plugin_options['ds_enabled']:  # if in plugin is enabled DS18B20
                       try:
                          import smbus  
                          import struct

                          bus = smbus.SMBus(1 if get_rpi_revision() >= 2 else 0)  

                          temp_data = bus.read_i2c_block_data(0x03, 0)
                          #log.info(NAME, _('Data: ') + str(temp_data))

                          # Each float from the hw board is 5 bytes long.
                          pom=0
                          for i in range(0, plugin_options['ds_used']):
                            priznak=0
                            jed=0
                            des=0
                            sto=0
                            tis=0
                            soucet=0
                            jed = temp_data[pom+4]        # 4 byte
                            des = temp_data[pom+3]*10     # 3
                            sto = temp_data[pom+2]*100    # 2
                            tis = temp_data[pom+1]*1000   # 1  
                            priznak = temp_data[pom]      # 0 byte

                            pom += 5

                            soucet = tis+sto+des+jed

                            if(soucet > 1270):
                               priznak=255 # error value not printing
                        
                            if(priznak==1):
                               soucet = soucet * -1  # negation number

                            teplota = soucet/10.0

                            if(priznak!=255):
                               self.status['DS%d' % i] = teplota
                               log.info(NAME, _('Temperature') + ' DS' + str(i) + ': ' + str(teplota))
                            else:
                               self.status['DS%d' % i] = -127
                               log.info(NAME, _('Temperature') + ' DS' + str(i) + ': err')

                       except Exception:
                          log.error(NAME, '\n' + _('Can not read data from I2C bus.') + ':\n' + traceback.format_exc())
                          pass
                       
                    self._sleep(5)

            except Exception:
                log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
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

def bin2dec(string_num):
    return str(int(string_num, 2))

def DHT11_read_data():
    data = []        
   
    GPIO.setup(19,GPIO.OUT) # pin 19 GPIO10
    GPIO.output(19,True)
    time.sleep(0.025)
    GPIO.output(19,False)
    time.sleep(0.02)
    GPIO.setup(19, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    for i in range(0,500):
       data.append(GPIO.input(19))
 
    bit_count = 0
    tmp = 0
    count = 0
    HumidityBit = ""
    TemperatureBit = ""
    crc = ""

    try:
        while data[count] == 1:
          tmp = 1
          count = count + 1

        for i in range(0, 32):
          bit_count = 0

          while data[count] == 0:
             tmp = 1
             count = count + 1
          
          while data[count] == 1:
             bit_count = bit_count + 1
             count = count + 1 

          if bit_count > 3:
             if i>=0 and i<8:
                HumidityBit = HumidityBit + "1"
             if i>=16 and i<24:
                TemperatureBit = TemperatureBit + "1"
          else:
             if i>=0 and i<8:
                HumidityBit = HumidityBit + "0"
             if i>=16 and i<24:
                TemperatureBit = TemperatureBit + "0"
   
        for i in range(0,8):
          bit_count = 0

          while data[count] == 0: 
              tmp = 1
              count = count + 1

          while data[count] == 1:
              bit_count = bit_count + 1
              count = count + 1

          if bit_count > 3:
              crc = crc + "1"
          else:
              crc = crc + "0"

          Humidity = bin2dec(HumidityBit)
          Temperature = bin2dec(TemperatureBit)

          if int(Humidity) + int(Temperature) - int(bin2dec(crc)) == 0:
             return int(Temperature),int(Humidity)              
    except:
       pass
       time.sleep(0.5)
            
   
def read_log():
    """Read log from json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'log.json')) as logf:
            return json.load(logf)
    except IOError:
        return []


def write_log(json_data):
    """Write json to log file."""
    with open(os.path.join(plugin_data_dir(), 'log.json'), 'w') as outfile:
        json.dump(json_data, outfile)


def update_log(status):
    log_data = read_log()
    data = {'datetime': datetime_string()}
    data['temp'] = str(status['temp'])
    data['humi'] = str(status['humi'])
    data['outp'] = str(status['outp'])
    data['ds0']  = str(status['DS0'])
    data['ds1']  = str(status['DS1'])
    data['ds2']  = str(status['DS2'])
    data['ds3']  = str(status['DS3'])
    data['ds4']  = str(status['DS4'])
    data['ds5']  = str(status['DS5'])
     
    log_data.insert(0, data)
    if plugin_options['log_records'] > 0:
        log_data = log_data[:plugin_options['log_records']]
    write_log(log_data)
    log.info(NAME, _('Saving log to file.'))



################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        return self.plugin_render.air_temp_humi(plugin_options, log.events(NAME))

    def POST(self):
        plugin_options.web_update(web.input())

        if sender is not None:
            sender.update()                
        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)


class log_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(read_log())


class log_csv(ProtectedPage):  # save log file from web as csv file type
    """Simple Log API"""

    def GET(self):
        log_records = read_log()
        data = "Date/Time"
        data += ";\t Temperature C"
        data += ";\t Humidity %RH" 
        data += ";\t Output"
        data += ";\t DS0 Temperature C"
        data += ";\t DS1 Temperature C"
        data += ";\t DS2 Temperature C"
        data += ";\t DS3 Temperature C"
        data += ";\t DS4 Temperature C"
        data += ";\t DS5 Temperature C"
        data += '\n'

        for record in log_records:
            data += record['datetime']
            data += ";\t" + record["temp"]
            data += ";\t" + record["humi"]
            data += ";\t" + record["outp"]
            data += ";\t" + record["ds0"]
            data += ";\t" + record["ds1"]
            data += ";\t" + record["ds2"]
            data += ";\t" + record["ds3"]
            data += ";\t" + record["ds4"]
            data += ";\t" + record["ds5"]
            data += '\n'

        web.header('Content-Type', 'text/csv')
        return data


class delete_log_page(ProtectedPage):  # delete log file from web
    """Delete all log_records"""

    def GET(self):
        write_log([])
        log.info(NAME, _('Deleted log file'))
        raise web.seeother(plugin_url(settings_page), True)


