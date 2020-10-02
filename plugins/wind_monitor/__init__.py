# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# This plugins check wind speed in meter per second. 
# This plugin read data from I2C counter PCF8583 on I2C address 0x50. Max count PCF8583 is 1 milion pulses per seconds

import json
import time as time_
import datetime, time
import sys
import traceback
import os

from threading import Thread, Event

import web
from ospy.stations import stations
from ospy.options import options
from ospy.log import log, logEM
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string
from ospy import helpers

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer


NAME = 'Wind Speed Monitor'
MENU =  _('Package: Wind Speed Monitor')
LINK = 'settings_page'

wind_options = PluginOptions(
    NAME,
    {
        'use_wind_monitor': False,
        'address': False,            # True = 0x51, False = 0x50 for PCF8583
        'sendeml': True,             # True = send email with error
        'pulses': 2,                 # 2 pulses per rotation
        'metperrot': 1.492,          # 1.492 meter per hour per rotation
        'maxspeed': 20,              # 20 max speed to deactivate stations  
        'emlsubject': _('Report from OSPy WIND SPEED MONITOR plugin'),
        'log_speed': 0,              # actual speed
        'log_maxspeed': 0,           # maximal speed (log) in m/sec
        'log_date_maxspeed': _('Measuring...'), # maximal speed (date log)
        'enable_log': False,         # log to file and graph
        'log_interval': 1,           # log interval in minutes
        'log_records': 0,            # log records 0= unlimited 
        'use_kmh': False,            # measure in km/h or m/s
        'enable_log_change': False,  # enable save log max speed if max wind > last max wind
        'delete_max_24h': False,     # deleting max speed after 24 hours
        'history': 0                 # selector for graph history
    }
)


################################################################################
# Main function loop:                                                          #
################################################################################

class WindSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop = Event()
   
        self.status = {}
        self.status['meter'] = 0.0
        self.status['kmeter'] = 0.0
        self.status['max_meter'] = wind_options['log_maxspeed']

        self._sleep_time = 0
        self.start()

    def stop(self):
        self._stop.set()

    def update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop.is_set():
            time_.sleep(1)
            self._sleep_time -= 1

    def run(self):
        millis = int(round(time_.time() * 1000))

        last_millis = millis        # timer for save log
        last_clear_millis = millis  # last clear millis for timer
        send = False                # send email
        disable_text = True
        val = 0

        en_del_24h = True
           
        wind_mon = showInFooter() #  instantiate class to enable data in footer
        wind_mon.label = _('Wind Speed')            # label on footer
        wind_mon.val = '---'                        # value on footer
        wind_mon.button = "wind_monitor/settings"   # button redirect on footer

        while not self._stop.is_set():
            try:
                if wind_options['use_wind_monitor']:    # if wind plugin is enabled
                    disable_text = True
                    
                    try:
                        import smbus  # for PCF 8583
                        self.bus = smbus.SMBus(0 if helpers.get_rpi_revision() == 1 else 1) 

                    except ImportError:
                        log.warning(NAME, _('Could not import smbus.'))

                    if self.bus is not None:
                        set_counter(self.bus)     # set pcf8583 as counter
                        puls = counter(self.bus)  # read pulses

                    if puls is not None:                    
                        puls = counter(self.bus)/10.0           # counter value is value/10sec
                        val = puls/(wind_options['pulses']*1.0)
                        val = val*wind_options['metperrot']   

                        wind_options['log_speed'] = round(val,2)*1.0 # m/sec
                        
                        self.status['meter']  = round(val,2)*1.0
                        self.status['kmeter'] = round(val,2)*3.6                        

                        if self.status['meter'] > self.status['max_meter']:
                            self.status['max_meter'] = self.status['meter']
                            if wind_options['enable_log_change']:
                                update_log()

                            qdict = {} # save to options max speed and datetime

                            if wind_options['use_wind_monitor']:
                               qdict['use_wind_monitor'] = u'on' 
                            if wind_options['address']:
                               qdict['address']  = u'on'
                            if wind_options['sendeml']:     
                               qdict['sendeml'] = u'on' 
                            if wind_options['enable_log']:     
                               qdict['enable_log'] = u'on'      
                            if wind_options['use_kmh']: 
                               qdict['use_kmh'] = u'on'  
                            if wind_options['enable_log_change']:
                               qdict['enable_log_change'] = u'on' 
                            if wind_options['delete_max_24h']:
                               qdict['delete_max_24h'] = u'on'             

                            qdict['log_maxspeed'] = self.status['max_meter']         # m/sec
                            qmax = datetime_string()
                            qdict['log_date_maxspeed'] = qmax
                            wind_options['log_maxspeed'] = self.status['max_meter']  # m/sec 
                            wind_options['log_date_maxspeed'] = qmax  

                            wind_options.web_update(qdict)
 
                        log.info(NAME, datetime_string())
                        if wind_options['use_kmh']:
                            log.info(NAME, _('Speed') + ': ' + str(self.status['meter']*3.6) + ' ' + _('km/h') + ', ' + _('Pulses') + ': ' + str(puls) + ' ' + _('pulses/sec'))                  
                        else:
                            log.info(NAME, _('Speed') + ': ' + str(self.status['meter']) + ' ' + _('m/sec') + ', ' + _('Pulses') + ': ' + str(puls) + ' ' + _('pulses/sec'))  

                        if wind_options['use_kmh']:
                            log.info(NAME, str(wind_options['log_date_maxspeed']) + ' ' + _('Maximal speed') + ': ' + str(wind_options['log_maxspeed']*3.6) + ' ' + _('km/h'))  
                        else:    
                            log.info(NAME, str(wind_options['log_date_maxspeed']) + ' ' + _('Maximal speed') + ': ' + str(wind_options['log_maxspeed']) + ' ' + _('m/sec'))  
            
                        if self.status['meter'] >= 42: 
                            log.error(NAME, datetime_string() + ' ' + _('Wind speed > 150 km/h (42 m/sec)'))
                                     
                        if get_station_is_on():                               # if station is on
                            if self.status['meter'] >= int(wind_options['maxspeed']):          # if wind speed is > options max speed
                                log.finish_run(None)                          # save log
                                stations.clear()                              # set all station to off
                                log.clear(NAME)
                                log.info(NAME, datetime_string() + ' ' + _('Stops all stations and sends e-mail if enabled sends e-mail.'))
                                if wind_options['sendeml']:                   # if enabled send email
                                    send = True  

                        millis = int(round(time_.time() * 1000))
 
                        if wind_options['enable_log']:                        # if logging
                            interval = (wind_options['log_interval'] * 60000)
                            if (millis - last_millis) >= interval:
                               last_millis = millis
                               update_log()

                        if (millis - last_clear_millis) >= 120000:            # after 120 second deleting in status screen
                               last_clear_millis = millis 
                               log.clear(NAME)  

                        if wind_options['delete_max_24h']:                    # if enable deleting max after 24 hours (86400000 ms)
                            from datetime import datetime, time
                            now = datetime.now()
                            now_time = now.time()
                            if now_time >= time(0,0) and now_time <= time(0,2) and en_del_24h: # is time for deleting only in time 00:00:00 - 00:02:00    
                                en_del_24h = False

                                qdict = {}
                                if wind_options['use_wind_monitor']:
                                    qdict['use_wind_monitor'] = u'on' 
                                if wind_options['address']:
                                    qdict['address']  = u'on'
                                if wind_options['sendeml']:     
                                    qdict['sendeml'] = u'on' 
                                if wind_options['enable_log']:
                                    qdict['enable_log'] = u'on' 
                                if wind_options['use_kmh']: 
                                    qdict['use_kmh'] = u'on'        
                                if wind_options['enable_log_change']:
                                    qdict['enable_log_change'] = u'on'    
                                if wind_options['delete_max_24h']:
                                    qdict['delete_max_24h'] = u'on'             
                                qdict['log_maxspeed'] = 0
                                qdict['log_date_maxspeed'] = datetime_string()
                                wind_options['log_maxspeed'] = 0
                                wind_options['log_date_maxspeed'] = datetime_string()
                                log.info(NAME, datetime_string() + ' ' + _('Deleting maximal speed after 24 hours.'))
                                update_log()
                        else:
                            en_del_24h = True        

                        tempText = ""
                        if wind_options['use_kmh']:
                            tempText += str(self.status['kmeter']) + ' ' + _(u'km/h')
                        else:
                            tempText +=  str(self.status['meter']) + ' ' + _(u'm/s')    
                        wind_mon.val = tempText.encode('utf8')                # value on footer
                        
                    else:
                        self._sleep(1)                                
                                      
                else:
                    # text on the web if plugin is disabled
                    if disable_text:  
                        log.clear(NAME)
                        log.info(NAME, _('Wind speed monitor plug-in is disabled.'))
                        disable_text = False   
                    self._sleep(1)                        

                if send:
                    msg = '<b>' + _('Wind speed monitor plug-in') + '</b> ' + '<br><p style="color:red;">' + _('System detected error: wind speed monitor. All stations set to OFF. Wind is') + ': ' + str(round(val*3.6,2)) + ' km/h. </p>'
                    msglog= _('System detected error: wind speed monitor. All stations set to OFF. Wind is') + ': ' + str(round(val,2)*3.6) + ' km/h.'
                    send = False
                    try:
                        from plugins.email_notifications import try_mail                                    
                        try_mail(msg, msglog, attachment=None, subject=wind_options['emlsubject']) # try_mail(text, logtext, attachment=None, subject=None)

                    except Exception:     
                        log.error(NAME, _('Wind Speed monitor plug-in') + ':\n' + traceback.format_exc()) 

                

            except Exception:
                log.clear(NAME)
                log.error(NAME, _('Wind Speed monitor plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)


wind_sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global wind_sender
    if wind_sender is None:
        wind_sender = WindSender()


def stop():
    global wind_sender
    if wind_sender is not None:
        wind_sender.stop()
        wind_sender.join()
        wind_sender = None


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
            time.sleep(0.01)
        else:
            break

    if not tries:
        raise error

    return result


def set_counter(i2cbus):
    try:
    	addr = 0
        if wind_options['address']:
            addr = 0x51
        else:
            addr = 0x50

        #i2cbus.write_byte_data(addr, 0x00, 0x20) # status registr setup to "EVENT COUNTER"
        #i2cbus.write_byte_data(addr, 0x01, 0x00) # reset LSB
        #i2cbus.write_byte_data(addr, 0x02, 0x00) # reset midle Byte
        #i2cbus.write_byte_data(addr, 0x03, 0x00) # reset MSB
        
        try_io(lambda: i2cbus.write_byte_data(addr, 0x00, 0x20)) # status registr setup to "EVENT COUNTER"
        try_io(lambda: i2cbus.write_byte_data(addr, 0x01, 0x00)) # reset LSB
        try_io(lambda: i2cbus.write_byte_data(addr, 0x02, 0x00)) # reset midle Byte
        try_io(lambda: i2cbus.write_byte_data(addr, 0x03, 0x00)) # reset MSB
        log.debug(NAME, _('Wind speed monitor plug-in') + ': ' + _('Setup PCF8583 as event counter - OK')) 

    except:
        log.error(NAME, _('Wind speed monitor plug-in') + ':\n' + _('Setup PCF8583 as event counter - FAULT'))
        log.error(NAME, _('Wind speed monitor plug-in') + traceback.format_exc())


def counter(i2cbus): # reset PCF8583, measure pulses and return number pulses per second
    try:
        pulses = 0
    	addr = 0
        
        if wind_options['address']:
            addr = 0x51
        else:
            addr = 0x50

        # reset PCF8583
        try_io(lambda: i2cbus.write_byte_data(addr, 0x01, 0x00)) # reset LSB
        try_io(lambda: i2cbus.write_byte_data(addr, 0x02, 0x00)) # reset midle Byte
        try_io(lambda: i2cbus.write_byte_data(addr, 0x03, 0x00)) # reset MSB
        time_.sleep(10)
        # read number (pulses in counter) and translate to DEC
        counter = try_io(lambda: i2cbus.read_i2c_block_data(addr, 0x00))
        num1 = (counter[1] & 0x0F)             # units
        num10 = (counter[1] & 0xF0) >> 4       # dozens
        num100 = (counter[2] & 0x0F)           # hundred
        num1000 = (counter[2] & 0xF0) >> 4     # thousand
        num10000 = (counter[3] & 0x0F)         # tens of thousands
        num100000 = (counter[3] & 0xF0) >> 4   # hundreds of thousands
        pulses = (num100000 * 100000) + (num10000 * 10000) + (num1000 * 1000) + (num100 * 100) + (num10 * 10) + num1
        return pulses

    except:
        log.error(NAME, _('Wind speed monitor plug-in') + traceback.format_exc())
        time_.sleep(10)
        return None


def get_station_is_on(): # return true if stations is ON
    if not options.manual_mode:                   # if not manual control
        for station in stations.get():
                if station.active:                # if station is active
                    return True
                else:
                    return False


def get_all_values():
    st = wind_sender.status

    if wind_options['use_kmh']:
        return st['meter']*3.6, st['max_meter']*3.6, wind_options['log_date_maxspeed']  # km/hod
    else:
        return st['meter'], st['max_meter'], wind_options['log_date_maxspeed']          # m/sec


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
    data['maximum'] = str(get_all_values()[1])
    data['actual']  = str(get_all_values()[0])
      
    log_data.insert(0, data)
    if wind_options['log_records'] > 0:
        log_data = log_data[:wind_options['log_records']]

    write_log(log_data)

    ### Data for graph log ###
    try:  
        graph_data = read_graph_log()    
    except: 
        create_default_graph()
        graph_data = read_graph_log()

    timestamp = int(time_.time())

    try:
        maximum = graph_data[0]['balances']
        maxval = {'total': get_all_values()[1]}
        maximum.update({timestamp: maxval})

        actual = graph_data[1]['balances']
        actval = {'total': get_all_values()[0]}
        actual.update({timestamp: actval})
    except:
        maximum = 0
        maxval = {'total': get_all_values()[1]}
        maximum.update({timestamp: maxval})
        actual = graph_data[1]['balances']
        actval = {'total': get_all_values()[0]}
        actual.update({timestamp: actval})
 
    write_graph_log(graph_data)

    log.info(NAME, datetime_string() + ' ' + _('Saving to log  files OK'))


def create_default_graph():
    """Create default graph json file."""

    maximum = _('Maximum')
    actual  = _('Actual')
 
    graph_data = [
       {"station": maximum, "balances": {}}, 
       {"station": actual, "balances": {}}
    ]
    write_graph_log(graph_data)  
    log.debug(NAME,datetime_string() + ' ' + _('Creating default graph log files OK'))                


################################################################################
# Web pages:                                                                   #
################################################################################


class settings_page(ProtectedPage):
    """Load an html page for entering wind speed monitor settings."""

    def GET(self):
        global wind_sender

        qdict = web.input()
        reset = helpers.get_input(qdict, 'reset', False, lambda x: True)
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)

        if wind_sender is not None and reset:
            if wind_options['use_wind_monitor']:
                qdict['use_wind_monitor'] = u'on' 
            if wind_options['address']:
                qdict['address']  = u'on'
            if wind_options['sendeml']:     
                qdict['sendeml'] = u'on' 
            if wind_options['enable_log']:
                qdict['enable_log'] = u'on' 
            if wind_options['use_kmh']: 
                qdict['use_kmh'] = u'on'        
            if wind_options['enable_log_change']:
                qdict['enable_log_change'] = u'on'    
            if wind_options['delete_max_24h']:
                qdict['delete_max_24h'] = u'on'             
            qdict['log_maxspeed'] = 0
            qdict['log_date_maxspeed'] = datetime_string()
            wind_options['log_maxspeed'] = 0
            wind_options['log_date_maxspeed'] = datetime_string()  

            wind_options.web_update(qdict)   

            log.clear(NAME)
            log.info(NAME, datetime_string() + ' ' + _('Maximal speed has reseted.'))
            
            raise web.seeother(plugin_url(settings_page), True)

        if wind_sender is not None and delete:
           write_log([])
           create_default_graph()
           log.info(NAME, datetime_string() + ' ' + _('Deleted all log files OK'))

           raise web.seeother(plugin_url(settings_page), True)

        return self.plugin_render.wind_monitor(wind_options, wind_sender.status, log.events(NAME))

    def POST(self):
        wind_options.web_update(web.input())

        if wind_sender is not None:
            wind_sender.update()

        if wind_options['use_wind_monitor']:
            log.clear(NAME) 
            log.info(NAME, _('Wind monitor is enabled.'))
        else:
            log.clear(NAME)
            log.info(NAME, _('Wind monitor is disabled.'))

        log.info(NAME, datetime_string() + ' ' + _('Options has updated.'))

        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(wind_options)


class data_json(ProtectedPage):
    """Returns plugin data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data =  {
          'log_maxspeed': round(wind_options['log_maxspeed'],2),    # in m/sec
          'log_speed': round(wind_options['log_speed'],2),          # in m/sec
          'log_date_maxspeed': wind_options['log_date_maxspeed'],
          'label': wind_options['emlsubject']
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
        data = []
        
        epoch = datetime.date(1970, 1, 1)                                      # first date
        current_time  = datetime.date.today()                                  # actual date

        if wind_options['history'] == 0:                                       # without filtering
            web.header('Access-Control-Allow-Origin', '*')
            web.header('Content-Type', 'application/json')
            return json.dumps(read_graph_log())

        if wind_options['history'] == 1:
            check_start  = current_time - datetime.timedelta(days=1)           # actual date - 1 day
        if wind_options['history'] == 2:
            check_start  = current_time - datetime.timedelta(days=7)           # actual date - 7 day (week)
        if wind_options['history'] == 3:
            check_start  = current_time - datetime.timedelta(days=30)          # actual date - 30 day (month)
        if wind_options['history'] == 4:
            check_start  = current_time - datetime.timedelta(days=365)         # actual date - 365 day (year)                       

        log_start = int((check_start - epoch).total_seconds())                 # start date for log in second (timestamp)
                
        try:  
            json_data = read_graph_log()    
        except: 
            create_default_graph()
            json_data = read_graph_log()

        for i in range(0, 2):                                                  # 0 = maximum, 2 = actual
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
        maximum = _('Maximum')
        actual  = _('Actual')

        data  = "Date/Time"
        data += ";\t Date"
        data += ";\t Time"
        if wind_options['use_kmh']: 
            data += ";\t %s km/h" % maximum
            data += ";\t %s km/h" % actual
        else:                       
            data += ";\t %s m/sec" % maximum
            data += ";\t %s m/sec" % actual
        data += '\n'

        try:
            log_records = read_log()

            for record in log_records:
                data +=         record['datetime']
                data += ";\t" + record['date']
                data += ";\t" + record['time']
                data += ";\t" + record["maximum"]
                data += ";\t" + record["actual"]
                data += '\n'
        except:
            pass                  

        web.header('Content-Type', 'text/csv')
        return data


