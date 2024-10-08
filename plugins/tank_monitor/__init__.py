# -*- coding: utf-8 -*-
# this plugin check water level in tank via ultrasonic sensor.
# for more use this hardware: https://pihrt.com/elektronika/339-moje-raspberry-pi-plugin-ospy-vlhkost-pudy-a-mozstvi-vody-v-tankua
# HW Atmega328 has 30sec timeout for reboot if not accesing via I2C bus.

__author__ = 'Martin Pihrt' # www.pihrt.com

import json
import time
import datetime

import sys
import traceback
import os

from threading import Thread, Event

import web

from ospy import helpers
from ospy.options import options, rain_blocks
from ospy.log import log, logEM
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.helpers import get_rpi_revision
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string
from ospy.stations import stations
from ospy.scheduler import predicted_schedule, combined_schedule

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer

from blinker import signal


NAME = 'Water Tank Monitor'
MENU =  _('Package: Water Tank Monitor')
LINK = 'settings_page'

tank_options = PluginOptions(
    NAME,
    {
       'use_sonic': False,      # use sonic sensor
       'distance_bottom': 213, # sensor <-> bottom tank
       'distance_top': 52,     # sensor <-> top tank
       'water_minimum': 60,    # water level <-> bottom tank
       'water_unblocking': 10, # unblocking for watering (cut rain delay)
       'diameter': 98,         # cylinder diameter for volume calculation
       'use_stop':      False, # not stop water system
       'use_send_email': True, # send email water level is minimum
       'emlsubject': _('Report from OSPy TANK plugin'),
       'address_ping': 0x04,   # device address for sonic ping HW board
       'enable_log': False,    # use logging
       'log_interval': 1,      # interval for log in minutes
       'log_records': 0,       # the number of records 
       'check_liters': False,  # display as liters or m3 (true = liters)
       'use_water_err': False, # send email probe has error
       'enable_reg': False,    # use maximal water regulation
       'reg_max': 300,         # maximal water level in cm for activate
       'reg_min': 280,         # minimal water level in cm for deactivate
       'reg_output': 0,        # selector for output
       'reg_mm': 60,           # min for maximal runtime
       'reg_ss': 0,            # sec for maximal runtime
       'use_water_stop': False,# if the level sensor fails, the above selected stations in the scheduler will stop
       'used_stations': [],    # use this stations for stoping scheduler if stations is activated in scheduler
       'delay_duration': 0,    # if there is no water in the tank and the stations stop, then we set the rain delay for this time for blocking
       'use_footer': True,     # show data from plugin in footer on home page
       'eplug': 0,             # email plugin type (email notifications or email notifications SSL)
       'use_avg':      False,  # use average for sonic samples
       'avg_samples': 20,      # number of samples for average
       'input_byte_debug_log': False, # logging for advanced user (save debug data from I2C bus)
       'byte_changed': True,   # logging of data only when this data changes, otherwise still logging.
       'saved_min': 400,       # logging min water level
       'saved_max': 0,         # logging max water level
       'en_sql_log': False,    # logging temperature to sql database
       'type_log': 0,          # 0 = show log and graph from local log file, 1 = from database
       'dt_from' : '2024-01-01T00:00',         # for graph history (from date time ex: 2024-02-01T6:00)
       'dt_to' : '2024-01-01T00:00',           # for graph history (to date time ex: 2024-03-17T12:00)

    }
)

global status
status = {}
status['level']    = -1
status['percent']  = -1
status['ping']     = -1
status['volume']   = -1
status['minlevel'] = tank_options['saved_min']
status['maxlevel'] = tank_options['saved_max']
status['maxlevel_datetime'] = datetime_string()
status['minlevel_datetime'] = datetime_string()

################################################################################
# Main function loop:                                                          #
################################################################################

class Sender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()

        global status, avg_lst, avg_cnt, avg_rdy

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
        last_millis = int(round(time.time() * 1000))   # timer for save log
        once_text = True
        two_text = True
        three_text = True
        five_text = True
        six_text = True
        send = False
        mini = True

        sonic_cm = -1
        level_in_tank = 0
        regulation_text = _('Regulation NONE.')

        if NAME in rain_blocks:
            del rain_blocks[NAME]
        self._sleep(2)

        tank_mon = None

        if tank_options['use_footer']:
            tank_mon = showInFooter() #  instantiate class to enable data in footer
            tank_mon.button = "tank_monitor/settings"        # button redirect on footer
            tank_mon.label =  _('Tank')                     # label on footer

        end = datetime.datetime.now()

        avg_lst = [0]*tank_options['avg_samples']
        avg_cnt = 0
        avg_rdy = False

        while not self._stop_event.is_set():
            try:
                if tank_options['use_sonic']: 
                    if two_text:
                        log.clear(NAME)
                        log.info(NAME, _('Water tank monitor is enabled.'))
                        once_text = True
                        two_text = False

                    ping_read = get_sonic_cm()

                    if tank_options['use_avg'] and ping_read > 0: # use averaging
                        try:
                            avg_lst[avg_cnt] = ping_read
                        except:
                            avg_lst.append(ping_read)    
                        avg_cnt += 1
                        if avg_cnt > tank_options['avg_samples']:
                            avg_cnt = 0
                            avg_rdy = True
                        if avg_rdy:
                            sonic_cm = average_list(avg_lst)
                            level_in_tank = get_sonic_tank_cm(sonic_cm)
                        else:    
                            sonic_cm = 0
                            log.clear(NAME)
                            log.info(NAME, _('Waiting for {} samples to be read from the sensor (when using averaging).').format(tank_options['avg_samples']))
                    else:                       # without averaging
                        if ping_read > 0:       # if sonic value is bad (-1) not use these
                            sonic_cm = ping_read
                            level_in_tank = get_sonic_tank_cm(sonic_cm)
                        else:
                            sonic_cm = 0
                            level_in_tank = 0

                    tempText = ""

                    if level_in_tank > 0 and sonic_cm != 0:  # if level is ok and sonic is ok
                        three_text = True
                        status['level']   = level_in_tank
                        status['ping']    = sonic_cm
                        status['volume']  = get_volume(level_in_tank)
                        status['percent'] = get_tank(level_in_tank)

                        ### printing information
                        log.clear(NAME)
                        if tank_options['check_liters']: # display in liters
                            tempText =  str(status['volume']) + ' ' + _('liters') + ', ' + str(status['level']) + ' ' + _('cm') + ' (' + str(status['percent']) + ' ' + ('%)')
                        else:
                            tempText =  str(status['volume']) + ' ' + _('m3') + ', ' + str(status['level']) + ' ' + _('cm') + ' (' + str(status['percent']) + ' ' + ('%)')                        
                        log.info(NAME, regulation_text)

                        ### regulation water level (automation)
                        if tank_options['enable_reg']:                                    # if enable regulation "maximum water level"
                            reg_station = stations.get(tank_options['reg_output'])
                            if int(status['level']) > int(tank_options['reg_max']):       # if actual level in tank > set maximum water level
                                if five_text:
                                    five_text = False
                                    six_text = True
                                    regulation_text = datetime_string() + ' ' + _('Regulation set ON.') + ' ' + ' (' + _('Output') + ' ' +  str(reg_station.index+1) + ').'

                                    start = datetime.datetime.now()
                                    sid = reg_station.index
                                    end = datetime.datetime.now() + datetime.timedelta(seconds=tank_options['reg_ss'], minutes=tank_options['reg_mm'])
                                    new_schedule = {
                                        'active': True,
                                        'program': -1,
                                        'station': sid,
                                        'program_name': _('Tank Monitor'),
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
                
                            if int(status['level']) < int(tank_options['reg_min']):        # if actual level in tank < set minimum water level
                                if six_text: # blocking for once
                                    five_text = True
                                    six_text = False
                                    regulation_text = datetime_string() + ' ' + _('Regulation set OFF.') + ' ' + ' (' + _('Output') + ' ' +  str(reg_station.index+1) + ').'
                                    sid = reg_station.index
                                    stations.deactivate(sid)
                                    active = log.active_runs()
                                    for interval in active:
                                        if interval['station'] == sid:
                                            log.finish_run(interval)

                            now = datetime.datetime.now()
                            if now > end: # if program end in schedule release five_text to true in regulation for next scheduling #
                                five_text = True
                                six_text = False
                                regulation_text = datetime_string() + ' ' + _('Waiting.')

                        ### changing the maximum level, so we will save it
                        if int(status['level']) > int(status['maxlevel']):                           # maximum level check                           
                            status['maxlevel'] = int(status['level'])
                            tank_options.__setitem__('saved_max', status['level'])
                            status['maxlevel_datetime'] = datetime_string()
                            log.info(NAME, datetime_string() + ': ' + _('Maximum has updated.'))
                            update_log()
  
                        ### changing the minimum level, so we will save it
                        if int(status['level']) < int(status['minlevel']):                           # minimum level check 
                            status['minlevel'] = int(status['level'])
                            tank_options.__setitem__('saved_min', status['level'])
                            status['minlevel_datetime'] = datetime_string()
                            log.info(NAME, datetime_string() + ': ' + _('Minimum has updated.'))
                            update_log()
                        
                        ### the water level is lower than the set minimum    
                        if int(status['level']) <= int(tank_options['water_minimum']):
                            if tank_options['use_send_email'] and mini:                    # if email is enabled
                                send = True                                                # send
                                mini = False
                            if tank_options['use_stop']:                                   # if stop scheduler
                                set_stations_in_scheduler_off()
                                log.info(NAME, datetime_string() + ' ' + _('ERROR: Water in Tank') + ' < ' + str(tank_options['water_minimum']) + ' ' + _('cm') + _('!'))
                                delaytime = int(tank_options['delay_duration'])
                                if delaytime > 0:                                          # if there is no water in the tank and the stations stop, then we set the rain delay for this time for blocking
                                    if NAME not in rain_blocks:
                                        rain_blocks[NAME] = datetime.datetime.now() + datetime.timedelta(hours=float(delaytime))

                        ### the water level is xx cm higher than the set minimum
                        if int(status['level']) > int(tank_options['water_minimum']) + int(tank_options['water_unblocking']) and not mini: # refresh send email if actual level > options minimum + xx cm
                            mini = True
                            if NAME in rain_blocks:
                                del rain_blocks[NAME]

                        ### periodically logging
                        if tank_options['enable_log'] or tank_options['en_sql_log']:
                            millis = int(round(time.time() * 1000))
                            interval = (tank_options['log_interval'] * 60000)
                            if (millis - last_millis) > interval:
                               last_millis = millis
                               update_log()

                    elif level_in_tank == -1 and sonic_cm == 0:     # waiting for samples
                        tempText =  _('Waiting for samples')
                    else:                                           # error probe
                        tempText =  _('FAULT')
                        log.clear(NAME)
                        log.info(NAME, datetime_string() + ' ' + _('Water level: Error.'))
                        if tank_options['use_water_err'] and three_text:   # if probe has error send email
                            three_text = False
                            log.info(NAME, datetime_string() + ' ' + _('ERROR: Water probe has fault?'))

                            msg = '<b>' + _('Water Tank Monitor plug-in') + '</b> ' + '<br><p style="color:red;">' + _('System detected error: Water probe has fault?') + '</p>'
                            msglog = _('Water Tank Monitor plug-in') + ': ' + _('System detected error: Water probe has fault?')
                            try:
                                from plugins.email_notifications import try_mail
                                try_mail(msg, msglog, attachment=None, subject=tank_options['emlsubject']) # try_mail(text, logtext, attachment=None, subject=None)

                            except Exception:
                                log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())

                        if tank_options['use_water_stop']:
                            if NAME not in rain_blocks:
                                set_stations_in_scheduler_off()
                                delaytime = int(tank_options['delay_duration'])
                                if delaytime > 0:                             # if probe has fault, then we set the rain delay for this time for blocking
                                    rain_blocks[NAME] = datetime.datetime.now() + datetime.timedelta(hours=float(delaytime))


                    if tank_options['enable_reg']:
                        tempText += ', ' + regulation_text

                    if tank_options['use_footer']:
                        if tank_mon is not None:    
                            tank_mon.val = tempText.encode('utf8').decode('utf8')           # value on footer

                    self._sleep(3)

                else:
                    if once_text:
                       log.clear(NAME)
                       log.info(NAME, _('Water tank monitor is disabled.'))
                       once_text = False
                       two_text = True
                       last_level = 0
                    self._sleep(1)

                if send:
                    msg = '<b>' + _('Water Tank Monitor plug-in') + '</b> ' + '<br><p style="color:red;">' + _('System detected error: Water Tank has minimum Water Level') +  ': ' + str(tank_options['water_minimum']) + _('cm') + '.\n' + '</p>'
                    msglog = _('Water Tank Monitor plug-in') + ': ' + _('System detected error: Water Tank has minimum Water Level') +  ': ' + str(tank_options['water_minimum']) + _('cm') + '. '  
                    send = False
                    try:
                        try_mail = None
                        if tank_options['eplug']==0: # email_notifications
                            from plugins.email_notifications import try_mail
                        if tank_options['eplug']==1: # email_notifications SSL
                            from plugins.email_notifications_ssl import try_mail    
                        if try_mail is not None:
                            try_mail(msg, msglog, attachment=None, subject=tank_options['emlsubject']) # try_mail(text, logtext, attachment=None, subject=None)

                    except Exception:
                        log.info(NAME, _('E-mail not send! The Email Notifications plug-in is not found in OSPy or not correctly setuped.'))
                        log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())


            except Exception:
                log.clear(NAME)
                log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
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

def average_list(lst):
    ### Average of a list ###
    try:
        import statistics
        return int(statistics.mean(lst))
    except:
        log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
        return -1

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
            time.sleep(0.1) #wait here to avoid 121 IO Error
        else:
            break

    if not tries:
        raise error

    return result

global last_data0, last_data1
last_data0 = 0
last_data1 = 0

def get_sonic_cm():
    global last_data0, last_data1
    try:
        import smbus
        bus = smbus.SMBus(1 if get_rpi_revision() >= 2 else 0)
        try:
            data = try_io(lambda: bus.read_i2c_block_data(tank_options['address_ping'], 4)) # read bytes from I2C
            # data[0] is ultrasonic distance in overflow 255
            # data[1] is ultrasonic distance in range 0-255cm
            # ex: sonic is 180cm -> d0=0, d1=180
            # ex: sonic is 265cm -> d0=1, d1=10
            # data[2] is firmware version in CPU Atmega328 on board
            # data[3] is CRC sum

            val = data[1] + data[0]*255

            ### logging ###
            if tank_options['input_byte_debug_log']:    # advanced bus logging
                if tank_options['byte_changed']:        # only if data changed
                    if (last_data0 != data[0]) or (last_data1 != data[1]):
                        last_data0 = data[0]
                        last_data1 = data[1]
                        update_debug_log(data[0], data[1], val, data[2], data[3])
                else:                                   # every 3 second log 
                    update_debug_log(data[0], data[1], val, data[2], data[3])

            ### FW version on CPU atmega 328 processing ###
            # NO CRC init old version FW<1.4
            if data[2] == 0xFF or data[2] == 0x00:        # not found version in atmega 328 (known version is 0x0D 13 FW1.3, 0x0E 14 FW1.4, 0x0F 15 FW1.5 ...)
                log.debug(NAME, _('FW version in CPU (Atmega 328) is FW <= 1.3'))
                if data[1] == 0xFF or data[0] == 0xFF:    # first check on buss error on sonic distance (byte 0 or byte 1 is 255 -> error skip)
                    return -1
                elif data[1] == 0x00 and data[0] == 0x00: # next check on buss error on sonic distance (byte 0 or byte 1 is 0 -> error skip)
                    return -1                    
                else:
                    if val > 400:                         # 400 cm is max ping from ultrasonic sensor
                        return -1
                    else:
                        return val

            # WITH CRC check FW=1.4            
            elif data[2] == 14:                           # 0x0E 14 is FW1.4 in Atmega 328 (with CRC8 check sum)
                from . import crc8                        # online calc http://zorc.breitbandkatze.de/crc.html
                hash = crc8.crc8()
                bytes_val = repr(val).encode('utf8')      # convert int val to bytes ex: int 157 to b'157'
                hash.update(bytes_val)                    # val is calculated ping as sum from byte0 + byte1 (number ex: 0-65535)
                bytes_data = data[3].to_bytes(1, byteorder='big')
                hash_data = hash.digest()      
                if hash_data == bytes_data:               # compare calculated ping in plugin and calculated ping on hw board
                    return val
                else:
                    return -1                       
            
            # UNKOWN VERSION       
            else:
                log.debug(NAME, _('Unkown FW version in CPU (Atmega 328)')) 
                return -1       

        except:
            log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
            return -1
    except:
        log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
        return -1


def get_sonic_tank_cm(level):
    try:
        cm = level
        if cm < 0:
           return -1

        tank_cm = maping(int(cm),int(tank_options['distance_bottom']),int(tank_options['distance_top']),0,(int(tank_options['distance_bottom'])-int(tank_options['distance_top'])))
        if tank_cm >= 0:
           return tank_cm

        else:
           return -1
    except:
        return -1 # if I2C device not exists


def get_tank(level): # return water tank level 0-100%, -1 is error i2c not found
    tank_lvl = level
    try:
        if tank_lvl >= 0:
            tank_proc = float(tank_lvl)/float(tank_options['distance_bottom']-tank_options['distance_top'])
            tank_proc = float(tank_proc)*100.0
            return int(tank_proc)
        else:
            return -1
    except:
        return -1

def get_volume(level): # return volume calculation from cylinder diameter and water column height in m3
    tank_lvl = level
    if tank_lvl >= 0:
       try:
          import math
          r = tank_options['diameter']/2.0
          area = math.pi*r*r               # calculate area of circle
          volume = area*tank_lvl           # volume in cm3
          if tank_options['check_liters']: # display in liters
            volume = volume*0.001          # convert from cm3 to liter (1 cm3 = 0.001 liter)
          else:  
            volume = volume/1000000.0      # convert from cm3 to m3
          volume = round(volume, 2)         # round only two decimals
          return volume
       except:
          return -1
    else:
       return -1


def maping(x, in_min, in_max, out_min, out_max):
    # return value from map. example (x=1023,0,1023,0,100) -> x=1023 return 100
    return ((x - in_min) * (out_max - out_min)) / ((in_max - in_min) + out_min)


def get_all_values():
    global status
    return status['level'], status['percent'], status['ping'], status['volume'], status['minlevel'], status['maxlevel'], status['minlevel_datetime'], status['maxlevel_datetime'], tank_options['check_liters']


def read_log():
    """Read log data from json file."""
    data = []
    try:
        with open(os.path.join(plugin_data_dir(), 'log.json')) as logf:
            data = json.load(logf)
    except:
        log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
        pass

    return data


def read_sql_log():
    """Read log data from database file."""
    data = None

    try:
        from plugins.database_connector import execute_db
        sql = "SELECT * FROM `tankmonitor` ORDER BY id DESC"
        data = execute_db(sql, test=False, commit=False, fetch=True) # fetch=true return data from table in format: id,datetime,min,max,actual,volume
    except:
        log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
        pass

    return data


def read_debug_log():
    """Read debug log data from json file."""
    data = []

    try:
        with open(os.path.join(plugin_data_dir(), 'debug_log.json')) as logf:
            data = json.load(logf)
    except:
        log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
        pass

    return data        


def read_graph_log():
    """Read graph data from json file."""
    data = []

    try:
        with open(os.path.join(plugin_data_dir(), 'graph.json')) as logf:
            data = json.load(logf)
    except:
        log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
        pass

    return data


def read_graph_sql_log():
    """Read graph data from database file and convert it to json balance file."""
    data = []

    try:
        sql_data = read_sql_log()

        minimum = _('Minimum')
        maximum = _('Maximum')
        level  = _('Level')
        volume  = _('Volume')
 
        graph_data = [
            {"station": minimum, "balances": {}},
            {"station": maximum, "balances": {}}, 
            {"station": level,  "balances": {}},
            {"station": volume,  "balances": {}}
        ]   

        if sql_data is not None:
            for row in sql_data:
                # row[0] is ID, row[1] is datetime, row[2] is min, ... max,actual,volume ...
                epoch = int(datetime.datetime.timestamp(row[1]))
            
                tmp0 = graph_data[0]['balances']
                min_val = {'total': float(row[2])}
                tmp0.update({epoch: min_val})
            
                tmp1 = graph_data[1]['balances']
                max_val = {'total': float(row[3])}
                tmp1.update({epoch: max_val})
            
                tmp2 = graph_data[2]['balances']
                lvl_val = {'total': float(row[4])}
                tmp2.update({epoch: lvl_val})
            
                tmp3 = graph_data[3]['balances']
                vol_val = {'total': float(row[5])}
                tmp3.update({epoch: vol_val})

        data = graph_data

    except:
        log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
        pass

    return data


def write_log(json_data):
    """Write data to log json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'log.json'), 'w') as outfile:
            json.dump(json_data, outfile)
    except:
        log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
        pass


def write_debug_log(json_data):
    """Write data to debug log json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'debug_log.json'), 'w') as outfile:
            json.dump(json_data, outfile)
    except:
        log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
        pass                   


def write_graph_log(json_data):
    """Write data to graph json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'graph.json'), 'w') as outfile:
            json.dump(json_data, outfile)
    except:
        log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
        pass            


def update_log():
    """Update data in json files."""
    global status

    if tank_options['enable_log']:
        ### Data for log ###
        try:
            log_data = read_log()
        except:
            write_log([])
            log_data = read_log()

        from datetime import datetime

        read_all = get_all_values()

        data = {'datetime': datetime_string()}
        data['date'] = str(datetime.now().strftime('%d.%m.%Y'))
        data['time'] = str(datetime.now().strftime('%H:%M:%S'))
        data['minimum'] = str(status['minlevel'])
        data['maximum'] = str(status['maxlevel'])
        data['actual']  = str(read_all[0])
        data['volume']  = str(read_all[3])
      
        log_data.insert(0, data)
        if tank_options['log_records'] > 0:
            log_data = log_data[:tank_options['log_records']]

        try:
            write_log(log_data)
        except:
            write_log([])

        ### Data for graph log ###
        try:
            graph_data = read_graph_log()
        except:
            create_default_graph()
            graph_data = read_graph_log()
            log.debug(NAME, _('Creating default graph log files OK'))

        timestamp = int(time.time())

        try:
            minimum = graph_data[0]['balances']
            minval = {'total': status['minlevel']}
            minimum.update({timestamp: minval})

            maximum = graph_data[1]['balances']
            maxval = {'total': status['maxlevel']}
            maximum.update({timestamp: maxval})

            actual = graph_data[2]['balances']
            actval = {'total': get_all_values()[0]}
            actual.update({timestamp: actval})

            volume = graph_data[3]['balances']
            volumeval = {'total': get_all_values()[3]}
            volume.update({timestamp: volumeval})

            write_graph_log(graph_data)
            log.info(NAME, _('Saving to log  files OK'))
        except:
            create_default_graph()

    if tank_options['en_sql_log']:
        try:
            from plugins.database_connector import execute_db
            # first create table tankmonitor if not exists
            sql = "CREATE TABLE IF NOT EXISTS `tankmonitor` (id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP, min VARCHAR(7), max VARCHAR(7), actual VARCHAR(7), volume VARCHAR(10))"
            execute_db(sql, test=False, commit=False) # not commit
            # next insert data to table tankmonitor
            sql = "INSERT INTO `tankmonitor` (`min`, `max`, `actual`, `volume`) VALUES ('%s','%s','%s','%s')" % (status['minlevel'],status['maxlevel'],get_all_values()[0],get_all_values()[3])
            execute_db(sql, test=False, commit=True)  # yes commit inserted data
            log.info(NAME, _('Saving to SQL database.'))
        except:
            log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
            pass


def update_debug_log(byte_0 = 0, byte_1 = 0, val = 0, byte_2 = 0, byte_3 = 0):
    """Update data in debug json files."""

    ### Data for log ###
    try:
        log_data = read_debug_log()
    except:
        write_log([])
        log_data = read_debug_log()

    from datetime import datetime

    data = {'datetime': datetime_string()}
    data['date'] = str(datetime.now().strftime('%d.%m.%Y'))
    data['b0']   = str(byte_0)
    data['b1']   = str(byte_1)
    data['b2']   = str(byte_2)
    data['b3']   = str(byte_3)
    data['val']  = str(val)
      
    log_data.insert(0, data)

    try:
        write_debug_log(log_data)
    except:
        write_debug_log([])


def create_default_graph():
    """Create default graph json file."""

    minimum = _('Minimum')
    maximum = _('Maximum')
    level   = _('Level')
    volume  = _('Volume')
 
    graph_data = [
       {"station": minimum, "balances": {}},
       {"station": maximum, "balances": {}}, 
       {"station": level,  "balances": {}},
       {"station": volume,  "balances": {}}
    ]
    write_graph_log(graph_data)
    log.info(NAME, _('Deleted all log files OK'))


def set_stations_in_scheduler_off():
    """Stoping selected station in scheduler."""
    
    current_time  = datetime.datetime.now()
    check_start = current_time - datetime.timedelta(days=1)
    check_end = current_time + datetime.timedelta(days=1)

    # In manual mode we cannot predict, we only know what is currently running and the history
    if options.manual_mode:
        active = log.finished_runs() + log.active_runs()
    else:
        active = combined_schedule(check_start, check_end)

    ending = False

    # active stations
    for entry in active:
        for used_stations in tank_options['used_stations']: # selected stations for stoping
            if entry['station'] == used_stations:           # is this station in selected stations? 
                log.finish_run(entry)                       # save end in log 
                stations.deactivate(entry['station'])       # stations to OFF
                ending = True   

    if ending:
        log.info(NAME, _('Stoping stations in scheduler'))


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        try:
            global sender, status, avg_lst, avg_cnt, avg_rdy

            qdict  = web.input()
            reset  = helpers.get_input(qdict, 'reset', False, lambda x: True)
            show = helpers.get_input(qdict, 'show', False, lambda x: True)
            debug = helpers.get_input(qdict, 'debug', False, lambda x: True)
            del_rain = helpers.get_input(qdict, 'del_rain', False, lambda x: True)
            log_now = helpers.get_input(qdict, 'log_now', False, lambda x: True)
            delSQL = helpers.get_input(qdict, 'delSQL', False, lambda x: True)
            delfilter = helpers.get_input(qdict, 'delfilter', False, lambda x: True)

            if sender is not None and reset:
                status['minlevel'] = status['level']
                status['maxlevel'] = status['level']
                tank_options['saved_max'] = status['level']
                tank_options['saved_min'] = status['level']
                status['minlevel_datetime'] = datetime_string()
                status['maxlevel_datetime'] = datetime_string()
                log.info(NAME, datetime_string() + ': ' + _('Minimum and maximum has reseted.'))
                raise web.seeother(plugin_url(settings_page), True)

            if sender is not None and 'dt_from' in qdict and 'dt_to' in qdict:
                dt_from = qdict['dt_from']
                dt_to = qdict['dt_to']
                tank_options.__setitem__('dt_from', dt_from) #__setitem__(self, key, value)
                tank_options.__setitem__('dt_to', dt_to)     #__setitem__(self, key, value)

            if sender is not None and delfilter:
                from datetime import datetime, timedelta
                dt_now = (datetime.today() + timedelta(days=1)).date()
                tank_options.__setitem__('dt_from', "2020-01-01T00:00")
                tank_options.__setitem__('dt_to', "{}T00:00".format(dt_now))

            if sender is not None and log_now:
                update_log()

            if sender is not None and 'history' in qdict:
                history = qdict['history']
                tank_options.__setitem__('history', int(history))

            if sender is not None and show:
                raise web.seeother(plugin_url(log_page), True)

            if sender is not None and debug:
                raise web.seeother(plugin_url(log_debug_page), True)

            if sender is not None and del_rain:
                if NAME in rain_blocks:
                    del rain_blocks[NAME]
                    log.info(NAME, datetime_string() + ': ' + _('Removing Rain Delay') + '.')
                raise web.seeother(plugin_url(settings_page), True)

            if sender is not None and delSQL:
                try:
                    from plugins.database_connector import execute_db
                    sql = "DROP TABLE IF EXISTS `tankmonitor`"
                    execute_db(sql, test=False, commit=False)  
                    log.info(NAME, _('Deleting the tankmonitor table from the database.'))
                except:
                    log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
                    pass

            return self.plugin_render.tank_monitor(tank_options, log.events(NAME))

        except:
            log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('tank_monitor -> settings_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            global sender, avg_lst, avg_cnt, avg_rdy
            tank_options.web_update(web.input(**tank_options)) #for save multiple select
            
            if tank_options['use_sonic']:
                avg_lst = [0]*tank_options['avg_samples']
                avg_cnt = 0
                avg_rdy = False 
                log.clear(NAME)
                log.info(NAME, _('Options has updated.'))
                if sender is not None:
                    sender.update()
            else:
                log.clear(NAME)
                log.info(NAME, _('Water tank monitor is disabled.'))
            
            updateSignal = signal('hass_plugin_update')
            updateSignal.send()
            
            raise web.seeother(plugin_url(settings_page), True)

        except:
            log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('tank_monitor -> settings_page POST')
            return self.core_render.notice('/', msg)

class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            return self.plugin_render.tank_monitor_help()
        except:
            log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('tank_monitor -> help_page GET')
            return self.core_render.notice('/', msg)

class log_page(ProtectedPage):
    """Load an html page for log"""

    def GET(self):
        try:
            global sender, avg_lst, avg_cnt, avg_rdy
            qdict  = web.input()
            delete = helpers.get_input(qdict, 'delete', False, lambda x: True)
            delSQL = helpers.get_input(qdict, 'delSQL', False, lambda x: True)

            if sender is not None and delete:
                write_log([])
                create_default_graph()
                avg_lst = [0]*tank_options['avg_samples']
                avg_cnt = 0
                avg_rdy = False
                tank_options.__setitem__('saved_max', status['level'])
                tank_options.__setitem__('saved_min', status['level']) 
                raise web.seeother(plugin_url(log_page), True)

            if sender is not None and delSQL and tank_options['en_sql_log']:
                try:
                    from plugins.database_connector import execute_db
                    sql = "DROP TABLE IF EXISTS `tankmonitor`"
                    execute_db(sql, test=False, commit=False)  
                    log.info(NAME, _('Deleting the tankmonitor table from the database.'))
                except:
                    log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
                    pass 
            return self.plugin_render.tank_monitor_log(read_log(), read_sql_log(), tank_options)

        except:
            log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('tank_monitor -> log_page GET')
            return self.core_render.notice('/', msg)

class log_debug_page(ProtectedPage):
    """Load an html page for debug log"""

    def GET(self):
        try:
            global sender
            qdict  = web.input()
            delete_debug = helpers.get_input(qdict, 'delete_debug', False, lambda x: True)
            if sender is not None and delete_debug:
                write_debug_log([])

            return self.plugin_render.tank_monitor_debug_log(read_debug_log(), tank_options)        

        except:
            log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('tank_monitor -> log_debug_page GET')
            return self.core_render.notice('/', msg)

class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(tank_options)
        except:
            return {}

class data_json(ProtectedPage):
    """Returns plugin data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data = {}
        try:
            read_all = get_all_values()
            data =  {
            'level': read_all[0],
            'percent': read_all[1],
            'ping': read_all[2],
            'volume': read_all[3],
            'minlevel': read_all[4],
            'maxlevel': read_all[5],
            'minlevel_datetime': read_all[6],
            'maxlevel_datetime': read_all[7],
            'unit': _('L') if read_all[8] else  _('m3'),
            'label': tank_options['emlsubject']
            }
            return json.dumps(data)
        except:
            log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
            return data

class log_json(ProtectedPage):
    """Returns data in JSON format."""

    def GET(self):
        data = []
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            data = json.dumps(read_log())
        except:
            log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
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
            log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
            pass
        return data


class graph_json(ProtectedPage):
    """Returns graph data in JSON format."""

    def GET(self):
        data = []
        try:
            from datetime import datetime

            dt_from = datetime.strptime(tank_options['dt_from'], '%Y-%m-%dT%H:%M') # from
            dt_to   = datetime.strptime(tank_options['dt_to'], '%Y-%m-%dT%H:%M')   # to

            epoch_time = datetime(1970, 1, 1)

            log_start = int((dt_from - epoch_time).total_seconds())
            log_end = int((dt_to - epoch_time).total_seconds())

            json_data = [{}]

            try:
                if tank_options['type_log'] == 0:
                    json_data = read_graph_log()
                if tank_options['type_log'] == 1:
                    json_data = read_graph_sql_log()
            except:
                log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
                pass

            if len(json_data) > 0:  
                for i in range(0, 4):                                              # 0 = min, max, actual
                    temp_balances = {}
                    for key in json_data[i]['balances']:
                        try:
                            find_key = int(key.encode('utf8'))                     # key is in unicode ex: u'1601347000' -> find_key is int number
                        except:
                            find_key = key      
                        if find_key >= log_start and find_key <= log_end:          # timestamp interval from <-> to
                            temp_balances[key] = json_data[i]['balances'][key]    
                    data.append({ 'station': json_data[i]['station'], 'balances': temp_balances })

        except:
            log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
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
            minimum = _('Minimum')
            maximum = _('Maximum')
            actual  = _('Actual')
            volume  = _('Volume')
            data  = "Date/Time"
            data += "; Date"
            data += "; Time"
            data += "; %s cm" % minimum
            data += "; %s cm" % maximum
            data += "; %s cm" % actual
            if tank_options['check_liters']:
                data += "; %s liters" % volume
            else:    
                data += "; %s m3" % volume
            data += '\n'

            for interval in log_file:
                data += '; '.join([
                    interval['datetime'],
                    interval['date'],
                    interval['time'],
                    '{}'.format(interval['minimum']),
                    '{}'.format(interval['maximum']),
                    '{}'.format(interval['actual']),
                    '{}'.format(interval['volume']),
                ]) + '\n'

        except:
            log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
            pass

        filestamp = time.strftime('%Y%m%d-%H%M%S')
        filename = 'local_log_{}_.csv'.format(filestamp)
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
            sql = "SELECT * FROM `tankmonitor`"
            log_file = execute_db(sql, test=False, commit=False, fetch=True) # fetch=true return data from table in format: id,datetime,ds1,ds2,ds3,ds4,ds5,ds6,dhttemp,dhthumi,dhtstate
            
            minimum = _('Minimum')
            maximum = _('Maximum')
            actual  = _('Actual')
            volume  = _('Volume')
            data  = "Id"
            data += "; Date/Time"
            data += "; %s cm" % minimum
            data += "; %s cm" % maximum
            data += "; %s cm" % actual
            if tank_options['check_liters']:
                data += "; %s liters" % volume
            else:    
                data += "; %s m3" % volume
            data += '\n'

            for interval in log_file:
                data += '; '.join([
                    '{}'.format(interval[0]),
                    '{}'.format(interval[1]),
                    '{}'.format(interval[2]),
                    '{}'.format(interval[3]),
                    '{}'.format(interval[4]),
                    '{}'.format(interval[5]),
                ]) + '\n'

        except:
            log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
            pass
        
        filestamp = time.strftime('%Y%m%d-%H%M%S')
        filename = 'sql_log_{}_.csv'.format(filestamp)
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-type', 'text/csv') # https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types
        web.header('Content-Disposition', 'attachment; filename="{}"'.format(filename))
        return data


class debug_log_csv(ProtectedPage):  # save debug log file from web as csv file type
    """Simple Log API"""
    def GET(self):
        data = []
        try:
            log_file = read_debug_log()
            data  = "Date/Time"
            data += "; Byte 0"
            data += "; Byte 1"
            data += "; Value"
            data += "; Byte 2 FW"
            data += "; Byte 3 CRC"
            data += '\n'

            for interval in log_file:
                data += '; '.join([
                    interval['datetime'],
                    '{}'.format(interval['b0']),
                    '{}'.format(interval['b1']),
                    '{}'.format(interval['val']),
                    '{}'.format(interval['b2']),
                    '{}'.format(interval['b3']),
                ]) + '\n'

        except:
            log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
            pass

        filestamp = time.strftime('%Y%m%d-%H%M%S')
        filename = 'debug_log_{}_.csv'.format(filestamp)
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-type', 'text/csv') # https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types 
        web.header('Content-Disposition', 'attachment; filename="{}"'.format(filename))
        return data