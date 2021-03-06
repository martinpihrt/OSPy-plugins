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


NAME = 'Water Tank Monitor'
MENU =  _(u'Package: Water Tank Monitor')
LINK = 'settings_page'

tank_options = PluginOptions(
    NAME,
    {
       'use_sonic': True,      # use sonic sensor
       'distance_bottom': 213, # sensor <-> bottom tank
       'distance_top': 52,     # sensor <-> top tank
       'water_minimum': 60,    # water level <-> bottom tank
       'diameter': 98,         # cylinder diameter for volume calculation
       'use_stop':      False, # not stop water system
       'use_send_email': True, # send email water level is minimum
       'emlsubject': _(u'Report from OSPy TANK plugin'),
       'address_ping': 0x04,   # device address for sonic ping HW board
       'log_maxlevel': 400,    # maximal level (log)
       'log_minlevel': 0,      # minimal level (log)
       'log_date_maxlevel': datetime_string(), # maximal level (date log)
       'log_date_minlevel': datetime_string(), # minimal level (date log)
       'enable_log': False,    # use logging
       'log_interval': 1,      # interval for log in minutes
       'log_records': 0,       # the number of records 
       'check_liters': False,  # display as liters or m3 (true = liters)
       'use_water_err': False, # send email probe has error
       'enable_reg': False,    # use maximal water regulation
       'reg_max': 300,         # maximal water level in cm for activate
       'reg_min': 280,         # minimal water level in cm for deactivate
       'reg_output': 0,        # selector for output
       'history': 0,           # selector for graph history
       'reg_mm': 60,           # min for maximal runtime
       'reg_ss': 0,            # sec for maximal runtime
       'use_water_stop': False,# if the level sensor fails, the above selected stations in the scheduler will stop
       'used_stations': [],    # use this stations for stoping scheduler if stations is activated in scheduler
       'delay_duration': 0,    # if there is no water in the tank and the stations stop, then we set the rain delay for this time for blocking
    } 
)

status = { }
################################################################################
# Main function loop:                                                          #
################################################################################

class Sender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop = Event()

        global status

        status['level']    = -1
        status['percent']  = -1
        status['ping']     = -1
        status['volume']   = -1

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
        last_millis = 0    # timer for save log
        once_text = True   # once_text to mini is auxiliary for blocking
        two_text = True
        three_text = True
        five_text = True
        six_text = True
        send = False
        mini = True

        sonic_cm = get_sonic_cm()
        level_in_tank = get_sonic_tank_cm(sonic_cm)
        regulation_text = _(u'Regulation NONE.')
        if NAME in rain_blocks:
            del rain_blocks[NAME]        
        self._sleep(2)

        tank_mon = showInFooter() #  instantiate class to enable data in footer
        tank_mon.button = "tank_monitor/settings"       # button redirect on footer
        tank_mon.label =  _(u'Tank')                     # label on footer

        end = datetime.datetime.now()

        while not self._stop.is_set():
            try:
                if tank_options['use_sonic']: 
                    if two_text:
                        log.clear(NAME)
                        log.info(NAME, _(u'Water tank monitor is enabled.'))
                        once_text = True
                        two_text = False
 
                    sonic_cm = get_sonic_cm()
                    level_in_tank = get_sonic_tank_cm(sonic_cm)

                    tempText = ""                    

                    if level_in_tank > 0 and sonic_cm != 0:  # if level is ok and sonic is ok
                        three_text = True

                        status['level']   = level_in_tank
                        status['ping']    = sonic_cm
                        status['volume']  = get_volume(level_in_tank)
                        status['percent'] = get_tank(level_in_tank)    

                        log.clear(NAME)
                        log.info(NAME, datetime_string() + ' ' + _(u'Water level') + ': ' + str(status['level']) + ' ' + _(u'cm') + ' (' + str(status['percent']) + ' ' + (u'%).'))
                        if tank_options['check_liters']: # display in liters
                            tempText =  str(status['volume']) + ' ' + _(u'liters') + ', ' + str(status['level']) + ' ' + _(u'cm') + ' (' + str(status['percent']) + ' ' + (u'%)')
                            log.info(NAME, _(u'Ping') + ': ' + str(status['ping']) + ' ' + _(u'cm') + ', ' + _(u'Volume') + ': ' + str(status['volume']) + ' ' + _(u'liters') + '.')
                        else:
                            tempText =  str(status['volume']) + ' ' + _(u'm3') + ', ' + str(status['level']) + ' ' + _(u'cm') + ' (' + str(status['percent']) + ' ' + (u'%)')
                            log.info(NAME, _(u'Ping') + ': ' + str(status['ping']) + ' ' + _(u'cm') + ', ' + _(u'Volume') + ': ' + str(status['volume']) + ' ' + _(u'm3') + '.')
                        log.info(NAME, str(tank_options['log_date_maxlevel']) + ' ' + _(u'Maximum Water level') + ': ' + str(tank_options['log_maxlevel']) + ' ' + _(u'cm') + '.')   
                        log.info(NAME, str(tank_options['log_date_minlevel']) + ' ' + _(u'Minimum Water level') + ': ' + str(tank_options['log_minlevel']) + ' ' + _(u'cm') + '.') 
                        log.info(NAME, regulation_text)

                        if tank_options['enable_reg']:                                    # if enable regulation "maximum water level"
                            reg_station = stations.get(tank_options['reg_output'])
                            if level_in_tank > tank_options['reg_max']:                   # if actual level in tank > set maximum water level
                                if five_text:
                                    five_text = False
                                    six_text = True
                                    regulation_text = datetime_string() + ' ' + _(u'Regulation set ON.') + ' ' + ' (' + _(u'Output') + ' ' +  str(reg_station.index+1) + ').'
                                    
                                    start = datetime.datetime.now()
                                    sid = reg_station.index
                                    end = datetime.datetime.now() + datetime.timedelta(seconds=tank_options['reg_ss'], minutes=tank_options['reg_mm'])
                                    new_schedule = {
                                        'active': True,
                                        'program': -1,
                                        'station': sid,
                                        'program_name': _(u'Tank Monitor'),
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
                
                            if level_in_tank < tank_options['reg_min']:                   # if actual level in tank < set minimum water level
                                if six_text: # blocking for once
                                    five_text = True
                                    six_text = False
                                    regulation_text = datetime_string() + ' ' + _(u'Regulation set OFF.') + ' ' + ' (' + _(u'Output') + ' ' +  str(reg_station.index+1) + ').'
                                    
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
                                regulation_text = datetime_string() + ' ' + _(u'Waiting.')

                        if status['level'] > tank_options['log_maxlevel']:                         # maximum level check
                            if tank_options['use_sonic']:
                                tank_options.__setitem__('use_sonic', u'on')
                            if tank_options['check_liters']:
                                tank_options.__setitem__('check_liters', u'on')
                            if tank_options['enable_reg']:
                                tank_options.__setitem__('enable_reg', u'on')
                            if tank_options['enable_log']:
                                tank_options.__setitem__('enable_log', u'on')
                            if tank_options['use_stop']:
                                tank_options.__setitem__('use_stop', u'on')
                            if tank_options['use_send_email']:
                                tank_options.__setitem__('use_send_email', u'on')
                            if tank_options['use_water_stop']:
                                tank_options.__setitem__('use_water_stop', u'on')
                            tank_options.__setitem__('log_maxlevel', status['level'])
                            qmax = datetime_string()
                            tank_options.__setitem__('log_date_maxlevel', qmax)
                            log.info(NAME, datetime_string() + ': ' + _(u'Maximum has updated.'))
  
                        if status['level'] < tank_options['log_minlevel'] and status['level'] > 2:  # minimum level check 
                            if tank_options['use_sonic']:
                                tank_options.__setitem__('use_sonic', u'on')
                            if tank_options['check_liters']:
                                tank_options.__setitem__('check_liters', u'on')
                            if tank_options['enable_reg']:
                                tank_options.__setitem__('enable_reg', u'on')
                            if tank_options['enable_log']:
                                tank_options.__setitem__('enable_log', u'on')
                            if tank_options['use_stop']:
                                tank_options.__setitem__('use_stop', u'on')
                            if tank_options['use_send_email']:
                                tank_options.__setitem__('use_send_email', u'on')
                            if tank_options['use_water_stop']:
                                tank_options.__setitem__('use_water_stop', u'on')
                            tank_options.__setitem__('log_minlevel', status['level'])
                            qmin = datetime_string()
                            tank_options.__setitem__('log_date_minlevel', qmin)
                            log.info(NAME, datetime_string() + ': ' + _(u'Minimum has updated.'))
                            
                        if status['level'] <= int(tank_options['water_minimum']) and mini and not options.manual_mode and status['level'] > 2: # level value is lower
                            if tank_options['use_send_email']:                             # if email is enabled
                                send = True                                                # send
                                mini = False 
    
                            if tank_options['use_stop']:                                   # if stop scheduler
                                set_stations_in_scheduler_off()         
                                log.info(NAME, datetime_string() + ' ' + _(u'ERROR: Water in Tank') + ' < ' + str(tank_options['water_minimum']) + ' ' + _(u'cm') + _(u'!'))
                                delaytime = int(tank_options['delay_duration'])
                                if delaytime > 0:                             # if there is no water in the tank and the stations stop, then we set the rain delay for this time for blocking
                                    rain_blocks[NAME] = datetime.datetime.now() + datetime.timedelta(hours=float(delaytime))
                                   
                        if level_in_tank > int(tank_options['water_minimum']) + 5 and not mini: # refresh send email if actual level > options minimum +5
                            mini = True
                        
                        if NAME in rain_blocks and level_in_tank > int(tank_options['water_minimum']):
                            del rain_blocks[NAME]

                        if tank_options['enable_log']:
                            millis = int(round(time.time() * 1000))
                            interval = (tank_options['log_interval'] * 60000)
                            if (millis - last_millis) > interval:
                               last_millis = millis
                               update_log()
                    else:
                        tempText =  _('FAULT')
                        log.clear(NAME)
                        log.info(NAME, datetime_string() + ' ' + _(u'Water level: Error.'))
                        log.info(NAME, str(tank_options['log_date_maxlevel']) + ' ' + _(u'Maximum Water level') + ': ' + str(tank_options['log_maxlevel']) + ' ' + _(u'cm') + _(u'.'))   
                        log.info(NAME, str(tank_options['log_date_minlevel']) + ' ' + _(u'Minimum Water level') + ': ' + str(tank_options['log_minlevel']) + ' ' + _(u'cm') + _(u'.'))    

                        if tank_options['use_water_err'] and three_text:   # if probe has error send email
                            three_text = False                                          
                            log.info(NAME, datetime_string() + ' ' + _(u'ERROR: Water probe has fault?'))
                               
                            msg = '<b>' + _(u'Water Tank Monitor plug-in') + '</b> ' + '<br><p style="color:red;">' + _(u'System detected error: Water probe has fault?') + '</p>'
                            msglog = _(u'Water Tank Monitor plug-in') + ': ' + _(u'System detected error: Water probe has fault?')  
                            try:
                                from plugins.email_notifications import try_mail                                    
                                try_mail(msg, msglog, attachment=None, subject=tank_options['emlsubject']) # try_mail(text, logtext, attachment=None, subject=None)

                            except Exception:     
                                log.error(NAME, _(u'Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())  

                        if tank_options['use_water_stop']:
                            if NAME not in rain_blocks:
                                set_stations_in_scheduler_off()
                                delaytime = int(tank_options['delay_duration'])
                                if delaytime > 0:                             # if probe has fault, then we set the rain delay for this time for blocking
                                    rain_blocks[NAME] = datetime.datetime.now() + datetime.timedelta(hours=float(delaytime))                            
       

                    if tank_options['enable_reg']:
                    	tempText += ', ' + regulation_text
                    tank_mon.val = tempText.encode('utf8')          # value on footer 

                    self._sleep(3)                      
                                        
                else:
                    if once_text:
                       log.clear(NAME)
                       log.info(NAME, _(u'Water tank monitor is disabled.'))
                       once_text = False
                       two_text = True
                       last_level = 0
                    self._sleep(1)  
                
                if send:
                    msg = '<b>' + _(u'Water Tank Monitor plug-in') + '</b> ' + '<br><p style="color:red;">' + _(u'System detected error: Water Tank has minimum Water Level') +  ': ' + str(tank_options['water_minimum']) + _(u'cm') + '.\n' + '</p>'
                    msglog = _(u'Water Tank Monitor plug-in') + ': ' + _(u'System detected error: Water Tank has minimum Water Level') +  ': ' + str(tank_options['water_minimum']) + _(u'cm') + '. '  
                    send = False                    
                    try:
                        from plugins.email_notifications import try_mail                                    
                        try_mail(msg, msglog, attachment=None, subject=tank_options['emlsubject']) # try_mail(text, logtext, attachment=None, subject=None)

                    except Exception:  
                        log.info(NAME, _(u'E-mail not send! The Email Notifications plug-in is not found in OSPy or not correctly setuped.'))    
                        log.error(NAME, _(u'Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())                        


            except Exception:
                log.clear(NAME)
                log.error(NAME, _(u'Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
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


def get_sonic_cm():
    try:
        import smbus
        bus = smbus.SMBus(1 if get_rpi_revision() >= 2 else 0)

        data = [2]
        data = try_io(lambda: bus.read_i2c_block_data(tank_options['address_ping'],2))
        cm = data[1] + data[0]*255
        return cm
    except:
        return -1   


def get_sonic_tank_cm(level):
    try:
        cm = level
        if cm < 0:
           return -1
       
        tank_cm = maping(cm,int(tank_options['distance_bottom']),int(tank_options['distance_top']),0,(int(tank_options['distance_bottom'])-int(tank_options['distance_top'])))
        if tank_cm >= 0:
           return tank_cm

        else:
           return -1 
    except:
        return -1 # if I2C device not exists


def get_tank(level): # return water tank level 0-100%, -1 is error i2c not found
    tank_lvl = level
    if tank_lvl >= 0:
       tank_proc = float(tank_lvl)/float(tank_options['distance_bottom']-tank_options['distance_top'])
       tank_proc = float(tank_proc)*100.0
       return int(tank_proc)
    else:
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
          volume = round(volume,2)         # round only two decimals
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

    return status['level'] , status['percent'], status['ping'], status['volume'], tank_options['log_minlevel'], tank_options['log_maxlevel'], tank_options['log_date_minlevel'], tank_options['log_date_maxlevel'], tank_options['check_liters']
   
 
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


def update_log():
    """Update data in json files.""" 

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
    data['minimum'] = str(tank_options['log_minlevel'])
    data['maximum'] = str(tank_options['log_maxlevel'])
    data['actual']  = str(get_all_values()[0])
    data['volume']  = str(get_all_values()[3])
      
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

    timestamp = int(time.time())

    try:
        minimum = graph_data[0]['balances']
        minval = {'total': tank_options['log_minlevel']}
        minimum.update({timestamp: minval})

        maximum = graph_data[1]['balances']
        maxval = {'total': tank_options['log_maxlevel']}
        maximum.update({timestamp: maxval})

        actual = graph_data[2]['balances']
        actval = {'total': get_all_values()[0]}
        actual.update({timestamp: actval})

        volume = graph_data[3]['balances']
        volumeval = {'total': get_all_values()[3]}
        volume.update({timestamp: volumeval})
 
        write_graph_log(graph_data)

        log.info(NAME, _(u'Saving to log  files OK'))
    except:
        create_default_graph()


def create_default_graph():
    """Create default graph json file."""

    minimum = _(u'Minimum')
    maximum = _(u'Maximum')
    actual  = _(u'Actual')
    volume  = _(u'Volume')
 
    graph_data = [
       {"station": minimum, "balances": {}},
       {"station": maximum, "balances": {}}, 
       {"station": actual,  "balances": {}},
       {"station": volume,  "balances": {}}
    ]
    write_graph_log(graph_data)
    log.info(NAME, _(u'Deleted all log files OK'))


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
        log.info(NAME, _(u'Stoping stations in scheduler'))


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        global sender, status

        qdict  = web.input()
        reset  = helpers.get_input(qdict, 'reset', False, lambda x: True)
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)
        show = helpers.get_input(qdict, 'show', False, lambda x: True)
        del_rain = helpers.get_input(qdict, 'del_rain', False, lambda x: True)

        if sender is not None and reset:
            tank_options.__setitem__('log_minlevel', status['level'])
            tank_options.__setitem__('log_maxlevel', status['level'])
            qm = datetime_string()
            tank_options.__setitem__('log_date_maxlevel', qm)
            tank_options.__setitem__('log_date_minlevel', qm)
            tank_options.__setitem__('log_date_maxlevel', qm)
            tank_options.__setitem__('log_date_minlevel', qm)
            if tank_options['use_sonic']:
                tank_options.__setitem__('use_sonic', u'on')
            if tank_options['check_liters']:
                tank_options.__setitem__('check_liters', u'on')
            if tank_options['enable_reg']:
                tank_options.__setitem__('enable_reg', u'on')
            if tank_options['enable_log']:
                tank_options.__setitem__('enable_log', u'on')
            if tank_options['use_stop']:
                tank_options.__setitem__('use_stop', u'on')
            if tank_options['use_send_email']:
                tank_options.__setitem__('use_send_email', u'on')
            if tank_options['use_water_stop']:
                tank_options.__setitem__('use_water_stop', u'on')
            log.info(NAME, datetime_string() + ': ' + _(u'Minimum and maximum has reseted.'))
            
            raise web.seeother(plugin_url(settings_page), True)

        if sender is not None and delete:
           write_log([])
           create_default_graph()
           raise web.seeother(plugin_url(settings_page), True)

        if sender is not None and 'history' in qdict:
           history = qdict['history']
           tank_options.__setitem__('history', int(history)) #__setitem__(self, key, value)

        if sender is not None and show:
            raise web.seeother(plugin_url(log_page), True)

        if sender is not None and del_rain:
            if NAME in rain_blocks:
                del rain_blocks[NAME]
                log.info(NAME, datetime_string() + ': ' + _(u'Removing Rain Delay') + '.')
            raise web.seeother(plugin_url(settings_page), True)

        return self.plugin_render.tank_monitor(tank_options, log.events(NAME))


    def POST(self):
        tank_options.web_update(web.input(**tank_options)) #for save multiple select

        if sender is not None:
            sender.update()

        if tank_options['use_sonic']:
            log.clear(NAME) 
            log.info(NAME, _(u'Water tank monitor is enabled.'))
        else:
            log.clear(NAME)
            log.info(NAME, _(u'Water tank monitor is disabled.'))

        log.info(NAME, _(u'Options has updated.'))
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.tank_monitor_help()

class log_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.tank_monitor_log(read_log(), tank_options)

class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(tank_options)


class data_json(ProtectedPage):
    """Returns plugin data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data =  {
          'level': get_all_values()[0],
          'percent':get_all_values()[1], 
          'ping': get_all_values()[2],    
          'volume': get_all_values()[3],
          'label': tank_options['emlsubject'],
          'unit': get_all_values()[4]
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
        #import datetime
        data = []
        
        epoch = datetime.date(1970, 1, 1)                                      # first date
        current_time  = datetime.date.today()                                  # actual date

        if tank_options['history'] == 0:                                       # without filtering
            web.header('Access-Control-Allow-Origin', '*')
            web.header('Content-Type', 'application/json')
            return json.dumps(read_graph_log())

        if tank_options['history'] == 1:
            check_start  = current_time - datetime.timedelta(days=1)           # actual date - 1 day
        if tank_options['history'] == 2:
            check_start  = current_time - datetime.timedelta(days=7)           # actual date - 7 day (week)
        if tank_options['history'] == 3:
            check_start  = current_time - datetime.timedelta(days=30)          # actual date - 30 day (month)
        if tank_options['history'] == 4:
            check_start  = current_time - datetime.timedelta(days=365)         # actual date - 365 day (year)                       

        log_start = int((check_start - epoch).total_seconds())                 # start date for log in second (timestamp)
                
        json_data = read_graph_log()

        for i in range(0, 4):                                                  # 0 = minimum, 1 = maximum, 2 = actual, 3 = volume
            temp_balances = {}
            for key in json_data[i]['balances']:
            	find_key =  int(key.encode('utf8'))                            # key is in unicode ex: u'1601347000' -> find_key is int number
                if find_key >= log_start:                                      # timestamp interval 
                    temp_balances[key] = json_data[i]['balances'][key]
            data.append({ 'station': json_data[i]['station'], 'balances': temp_balances })

        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(data)

class log_csv(ProtectedPage):  # save log file from web as csv file type
    """Simple Log API"""

    def GET(self):
        minimum = _(u'Minimum')
        maximum = _(u'Maximum')
        actual  = _(u'Actual')
        volume  = _(u'Volume')

        data  = "Date/Time"
        data += ";\t Date"
        data += ";\t Time"
        data += ";\t %s cm" % minimum
        data += ";\t %s cm" % maximum
        data += ";\t %s cm" % actual
        if tank_options['check_liters']:
            data += ";\t %s liters" % volume
        else:    
            data += ";\t %s m3" % volume
        data += '\n'        

        try:
            log_records = read_log()
            for record in log_records:
                data +=         record['datetime']
                data += ";\t" + record['date']
                data += ";\t" + record['time']
                data += ";\t" + record["minimum"]
                data += ";\t" + record["maximum"]
                data += ";\t" + record["actual"]
                data += ";\t" + record["volume"]
                data += '\n'
        except:
            pass        

        web.header('Content-Type', 'text/csv')
        return data
   
