# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# This plugin read data from probe DHT11 (22) (temp and humi). # Raspberry Pi pin 19 as GPIO 10
# This plugin read data from DS18B20 hw I2C board (temp). # Raspberry Pi I2C pin
# Only for Python 3+

import json
import time
import datetime
import traceback
import os
from threading import Thread, Event
from contextlib import contextmanager

import web

from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import get_rpi_revision, datetime_string
from ospy import helpers
from ospy.stations import stations

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer
#from ospy.webpages import showOnTimeline # Enable plugin to display station data on timeline

from blinker import signal

import RPi.GPIO as GPIO

# Thank's: https://github.com/szazo/DHT11_Python
from . import dht11
from . import dht22 

instance = dht11.DHT11(pin=19)   # DHT on GPIO 10 pin
instance22 = dht22.DHT22(pin=19) # DHT on GPIO 10 pin

NAME = 'Air Temperature and Humidity Monitor'
MENU =  _('Package: Air Temperature and Humidity Monitor')
LINK = 'settings_page'

tempDS = [-127,-127,-127,-127,-127,-127]
tempDHT = 0
humiDHT = 0
DS18B20_ERROR_VALUE = -127
DS18B20_READ_RETRIES = 6
DS18B20_RETRY_DELAY = 0.4
DS18B20_I2C_LOCK_TIMEOUT = 5.0
DS18B20_I2C_SETTLE_TIME = 0.05
DS18B20_LAST_VALID = [None, None, None, None, None, None]
DS18B20_LAST_VALID_TS = [0, 0, 0, 0, 0, 0]

try:
    from plugins.i2c_guard import i2c_transaction
except Exception:
    _LOCAL_I2C_LOCK = None

    @contextmanager
    def i2c_transaction(timeout=5.0, settle_time=0.05):
        global _LOCAL_I2C_LOCK
        if _LOCAL_I2C_LOCK is None:
            from threading import Lock
            _LOCAL_I2C_LOCK = Lock()

        start = time.time()
        acquired = False
        while not acquired:
            acquired = _LOCAL_I2C_LOCK.acquire(False)
            if acquired:
                break
            if time.time() - start >= timeout:
                raise IOError('I2C bus is busy.')
            time.sleep(0.05)

        try:
            if settle_time > 0:
                time.sleep(settle_time)
            yield
        finally:
            _LOCAL_I2C_LOCK.release()

plugin_options = PluginOptions(
    NAME,
    {'enabled': False,
     'enable_log': False,
     'log_interval': 1,
     'log_records': 0,
     'enable_dht': False,
     'dht_type': 0,
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
     'ds0_enabled': False,  # use DS1 in UI, logs and graph
     'ds1_enabled': False,  # use DS2 in UI, logs and graph
     'ds2_enabled': False,  # use DS3 in UI, logs and graph
     'ds3_enabled': False,  # use DS4 in UI, logs and graph
     'ds4_enabled': False,  # use DS5 in UI, logs and graph
     'ds5_enabled': False,  # use DS6 in UI, logs and graph
     'ds_used': 0,          # count DS18b20, default 0 max 6x
     'reg_mm': 60,          # min for maximal runtime
     'reg_ss': 0,           # sec for maximal runtime
     'use_footer': True,    # show in footer on home page
     'en_sql_log': False,   # logging temperature to sql database
     'type_log': 0,         # 0 = show log and graph from local log file, 1 = from database
     'show_err': 0,         # 0 = disable show error values in graph ex: -127 C
     'ds_error_timeout': 300, # seconds to keep last valid DS18B20 value before showing error
     'dt_from' : '2024-01-01T00:00',        # for graph history (from date time ex: 2024-02-01T6:00)
     'dt_to' : '2024-01-01T00:00',          # for graph history (to date time ex: 2024-03-17T12:00)
     }
)


def normalize_ds_options(migrate_legacy=True):
    """Keep old ds_used compatible while new DS checkboxes drive the UI."""
    active = []

    if migrate_legacy and plugin_options['ds_enabled'] and plugin_options['ds_used'] > 0:
        for i in range(0, 6):
            if plugin_options['ds%d_enabled' % i]:
                active.append(i)
        if not active:
            for i in range(0, min(plugin_options['ds_used'], 6)):
                plugin_options.__setitem__('ds%d_enabled' % i, True)

    active = []
    for i in range(0, 6):
        if plugin_options['ds_enabled'] and plugin_options['ds%d_enabled' % i]:
            active.append(i)

    ds_used = active[-1] + 1 if active else 0
    if plugin_options['ds_used'] != ds_used:
        plugin_options.__setitem__('ds_used', ds_used)

    return active


def DS18B20_is_enabled(probe):
    try:
        return plugin_options['ds_enabled'] and plugin_options['ds%d_enabled' % probe]
    except:
        return False


def DS18B20_active_indexes():
    return normalize_ds_options(migrate_legacy=False)


def DS18B20_graph_name(probe):
    if DS18B20_is_enabled(probe):
        return plugin_options['label_ds%d' % probe]
    return ''


normalize_ds_options()


################################################################################
# Main function loop:                                                          #
################################################################################


class Sender(Thread):

    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()

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
        self._stop_event.set()

    def update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def run(self):
        Temperature = 0
        Humidity = 0

        last_millis = 0 # timer for save log
        var1 = True     # Auxiliary variable for once on
        var2 = True     # Auxiliary variable for once off

        air_temp = None

        if plugin_options['use_footer']:
            air_temp = showInFooter() #  instantiate class to enable data in footer
            air_temp.button = "air_temp_humi/settings"   # button redirect on footer
            air_temp.label =  _('Temperature')           # label on footer

        regulation_text = ''

        #flow = showOnTimeline()  #  instantiate class to enable data display
        #flow.unit = _(u'Liters')
        #flow.val = 10
        #flow.clear

        while not self._stop_event.is_set():
            try:
                if plugin_options['enabled']:        # if plugin is enabled   
                    log.clear(NAME)
                    log.info(NAME, datetime_string())
                    tempText = ""

                    if plugin_options['enable_dht']: # if DHTxx probe is enabled
                      try:
                        result = 1                        # 1=ERR_MISSING_DATA
                        if plugin_options['dht_type']==0: # DHT11
                          result = instance.read()
                        if plugin_options['dht_type']==1: # DHT22
                          result = instance22.read()

                        if result.is_valid():             # 0=ERR_NO_ERROR, 1=ERR_MISSING_DATA, 2=ERR_CRC 
                          Temperature = result.temperature
                          Humidity = result.humidity

                          global tempDHT, humiDHT

                          tempDHT = Temperature
                          humiDHT = Humidity

                      except:
                        log.clear(NAME)
                        log.info(NAME, datetime_string())
                        if plugin_options['dht_type']==0: # DHT11
                          log.debug(NAME, _('DHT11 data is not valid'))
                          tempText += ' ' + _('DHT11 data is not valid')
                        if plugin_options['dht_type']==1: # DHT22
                          log.debug(NAME, _('DHT22 data is not valid'))
                          tempText += ' ' + _('DHT22 data is not valid')

                      if Humidity and Temperature != 0:
                        self.status['temp'] = Temperature
                        self.status['humi'] = Humidity
                        log.debug(NAME, _('Temperature') + ' ' + _('DHT') + ': ' + '%.1f \u2103' % Temperature)
                        log.debug(NAME, _('Humidity') + ' ' + _('DHT') + ': ' + '%.1f' % Humidity + ' %RH')
                        tempText += ' ' +  _('DHT') + ': ' + '%.1f \u2103' % Temperature + ' ' + '%.1f' % Humidity + ' %RH' + ' '

                        if plugin_options['enabled_reg']:
                            log.info(NAME, regulation_text)

                        station = stations.get(plugin_options['control_output'])

                        if plugin_options['enabled_reg']:  # if regulation is enabled
                          if Humidity > (plugin_options['humidity_on'] + plugin_options['hysteresis']/2) and var1 is True:
                            start = datetime.datetime.now()
                            sid = station.index
                            end = datetime.datetime.now() + datetime.timedelta(seconds=plugin_options['reg_ss'], minutes=plugin_options['reg_mm'])
                            new_schedule = {
                              'active': True,
                              'program': -1,
                              'station': sid,
                              'program_name': _('Air Temperature'),
                              'fixed': True,
                              'cut_off': 0,
                              'manual': True,
                              'blocked': False,
                              'start': start,
                              'original_start': start,
                              'end': end,
                              'uid': '%s-%s-%d' % (str(start), "Manual", sid),
                              'usage': stations.get(sid).usage
                            }

                            log.start_run(new_schedule)
                            stations.activate(new_schedule['station'])
                            var1 = False
                            var2 = True
                            self.status['outp'] = 1
                            regulation_text = datetime_string() + ' ' + _('Regulation set ON.') + ' ' + ' (' + _('Output') + ' ' +  str(station.index+1) + ').'
                            update_log(self.status)

                          if Humidity < (plugin_options['humidity_off'] - plugin_options['hysteresis']/2) and var2 is True:
                            sid = station.index
                            stations.deactivate(sid)
                            active = log.active_runs()
                            for interval in active:
                              if interval['station'] == sid:
                                log.finish_run(interval)
                            var1 = True
                            var2 = False
                            self.status['outp'] = 0
                            regulation_text = datetime_string() + ' ' + _('Regulation set OFF.') + ' ' + ' (' + _('Output') + ' ' +  str(station.index+1) + ').'
                            update_log(self.status)

                    if plugin_options['ds_enabled']:  # if in plugin is enabled DS18B20
                       DS18B20_read_data()            # get read DS18B20 temperature data to global tempDS[xx]
                       active_ds = DS18B20_active_indexes()
                       if active_ds:
                          tempText +=  _('DS') + ': '
                       for i in active_ds:
                          self.status['DS%d' % i] = tempDS[i]
                          log.debug(NAME, _('Temperature') + ' ' + _('DS') + str(i+1) + ' (' + '%s' % plugin_options['label_ds%d' % i] + '): ' + '%.1f \u2103' % self.status['DS%d' % i])   
                          tempText += ' %s' % plugin_options['label_ds%d' % i] + ' %.1f \u2103' % self.status['DS%d' % i]

                    if plugin_options['enabled_reg']:
                       tempText += ' ' + regulation_text

                    if plugin_options['use_footer']:
                        if air_temp is not None:
                            air_temp.val = tempText.encode('utf8').decode('utf8')    # value on footer

                    if plugin_options['enable_log'] or plugin_options['en_sql_log']:  # enabled logging
                          millis = int(round(time.time() * 1000))
                          interval = (plugin_options['log_interval'] * 60000)
                          if (millis - last_millis) > interval:
                             last_millis = millis
                             update_log(self.status)

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
       sender.join(15)
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
            time.sleep(1) #wait here to avoid 121 IO Error
        else:
            break

    if not tries:
        raise error

    return result


def DS18B20_decode_i2c_data(i2c_data):
    if len(i2c_data) < 30:
       raise ValueError('Incomplete DS18B20 I2C data.')

    # Test received data byte 1 and 2.
    if i2c_data[1] == 255 or i2c_data[2] == 255:
       return None

    # Each float temperature from the hw board is 5 bytes long (5byte * 6 probe = 30 bytes).
    pom = 0
    teplota = [DS18B20_ERROR_VALUE, DS18B20_ERROR_VALUE, DS18B20_ERROR_VALUE, DS18B20_ERROR_VALUE, DS18B20_ERROR_VALUE, DS18B20_ERROR_VALUE]
    for i in range(0, 6):
       jed = i2c_data[pom+4]        # 4 byte
       des = i2c_data[pom+3]*10     # 3
       sto = i2c_data[pom+2]*100    # 2
       tis = i2c_data[pom+1]*1000   # 1
       priznak = i2c_data[pom]      # 0 byte
       pom += 5
       soucet = tis+sto+des+jed
       if priznak == 1:
          soucet = soucet * -1      # negation number
       teplota[i] = soucet/10.0
       if teplota[i] > 127:
          teplota[i] = DS18B20_ERROR_VALUE
    return teplota


def DS18B20_has_error(teplota):
    active_ds = DS18B20_active_indexes()
    check_indexes = active_ds if active_ds else range(0, 6)
    for i in check_indexes:
       if teplota[i] == DS18B20_ERROR_VALUE:
          return True
    return False


def DS18B20_error_timeout():
    try:
       return max(0, int(plugin_options['ds_error_timeout']))
    except:
       return 300


def DS18B20_value_is_valid(value):
    return value is not None and value != DS18B20_ERROR_VALUE


def DS18B20_store_valid_values(teplota):
    now = time.time()
    for i in range(0, 6):
       if DS18B20_value_is_valid(teplota[i]):
          DS18B20_LAST_VALID[i] = teplota[i]
          DS18B20_LAST_VALID_TS[i] = now


def DS18B20_apply_reading(teplota):
    now = time.time()
    timeout = DS18B20_error_timeout()
    active_ds = DS18B20_active_indexes()
    check_indexes = active_ds if active_ds else range(0, 6)
    result = [DS18B20_ERROR_VALUE, DS18B20_ERROR_VALUE, DS18B20_ERROR_VALUE, DS18B20_ERROR_VALUE, DS18B20_ERROR_VALUE, DS18B20_ERROR_VALUE]

    if teplota is not None:
       DS18B20_store_valid_values(teplota)

    for i in range(0, 6):
       if teplota is not None and DS18B20_value_is_valid(teplota[i]):
          result[i] = teplota[i]
       elif DS18B20_LAST_VALID[i] is not None and (timeout == 0 or now - DS18B20_LAST_VALID_TS[i] <= timeout):
          result[i] = DS18B20_LAST_VALID[i]

    for i in range(0, 6):
       tempDS[i] = result[i]

    for i in check_indexes:
       if result[i] == DS18B20_ERROR_VALUE:
          return False
    return True


def DS18B20_read_data():
    import smbus
    best_read = None
    try:
       bus = smbus.SMBus(1 if get_rpi_revision() >= 2 else 0)

       for attempt in range(0, DS18B20_READ_RETRIES):
          try:
             with i2c_transaction(timeout=DS18B20_I2C_LOCK_TIMEOUT, settle_time=DS18B20_I2C_SETTLE_TIME):
                i2c_data = try_io(lambda: bus.read_i2c_block_data(0x03, 0), tries=3)
             teplota = DS18B20_decode_i2c_data(i2c_data)
          except Exception:
             teplota = None

          if teplota is None:
             log.debug(NAME, _('Data is not correct. Please try again later.'))
          else:
             if best_read is None or not DS18B20_has_error(teplota):
                best_read = teplota
             if not DS18B20_has_error(teplota):
                DS18B20_apply_reading(teplota)
                return teplota                 # data is ok
             log.debug(NAME, _('DS18B20 returned error value. Reading again.'))

          if attempt < DS18B20_READ_RETRIES - 1:
             time.sleep(DS18B20_RETRY_DELAY)

       DS18B20_apply_reading(best_read)
       return tempDS

    except Exception:
      log.debug(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
      time.sleep(0.5)
      DS18B20_apply_reading(None)
      return tempDS # try data has error


def DS18B20_read_string_data():
    txt = [-127,-127,-127,-127,-127,-127,]
    for i in range(0, 6):
       txt[i] = tempDS[i]
    return str(txt)


def DS18B20_read_probe(probe):
    try:
       return tempDS[probe]
    except:
       return -127


def DHT_read_temp_value():
    global tempDHT
    return tempDHT


def DHT_read_humi_value():
    global humiDHT
    return humiDHT
   

def read_log():
    """Read log data from json file."""
    data = []

    try:
        with open(os.path.join(plugin_data_dir(), 'log.json')) as logf:
            data = json.load(logf)
    except:
        log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
        pass
    
    return data


def read_sql_log():
    """Read log data from database file."""
    data = None

    try:
        from plugins.database_connector import execute_db
        sql = "SELECT * FROM airtemp ORDER BY id DESC"
        data = execute_db(sql, test=False, commit=False, fetch=True) # fetch=true return data from table in format: id,datetime,ds1,ds2,ds3,ds4,ds5,ds6,dhttemp,dhthumi,dhtstate
    except:
        log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
        pass

    return data


def read_graph_log():
    """Read graph data from local json file."""
    data = []

    try:
        with open(os.path.join(plugin_data_dir(), 'graph.json')) as logf:
            data = json.load(logf)
    except:
        pass
    
    return data


def read_graph_sql_log():
    """Read graph data from database file and convert it to json balance file."""
    data = []

    try:
        sql_data = read_sql_log()

        name1 = DS18B20_graph_name(0)
        name2 = DS18B20_graph_name(1)
        name3 = DS18B20_graph_name(2)
        name4 = DS18B20_graph_name(3)
        name5 = DS18B20_graph_name(4)
        name6 = DS18B20_graph_name(5)
        name7 = ""
        name8 = ""

        if plugin_options['enable_dht']:
            name7 = plugin_options['label'] + ' &deg;C'
            name8 = plugin_options['label'] + ' %'

        graph_data = [
            {"station": name1, "balances": {}}, # ds0
            {"station": name2, "balances": {}}, # ds1
            {"station": name3, "balances": {}}, # ds2
            {"station": name4, "balances": {}}, # ds3
            {"station": name5, "balances": {}}, # ds4
            {"station": name6, "balances": {}}, # ds5
            {"station": name7, "balances": {}}, # dht temp
            {"station": name8, "balances": {}}  # dht humi
        ]

        if sql_data is not None:
            for row in sql_data:
                # row[0] is ID, row[1] is datetime, row[2] is ds1 ...
                epoch = int(datetime.datetime.timestamp(row[1]))
            
                temp0 = graph_data[0]['balances']
                DS1 = {'total': float(row[2])}
                temp0.update({epoch: DS1})
            
                temp1 = graph_data[1]['balances']
                DS2 = {'total': float(row[3])}
                temp1.update({epoch: DS2})
            
                temp2 = graph_data[2]['balances']
                DS3 = {'total': float(row[4])}
                temp2.update({epoch: DS3})
            
                temp3 = graph_data[3]['balances']
                DS4 = {'total': float(row[5])}
                temp3.update({epoch: DS4})
            
                temp4 = graph_data[4]['balances']
                DS5 = {'total': float(row[6])}
                temp4.update({epoch: DS5})
            
                temp5 = graph_data[5]['balances']
                DS6 = {'total': float(row[7])}
                temp5.update({epoch: DS6})
            
                if plugin_options['enable_dht']:
                    temp6 = graph_data[6]['balances']
                    DH1 = {'total': float(row[8])}
                    temp6.update({epoch: DH1})

                    temp7 = graph_data[7]['balances']
                    DH2 = {'total': float(row[9])}
                    temp7.update({epoch: DH2})

        data = graph_data

    except:
        log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
        pass

    return data


def write_log(json_data):
    """Write data to log json file."""

    try:
        with open(os.path.join(plugin_data_dir(), 'log.json'), 'w') as outfile:
            json.dump(json_data, outfile)
    except:
        log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
        pass


def write_graph_log(json_data):
    """Write data to graph json file."""

    try:
        with open(os.path.join(plugin_data_dir(), 'graph.json'), 'w') as outfile:
            json.dump(json_data, outfile)
    except:
        log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
        pass


def update_log(status):
    """Update data in json files."""

    if plugin_options['enable_log']:
        ### Data for log ###
        try:
            log_data = read_log()
        except:
            write_log([])
            log_data = read_log()

        from datetime import datetime

        data = {'datetime': datetime_string()}
        data['date'] = str(datetime.now().strftime('%d.%m.%Y'))
        data['time'] = str(datetime.now().strftime('%H:%M:%S'))
        if plugin_options['enable_dht']:
            data['temp'] = str(status['temp'])
            data['humi'] = str(status['humi'])
            data['outp'] = str(status['outp'])
        else:
            data['temp'] = _('Not used')
            data['humi'] = _('Not used')
            data['outp'] = _('Not used')

        for i in range(0, 6):
            if DS18B20_is_enabled(i):
                data['ds%d' % i] = str(status['DS%d' % i])
            else:
                data['ds%d' % i] = _('Not used')

        log_data.insert(0, data)
        if plugin_options['log_records'] > 0:
            log_data = log_data[:plugin_options['log_records']]
        write_log(log_data)

        ### Data for graph log ###
        try:
            graph_data = read_graph_log()     # example default -> [{"station": "DS1", "balances": {}, {"station": "DS2", "balances": {}},{"station": "DS3", "balances": {}}}]
        except: 
            create_default_graph()
            graph_data = read_graph_log()
            log.debug(NAME, _('Creating default graph log files OK'))

        timestamp = int(time.time())

        try:
            for i in DS18B20_active_indexes():
                temp = graph_data[i]['balances']
                DS = {'total': status['DS%d' % i]}
                temp.update({timestamp: DS})

            if plugin_options['enable_dht']:
                temp6 = graph_data[6]['balances']  # DHT temp
                DHT = {'total': status['temp']}
                temp6.update({timestamp: DHT})
                try:
                    temp7 = graph_data[7]['balances']  # DHT humi
                    DHT2 = {'total': status['humi']}
                    temp7.update({timestamp: DHT2})
                except:
                    pass
            write_graph_log(graph_data)
            log.info(NAME, _('Saving to log files.'))
    
        except:
            create_default_graph()

    if plugin_options['en_sql_log']:
        try:
            from plugins.database_connector import execute_db
            # first create table airtemp if not exists
            sql = "CREATE TABLE IF NOT EXISTS airtemp (id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP, ds1 VARCHAR(7), ds2 VARCHAR(7), ds3 VARCHAR(7), ds4 VARCHAR(7), ds5 VARCHAR(7), ds6 VARCHAR(7), dht1 VARCHAR(7), dht2 VARCHAR(7), dht3 VARCHAR(2))"
            execute_db(sql, test=False, commit=False) # not commit
            # next insert data to table airtemp
            sql = "INSERT INTO `airtemp` (`ds1`, `ds2`, `ds3`, `ds4`, `ds5`, `ds6`, `dht1`, `dht2`, `dht3`) VALUES ('%s','%s','%s','%s','%s','%s','%s','%s','%s')" % (status['DS0'],status['DS1'],status['DS2'],status['DS3'],status['DS4'],status['DS5'],status['temp'],status['humi'],status['outp'])
            execute_db(sql, test=False, commit=True)  # yes commit inserted data
            log.info(NAME, _('Saving to SQL database.'))
        except:
            log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
            pass

def create_default_graph():
    """Create default graph json file."""

    name1 = DS18B20_graph_name(0)
    name2 = DS18B20_graph_name(1)
    name3 = DS18B20_graph_name(2)
    name4 = DS18B20_graph_name(3)
    name5 = DS18B20_graph_name(4)
    name6 = DS18B20_graph_name(5)
    name7 = ""
    name8 = ""

    if plugin_options['enable_dht']:
        name7 = plugin_options['label'] + ' &deg;C'
        name8 = plugin_options['label'] + ' %'

    graph_data = [
       {"station": name1, "balances": {}},
       {"station": name2, "balances": {}}, 
       {"station": name3, "balances": {}},
       {"station": name4, "balances": {}},
       {"station": name5, "balances": {}},
       {"station": name6, "balances": {}},
       {"station": name7, "balances": {}},
       {"station": name8, "balances": {}}
    ]
    write_graph_log(graph_data)



################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments and deleting logs"""

    def GET(self):
        try:
            global sender
            normalize_ds_options()
            qdict = web.input()
            show = helpers.get_input(qdict, 'show', False, lambda x: True)
            delSQL = helpers.get_input(qdict, 'delSQL', False, lambda x: True)
            delfilter = helpers.get_input(qdict, 'delfilter', False, lambda x: True)

            if sender is not None and 'dt_from' in qdict and 'dt_to' in qdict:
                dt_from = qdict['dt_from']
                dt_to = qdict['dt_to']
                plugin_options.__setitem__('dt_from', dt_from) #__setitem__(self, key, value)
                plugin_options.__setitem__('dt_to', dt_to)     #__setitem__(self, key, value)
                if 'show_err' in qdict:
                    plugin_options.__setitem__('show_err', True)
                else:
                    plugin_options.__setitem__('show_err', False)

            if sender is not None and delfilter:
                from datetime import datetime, timedelta
                dt_now = (datetime.today() + timedelta(days=1)).date()
                plugin_options.__setitem__('dt_from', "2020-01-01T00:00")
                plugin_options.__setitem__('dt_to', "{}T00:00".format(dt_now))

            if sender is not None and show:
                raise web.seeother(plugin_url(log_page), True)

            if sender is not None and delSQL:
                try:
                    from plugins.database_connector import execute_db
                    sql = "DROP TABLE IF EXISTS `airtemp`"
                    execute_db(sql, test=False, commit=False)  
                    log.info(NAME, _('Deleting the airtemp table from the database.'))
                except:
                    log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
                    pass

            return self.plugin_render.air_temp_humi(plugin_options, log.events(NAME))
        except:
            log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('air_temp_humi -> settings_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            plugin_options.web_update(web.input())
            normalize_ds_options(migrate_legacy=False)

            updateSignal = signal('hass_plugin_update')
            updateSignal.send()
            updateSignal = signal('air_temp_humi_plugin_update')
            updateSignal.send()
            if sender is not None:
                sender.update()
            raise web.seeother(plugin_url(settings_page), True)
        except:
            log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('air_temp_humi -> settings_page POST')
            return self.core_render.notice('/', msg)

class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            return self.plugin_render.air_temp_humi_help()
        except:
            log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('air_temp_humi -> help_page GET')
            return self.core_render.notice('/', msg)

class log_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            global sender
            qdict = web.input()
            delete = helpers.get_input(qdict, 'delete', False, lambda x: True)
            delSQL = helpers.get_input(qdict, 'delSQL', False, lambda x: True)
        
            if sender is not None and delete and plugin_options['enable_log']:
                write_log([])
                create_default_graph()
                log.info(NAME, _('Deleted all log files OK'))

            if sender is not None and delSQL and plugin_options['en_sql_log']:
                try:
                    from plugins.database_connector import execute_db
                    sql = "DROP TABLE IF EXISTS `airtemp`"
                    execute_db(sql, test=False, commit=False)  
                    log.info(NAME, _('Deleting the airtemp table from the database.'))
                except:
                    log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
                    pass          

            return self.plugin_render.air_temp_humi_log(read_log(), read_sql_log(), plugin_options)

        except:
            log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('air_temp_humi -> log_page GET')
            return self.core_render.notice('/', msg)

class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(plugin_options)
        except:
            return {}


class data_json(ProtectedPage):
    """Returns plugin data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data = {}
        try:
            data =  {
            'enabled': plugin_options['enabled'],
            'enable_dht': plugin_options['enable_dht'],
            'ds_enabled': plugin_options['ds_enabled'],
            'label': plugin_options['label'],
            'label_ds0': plugin_options['label_ds0'],
            'label_ds1': plugin_options['label_ds1'],
            'label_ds2': plugin_options['label_ds2'],
            'label_ds3': plugin_options['label_ds3'],
            'label_ds4': plugin_options['label_ds4'],
            'label_ds5': plugin_options['label_ds5'],
            'ds0_enabled': DS18B20_is_enabled(0),
            'ds1_enabled': DS18B20_is_enabled(1),
            'ds2_enabled': DS18B20_is_enabled(2),
            'ds3_enabled': DS18B20_is_enabled(3),
            'ds4_enabled': DS18B20_is_enabled(4),
            'ds5_enabled': DS18B20_is_enabled(5),
            'ds_active': DS18B20_active_indexes(),
            'temp_ds0':  DS18B20_read_probe(0),
            'temp_ds1':  DS18B20_read_probe(1),
            'temp_ds2':  DS18B20_read_probe(2),
            'temp_ds3':  DS18B20_read_probe(3),
            'temp_ds4':  DS18B20_read_probe(4),
            'temp_ds5':  DS18B20_read_probe(5),
            'temp_dht':  DHT_read_temp_value(),
            'humi_dht':  DHT_read_humi_value()
            }
        except:
            log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
            pass

        return json.dumps(data)


class log_json(ProtectedPage):
    """Returns data in JSON format from local file log."""

    def GET(self):
        data = []
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            data = json.dumps(read_log())
        except:
            log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
            pass
        return data


class log_sql_json(ProtectedPage):
    """Returns data in JSON format from database file log."""

    def GET(self):
        data = []
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            data = json.dumps(read_sql_log())
        except:
            log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
            pass
        return data


class graph_json(ProtectedPage):
    """Returns graph data in JSON format."""

    def GET(self):
        data = []
        try:
            from datetime import datetime
            qdict = web.input()

            dt_from_text = qdict.get('dt_from', plugin_options['dt_from'])
            dt_to_text = qdict.get('dt_to', plugin_options['dt_to'])
            show_err = qdict.get('show_err', None)
            if show_err is None:
                show_err = plugin_options['show_err']
            else:
                show_err = show_err in ('1', 'on', 'true', 'True')

            dt_from = datetime.strptime(dt_from_text, '%Y-%m-%dT%H:%M') # from
            dt_to   = datetime.strptime(dt_to_text, '%Y-%m-%dT%H:%M')   # to

            epoch_time = datetime(1970, 1, 1)

            log_start = int((dt_from - epoch_time).total_seconds())
            log_end = int((dt_to - epoch_time).total_seconds())
 
            try:
                if plugin_options['type_log'] == 0:
                    json_data = read_graph_log()
                if plugin_options['type_log'] == 1:
                    json_data = read_graph_sql_log()
            except:
                json_data = []
                pass

            if len(json_data) > 0:
                for i in range(0, min(8, len(json_data))):                         # 0 = ds1 ... 5 = ds6, 6 = DHT temp, 7 = DHT humi
                    if i < 6:
                        station_name = DS18B20_graph_name(i)
                    elif i == 6 and plugin_options['enable_dht']:
                        station_name = plugin_options['label'] + ' &deg;C'
                    elif i == 7 and plugin_options['enable_dht']:
                        station_name = plugin_options['label'] + ' %'
                    else:
                        station_name = ''
                    if not station_name:
                        continue
                    temp_balances = {}
                    for key in json_data[i]['balances']:
                        try:
                            find_key = int(key.encode('utf8'))                     # key is in unicode ex: u'1601347000' -> find_key is int number
                        except:
                            find_key = key   
                        if find_key >= log_start and find_key <= log_end:          # timestamp interval from <-> to
                            find_data = json_data[i]['balances'][key] 
                            if show_err:                                           # if is checked show error values in graph
                                temp_balances[key] = json_data[i]['balances'][key]
                            else:
                                if float(find_data['total']) != -127.0:            # not checked, add values if not -127
                                    temp_balances[key] = json_data[i]['balances'][key]    
                    data.append({ 'station': station_name, 'balances': temp_balances })

        except:
            log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
            pass

        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(data)

class log_csv(ProtectedPage):  # save log file from web as csv file type
    """Simple Log API"""
    def GET(self):
        data = []
        try:
            log_file = read_log()
            name1 = plugin_options['label_ds0']
            name2 = plugin_options['label_ds1']
            name3 = plugin_options['label_ds2']
            name4 = plugin_options['label_ds3']
            name5 = plugin_options['label_ds4']
            name6 = plugin_options['label_ds5']
            data = "Date/Time; Date; Time; DHT Temperature C; DHT Humidity %; DHT Output; " + name1 + "; " + name2 + "; " + name3 + "; " + name4 + "; " + name5 + "; " + name6 + "\n"
            for interval in log_file:
                data += '; '.join([
                    interval['datetime'],
                    interval['date'],
                    interval['time'],
                    '{}'.format(interval['temp']),
                    '{}'.format(interval['humi']),
                    '{}'.format(interval['outp']),
                    '{}'.format(interval['ds0']),
                    '{}'.format(interval['ds1']),
                    '{}'.format(interval['ds2']),
                    '{}'.format(interval['ds3']),
                    '{}'.format(interval['ds4']),
                    '{}'.format(interval['ds5']),
                ]) + '\n'

        except:
            log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
            pass

        filestamp = time.strftime('%Y%m%d-%H%M%S')
        filename = 'log_{}_.csv'.format(filestamp)
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-type', 'text/csv') # https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types 
        web.header('Content-Disposition', 'attachment; filename="{}"'.format(filename))
        return data

class log_sql_csv(ProtectedPage):  # save log file from database as csv file type from web
    """Simple Log API"""
    def GET(self):
        data = []
        try:
            from plugins.database_connector import execute_db
            sql = "SELECT * FROM airtemp"
            log_file = execute_db(sql, test=False, commit=False, fetch=True) # fetch=true return data from table in format: id,datetime,ds1,ds2,ds3,ds4,ds5,ds6,dhttemp,dhthumi,dhtstate
            name1 = plugin_options['label_ds0']
            name2 = plugin_options['label_ds1']
            name3 = plugin_options['label_ds2']
            name4 = plugin_options['label_ds3']
            name5 = plugin_options['label_ds4']
            name6 = plugin_options['label_ds5']
            data = "Id; DateTime; DHT Temperature C; DHT Humidity %; DHT Output; " + name1 + "; " + name2 + "; " + name3 + "; " + name4 + "; " + name5 + "; " + name6 + "\n"
            for interval in log_file:
                data += '; '.join([
                    '{}'.format(str(interval[0])),
                    '{}'.format(str(interval[1])),
                    '{}'.format(str(interval[8])),
                    '{}'.format(str(interval[9])),
                    '{}'.format(str(interval[10])),
                    '{}'.format(str(interval[2])),
                    '{}'.format(str(interval[3])),
                    '{}'.format(str(interval[4])),
                    '{}'.format(str(interval[5])),
                    '{}'.format(str(interval[6])),
                    '{}'.format(str(interval[7])),
                ]) + '\n'

        except:
            log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
            pass
        
        filestamp = time.strftime('%Y%m%d-%H%M%S')
        filename = 'log_{}_.csv'.format(filestamp)
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-type', 'text/csv') # https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types
        web.header('Content-Disposition', 'attachment; filename="{}"'.format(filename))
        return data
