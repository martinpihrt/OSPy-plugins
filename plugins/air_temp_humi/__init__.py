# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# This plugin read data from probe DHT11 (temp and humi). # Raspberry Pi pin 19 as GPIO 10
# This plugin read data from DS18B20 hw I2C board (temp). # Raspberry Pi I2C pin

import json
import time
from datetime import datetime
import traceback
import os
from threading import Thread, Event

import web

from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import get_rpi_revision
from ospy.helpers import datetime_string
from ospy import helpers
from ospy.stations import stations

import RPi.GPIO as GPIO

# Thank's: https://github.com/szazo/DHT11_Python
import dht11 

instance = dht11.DHT11(pin=19) # DHT on GPIO 10 pin

import i18n

NAME = 'Air Temperature and Humidity Monitor'
LINK = 'settings_page'

tempDS = [-127,-127,-127,-127,-127,-127]
tempDHT = 0
humiDHT = 0


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
     'label_ds0': 'label',  # label for DS1
     'label_ds1': 'label',  # label for DS2
     'label_ds2': 'label',  # label for DS3
     'label_ds3': 'label',  # label for DS4
     'label_ds4': 'label',  # label for DS5
     'label_ds5': 'label',  # label for DS6
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
        self.status['DS0']  = -127
        self.status['DS1']  = -127
        self.status['DS2']  = -127
        self.status['DS3']  = -127
        self.status['DS4']  = -127
        self.status['DS5']  = -127

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
                    log.clear(NAME)
                    log.info(NAME, datetime_string())
                    try:
                
                       result = instance.read()
                       if result.is_valid():
                           Temperature = result.temperature
                           Humidity = result.humidity

                           global tempDHT, humiDHT
                           
                           tempDHT = Temperature
                           humiDHT = Humidity 
                    except:
                       log.clear(NAME)
                       log.info(NAME, datetime_string())
                       log.info(NAME, _('DHT11 data is not valid'))                                     
                      
                    if Humidity and Temperature != 0:
                       self.status['temp'] = Temperature
                       self.status['humi'] = Humidity
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
                       DS18B20_read_data() # get read DS18B20 temperature data to global tempDS[xx]
                        
                       for i in range(0, plugin_options['ds_used']):
                          self.status['DS%d' % i] = tempDS[i]
                          log.info(NAME, _('Temperature') + ' DS' + str(i+1) + ' (' + u'%s' % plugin_options['label_ds%d' % i] + '): ' + u'%.1f \u2103' % self.status['DS%d' % i])   

                    #print DS18B20_read_string_data() # for testing only
                    
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


def DS18B20_read_data():
    import smbus  
    try:
       bus = smbus.SMBus(1 if get_rpi_revision() >= 2 else 0)     
       i2c_data = try_io(lambda: bus.read_i2c_block_data(0x03, 0))

       # Test recieved data byte 1 and 2
       if i2c_data[1] == 255 or i2c_data[2] == 255:         
          log.error(NAME, _('Data is not correct. Please try again later.'))
          return [255,255,255,255,255,255] # data has error 

       # Each float temperature from the hw board is 5 bytes long (5byte * 6 probe = 30 bytes).
       pom = 0
       teplota = [0,0,0,0,0,0]
       for i in range(0, plugin_options['ds_used']):
          priznak=0
          jed=0
          des=0
          sto=0
          tis=0
          soucet=0
          jed = i2c_data[pom+4]        # 4 byte
          des = i2c_data[pom+3]*10     # 3
          sto = i2c_data[pom+2]*100    # 2
          tis = i2c_data[pom+1]*1000   # 1  
          priznak = i2c_data[pom]      # 0 byte
          pom += 5
          soucet = tis+sto+des+jed
          if(priznak==1):
            soucet = soucet * -1      # negation number
          teplota[i]  = soucet/10.0
          tempDS[i] = teplota[i]      # global temperature for all probe DS18B20

    except Exception:
      log.debug(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())       
      time.sleep(0.5)
      pass
      return [255,255,255,255,255,255] # try data has error     
    return teplota     # data is ok


def DS18B20_read_string_data():
    txt = [-127,-127,-127,-127,-127,-127,]
    for i in range(0, plugin_options['ds_used']):
       txt[i] = tempDS[i]
    return str(txt)


def DS18B20_read_probe(probe):
    try:
       return tempDS[probe]
    except:
       return "--"        


def DHT_read_temp_value():
    global tempDHT

    return tempDHT


def DHT_read_humi_value():
    global humiDHT  
    
    return humiDHT        
   

def read_log():
    """Read log data from json file."""

    try:
        with open(os.path.join(plugin_data_dir(), 'log.json')) as logf:
            return json.load(logf)
    except IOError:
        return []


def read_graph_log():
    """Read graph data from json file."""

    try:
        with open(os.path.join(plugin_data_dir(), 'graph.json')) as logf:
            return json.load(logf)
    except IOError:
        return []


def write_log(json_data):
    """Write data to log json file."""

    with open(os.path.join(plugin_data_dir(), 'log.json'), 'w') as outfile:
        json.dump(json_data, outfile)


def write_graph_log(json_data):
    """Write data to graph json file."""

    with open(os.path.join(plugin_data_dir(), 'graph.json'), 'w') as outfile:
        json.dump(json_data, outfile)


def update_log(status):
    """Update data in json files.""" 

    ### Data for log ###
    log_data = read_log()
    data = {'datetime': datetime_string()}
    data['date'] = str(datetime.now().strftime('%d.%m.%Y'))
    data['time'] = str(datetime.now().strftime('%H:%M:%S'))
    data['temp'] = str(status['temp'])
    data['humi'] = str(status['humi'])
    data['outp'] = str(status['outp'])
    if plugin_options['ds_used'] > 0:
      data['ds0']  = str(status['DS0'])
    else:
      data['ds0']  = str('not used')
    if plugin_options['ds_used'] > 1:
      data['ds1']  = str(status['DS1'])
    else:
      data['ds1']  = str('not used')
    if plugin_options['ds_used'] > 2:
      data['ds2']  = str(status['DS2'])
    else:
      data['ds2']  = str('not used')
    if plugin_options['ds_used'] > 3:
      data['ds3']  = str(status['DS3'])
    else:
      data['ds3']  = str('not used')
    if plugin_options['ds_used'] > 4:
      data['ds4']  = str(status['DS4'])
    else:
      data['ds4']  = str('not used')
    if plugin_options['ds_used'] > 5:
      data['ds5']  = str(status['DS5'])
    else:
      data['ds5']  = str('not used')
     
    log_data.insert(0, data)
    if plugin_options['log_records'] > 0:
        log_data = log_data[:plugin_options['log_records']]
    write_log(log_data)

    ### Data for graph log ###
    try:  
        graph_data = read_graph_log()     # example default -> [{"station": "DS1", "balances": {}, {"station": "DS2", "balances": {}},{"station": "DS3", "balances": {}}}]
    except: 
        create_default_graph()
        log.debug(NAME, _('Creating default graph log files OK'))

    timestamp = int(time.time())

    if plugin_options['ds_used'] > 0:      # DS1
        temp0 = graph_data[0]['balances']
        if status['DS0'] != -127:
           DS1 = {'total': status['DS0']}
           temp0.update({timestamp: DS1})
    if plugin_options['ds_used'] > 1:      # DS2
        temp1 = graph_data[1]['balances']
        if status['DS1'] != -127:
           DS2 = {'total': status['DS1']}
           temp1.update({timestamp: DS2})
    if plugin_options['ds_used'] > 2:      # DS3
        temp2 = graph_data[2]['balances']
        if status['DS2'] != -127:
           DS3 = {'total': status['DS2']}
           temp2.update({timestamp: DS3})
    if plugin_options['ds_used'] > 3:      # DS4
        temp3 = graph_data[3]['balances']
        if status['DS3'] != -127:
           DS4 = {'total': status['DS3']}
           temp3.update({timestamp: DS4})
    if plugin_options['ds_used'] > 4:      # DS5
        temp4 = graph_data[4]['balances']
        if status['DS4'] != -127:
           DS5 = {'total': status['DS4']}
           temp4.update({timestamp: DS5})
    if plugin_options['ds_used'] > 5:      # DS6
        temp5 = graph_data[5]['balances']
        if status['DS5'] != -127:
           DS6 = {'total': status['DS5']}
           temp5.update({timestamp: DS6})

    temp6 = graph_data[6]['balances']      # DHT    
    DHT = {'total': status['temp']}
    temp6.update({timestamp: DHT})
     
    write_graph_log(graph_data)

    log.info(NAME, _('Saving to log  files OK'))


def create_default_graph():
    """Create default graph json file."""

    name1 = ""
    name2 = ""
    name3 = ""
    name4 = ""
    name5 = ""
    name6 = ""

    if plugin_options['ds_used'] > 0:
        name1 = plugin_options['label_ds0']
    if plugin_options['ds_used'] > 1:
        name2 = plugin_options['label_ds1']
    if plugin_options['ds_used'] > 2:
        name3 = plugin_options['label_ds2']
    if plugin_options['ds_used'] > 3:
        name4 = plugin_options['label_ds3']
    if plugin_options['ds_used'] > 4:
        name5 = plugin_options['label_ds4']
    if plugin_options['ds_used'] > 5:
        name6 = plugin_options['label_ds5']

    name7 = plugin_options['label']

    graph_data = [
       {"station": name1, "balances": {}},
       {"station": name2, "balances": {}}, 
       {"station": name3, "balances": {}},
       {"station": name4, "balances": {}},
       {"station": name5, "balances": {}},
       {"station": name6, "balances": {}},
       {"station": name7, "balances": {}}
    ]
    write_graph_log(graph_data)



################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments and deleting logs"""

    def GET(self):
        global sender
        qdict = web.input()
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)

        if sender is not None and delete:
           write_log([])
           create_default_graph()
           log.info(NAME, _('Deleted all log files OK'))

           raise web.seeother(plugin_url(settings_page), True)

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


class data_json(ProtectedPage):
    """Returns plugin data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data =  {
          'label': plugin_options['label'],
          'label_ds0': plugin_options['label_ds0'],  
          'label_ds1': plugin_options['label_ds1'], 
          'label_ds2': plugin_options['label_ds2'],
          'label_ds3': plugin_options['label_ds3'],
          'label_ds4': plugin_options['label_ds4'],
          'label_ds5': plugin_options['label_ds5'],
          'temp_ds0':  DS18B20_read_probe(0),
          'temp_ds1':  DS18B20_read_probe(1),
          'temp_ds2':  DS18B20_read_probe(2),
          'temp_ds3':  DS18B20_read_probe(3),
          'temp_ds4':  DS18B20_read_probe(4),
          'temp_ds5':  DS18B20_read_probe(5),
          'temp_dht':  DHT_read_temp_value(),
          'humi_dht':  DHT_read_humi_value()
        }

        return json.dumps(data)


class log_json(ProtectedPage):
    """Returns data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(read_log())


class graph_json(ProtectedPage):
    """Returns graph data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(read_graph_log())


class log_csv(ProtectedPage):  # save log file from web as csv file type
    """Simple Log API"""

    def GET(self):

        name1 = plugin_options['label_ds0']
        name2 = plugin_options['label_ds1']
        name3 = plugin_options['label_ds2']
        name4 = plugin_options['label_ds3']
        name5 = plugin_options['label_ds4']
        name6 = plugin_options['label_ds5']
        
        log_records = read_log()
        data  = "Date/Time"
        data += ";\t Date"
        data += ";\t Time"
        data += ";\t Temperature C"
        data += ";\t Humidity %RH" 
        data += ";\t Output"
        data += ";\t" + name1
        data += ";\t" + name2
        data += ";\t" + name3
        data += ";\t" + name4
        data += ";\t" + name5
        data += ";\t" + name6
        data += '\n'

        for record in log_records:
            data +=         record['datetime']
            data += ";\t" + record['date']
            data += ";\t" + record['time']
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
