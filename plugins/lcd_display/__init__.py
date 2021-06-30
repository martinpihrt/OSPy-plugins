# -*- coding: utf-8 -*-

__author__ = 'Martin Pihrt'
# This plugin sends data to I2C for LCD 16x2 char with PCF8574.
# Visit for more: https://pihrt.com/elektronika/315-arduino-uno-deska-i2c-lcd-16x2.
# This plugin requires python pylcd.py library


import json
import time
import traceback
from datetime import datetime

from threading import Thread, Event

import web
from ospy import helpers
from ospy import version
from ospy.inputs import inputs
from ospy.options import options
from ospy.log import log
from plugins import PluginOptions, plugin_url
from ospy.webpages import ProtectedPage
from ospy.helpers import ASCI_convert, datetime_string
from ospy.stations import stations
from ospy.sensors import sensors

from blinker import signal

global blocker
blocker = False

NAME = 'LCD Display'
MENU =  _(u'Package: LCD Display')
LINK = 'settings_page'

lcd_options = PluginOptions(
    NAME,
    {
        "use_lcd": True,
        "debug_line": True,
        "address": 0,
        "d_system_name": True,
        "d_sw_version_date": True,
        "d_ip": True,
        "d_port": True,
        "d_cpu_temp": True,
        "d_time_date": True,
        "d_uptime": True,
        "d_rain_sensor": True,
        "d_last_run": True,
        "d_pressure_sensor": True,
        "d_water_tank_level": True,
        "d_running_stations": True,
        "d_temperature": True,
        "d_sched_manu": True,
        "d_syst_enabl": True,
        "d_sensors": True,
        "hw_PCF8574": 1               # 0-4, default is 1 LCD1602 china I2C display
    }
)


################################################################################
# Main function loop:                                                          #
################################################################################
class LCDSender(Thread):
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
        global blocker
        report_index = 0
        
        rebooted = signal('rebooted')
        rebooted.connect(notify_rebooted)

        restarted = signal('restarted')
        restarted.connect(notify_restarted)
        
        poweroff = signal('poweroff')
        poweroff.connect(notify_poweroff)

        ospyupdate = signal('ospyupdate')
        ospyupdate.connect(notify_ospyupdate)
        
        while not self._stop.is_set():
            try:
                if lcd_options['use_lcd']  and not blocker:  # if LCD plugin is enabled
                    if lcd_options['debug_line']:
                        log.clear(NAME)

                    line1 = get_report(report_index)
                    line2 = get_report(report_index + 1)

                    if report_index >= 31:
                        report_index = 0
                    
                    skip_lines = False
                    if line1 is None and line2 is None:
                        skip_lines = True

                    if not skip_lines:    
                        update_lcd(line1, line2)                                       
                        if lcd_options['debug_line'] and line1 is not None:
                            log.info(NAME, line1)
                        if lcd_options['debug_line'] and line2 is not None:
                            log.info(NAME, line2)

                        self._sleep(2)    

                    report_index += 2

                    time.sleep(0.1)

            except Exception:
                log.error(NAME, _(u'LCD display plug-in:') + '\n' + traceback.format_exc())
                self._sleep(5)


lcd_sender = None


class DummyLCD(object):
    def __init__(self):
        self._lines = (' ' * 17) + '/' + (' ' * 17)

    lcd_clear = __init__

    def lcd_puts(self, text, line):
        text = text[:16]
        if line == 1:
            self._lines = text + self._lines[len(text):]
        elif line == 2:
            self._lines = self._lines[:20] + text + self._lines[20 + len(text):]
        #log.debug('LCD', self._lines)


dummy_lcd = DummyLCD()

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global lcd_sender
    if lcd_sender is None:
        lcd_sender = LCDSender()


def stop():
    global lcd_sender
    if lcd_sender is not None:
        lcd_sender.stop()
        lcd_sender.join()
        lcd_sender = None


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


def get_active_state():
    station_state = False
    station_result = ''
    for station in stations.get(): # check if station runing
      if station.active:
        station_state = True       # yes runing
        station_result += str(station.index+1) + _(u',') + ' ' # station number runing ex: 2, 6, 20,
    if station_state:
      return station_result
    else:
      return False

def maping(x, in_min, in_max, out_min, out_max):
    """ Return value from range """
    return ((x - in_min) * (out_max - out_min)) / ((in_max - in_min) + out_min)

def get_tank_cm(level, dbot, dtop):
    """ Return level from top and bottom distance"""
    try:
        if level < 0:
            return -1
        tank = maping(level, int(dbot), int(dtop), 0, (int(dbot)-int(dtop)))
        if tank >= 0:
            return tank
        else:
            return -1
    except:
        return -1

def get_percent(level, dbot, dtop):
    """ Return level 0-100% from top and bottom distance"""
    try:
        if level >= 0:
            perc = float(level)/float((int(dbot)-int(dtop)))
            perc = float(perc)*100.0 
            if perc > 100.0:
                perc = 100.0
            if perc < 0.0:
                perc = -1.0
            return int(perc)
        else:
            return -1
    except:
        return -1        

def get_report(index):
    result = None

    if index == 0:  
        if lcd_options['d_system_name']:
            result = ASCI_convert(_(u'System:'))
        else: 
            result = None
    elif index == 1:
        if lcd_options['d_system_name']:
            result = ASCI_convert(options.name)
        else: 
            result = None
    elif index == 2:
        if lcd_options['d_sw_version_date']:
            result = ASCI_convert(_(u'SW Version:'))
        else: 
            result = None
    elif index == 3:
        if lcd_options['d_sw_version_date']:
            result = version.ver_str + ' ' + version.ver_date
        else: 
            result = None
    elif index == 4:
        if lcd_options['d_ip']:
            result = ASCI_convert(_(u'My IP is:'))
        else: 
            result = None
    elif index == 5:
        if lcd_options['d_ip']:
            ip = ASCI_convert(_(u'http'))
            if options.use_ssl:
                ip = ASCI_convert(_(u'https'))
            ip += ASCI_convert(_(u'://')) + helpers.get_ip() + _(u':') + str(options.web_port)
            result = str(ip)
        else: 
            result = None
    elif index == 6:
        if lcd_options['d_port']:
            result = ASCI_convert(_(u'My Port is:'))
        else: 
            result = None
    elif index == 7:
        if lcd_options['d_port']:
            result = str(options.web_port)
        else: 
            result = None
    elif index == 8:
        if lcd_options['d_cpu_temp']:
            result = ASCI_convert(_(u'CPU Temperature:'))
        else: 
            result = None
    elif index == 9:
        if lcd_options['d_cpu_temp']:
            result = helpers.get_cpu_temp(options.temp_unit) + ' ' + options.temp_unit
        else: 
            result = None
    elif index == 10:
        if lcd_options['d_time_date']:
            str_date = ASCI_convert(_(u'Date:')) + ' '
            result = str_date + datetime.now().strftime('%d.%m.%Y')
        else: 
            result = None
    elif index == 11:
        if lcd_options['d_time_date']:
            str_time = ASCI_convert(_(u'Time:')) + ' '
            result = str_time + datetime.now().strftime('%H:%M:%S')
        else: 
            result = None
    elif index == 12:
        if lcd_options['d_uptime']:
            result = ASCI_convert(_(u'System Uptime:'))
        else: 
                result = None
    elif index == 13:
        if lcd_options['d_uptime']:
            result = ASCI_convert(helpers.uptime())
        else: 
            result = None
    elif index == 14:
        if lcd_options['d_rain_sensor']:
            result = ASCI_convert(_(u'Rain Sensor:'))
        else: 
            result = None
    elif index == 15:
        if lcd_options['d_rain_sensor']:
            if inputs.rain_sensed():
                result = ASCI_convert(_(u'Active'))
            else:
                result = ASCI_convert(_(u'Inactive'))
        else: 
            result = None
    elif index == 16:
        if lcd_options['d_last_run']:
            result = ASCI_convert(_(u'Last Program:'))
        else: 
            result = None
    elif index == 17:
        if lcd_options['d_last_run']:
            finished = [run for run in log.finished_runs() if not run['blocked']]
            if finished:
                str_fin= ASCI_convert(finished[-1]['program_name']) + finished[-1]['start'].strftime(' %H:%M')
                result = ASCI_convert(str_fin) 
            else:
                result = ASCI_convert(_(u'None'))
        else: 
            result = None
    elif index == 18:
        if lcd_options['d_pressure_sensor']:
            result = ASCI_convert(_(u'Pressure Sensor:'))
        else: 
            result = None
    elif index == 19:
        if lcd_options['d_pressure_sensor']:
            try:
                from plugins import pressure_monitor
                state_press = pressure_monitor.get_check_pressure()
                if state_press:
                    result = ASCI_convert(_(u'Inactive'))
                else:
                    result = ASCI_convert(_(u'Active'))
            except Exception:
                result = ASCI_convert(_(u'Not Available'))
        else: 
            result = None
    elif index == 20:    
        if lcd_options['d_water_tank_level']:
            result = ASCI_convert(_(u'Water Tank Level:'))
        else: 
            result = None
    elif index == 21:
        if lcd_options['d_water_tank_level']:
            try:
                from plugins import tank_monitor
                cm = tank_monitor.get_all_values()[0]
                percent = tank_monitor.get_all_values()[1]
                ping = tank_monitor.get_all_values()[2]
                volume = tank_monitor.get_all_values()[3]
                units = tank_monitor.get_all_values()[4]
                if cm > 0: 
                    result = ASCI_convert(_(u'Level')) + ' ' + str(cm) + ASCI_convert(_(u'cm')) + ' ' + str(percent) + ASCI_convert(_(u'%')) + ' ' + str(int(volume))
                    if units:
                        result += ASCI_convert(_(u'liter'))# + ' ' + ASCI_convert(_(u'ping')) + ' ' + str(ping) + ASCI_convert(_(u'cm')) 
                    else:
                        result += ASCI_convert(_(u'm3'))# + ' ' + ASCI_convert(_(u'ping')) + ' ' + str(ping) + ASCI_convert(_(u'cm')) 
                else:
                    result = ASCI_convert(_(u'Error - I2C Device Not Found!'))
            except Exception:
                result = ASCI_convert(_(u'Not Available'))
        else: 
            result = None
    elif index == 22:
        if lcd_options['d_temperature']:
            result = ASCI_convert(_(u'DS Temperature:'))
        else: 
            result = None
    elif index == 23:
        if lcd_options['d_temperature']:
            try:
                from plugins import air_temp_humi
                air_options = air_temp_humi.plugin_options
                if air_options['ds_enabled']:
                    air_result = ''
                    for i in range(0, air_options['ds_used']):
                        air_result += u'%s' % air_options['label_ds%d' % i] + u': %s' % air_temp_humi.DS18B20_read_probe(i) + ' '
                    result = ASCI_convert(air_result)
                else:     
                    result = ASCI_convert(_(u'DS temperature not use'))
            except Exception:
                result = ASCI_convert(_(u'Not Available'))
        else: 
            result = None
    elif index == 24:
        if lcd_options['d_running_stations']:
            result = ASCI_convert(_(u'Station running:'))
        else: 
            result = None
    elif index == 25:
        if lcd_options['d_running_stations']:
            if get_active_state()==False:
                result = ASCI_convert(_(u'Nothing running')) 
            else:
                result = get_active_state()
        else:
            result = None
    elif index == 26:
        if lcd_options['d_sched_manu']:
            result = ASCI_convert(_(u'Control:'))
        else: 
            result = None
    elif index == 27:
        if lcd_options['d_sched_manu']:
            if options.manual_mode:
                result = ASCI_convert(_(u'Manual mode'))
            else:
                result = ASCI_convert(_(u'Scheduler'))
        else:
            result = None
    elif index == 28:
        if lcd_options['d_syst_enabl']:
            result = ASCI_convert(_(u'Scheduler:'))
        else: 
            result = None
    elif index == 29:
        if lcd_options['d_syst_enabl']:
            if options.scheduler_enabled:
                result = ASCI_convert(_(u'Enabled'))
            else:
                result = ASCI_convert(_(u'Disabled'))
        else:
            result = None
    ### OSPy sensors ###        
    elif index == 30:
        if lcd_options['d_sensors']:
            result = ASCI_convert(_(u'Sensors:'))
        else: 
            result = None
    elif index == 31:
        if lcd_options['d_sensors']:
            try:
                if sensors.count() > 0:
                    sensor_result = ''
                    for sensor in sensors.get():
                        if sensor.enabled:
                            if sensor.response == 1:
                                sensor_result += sensor.name + ': '
                                if sensor.sens_type == 1:                               # dry contact
                                    sensor_result += _(u'Contact Closed') if int(sensor.last_read_value[4])==1 else _(u'Contact Open')
                                if sensor.sens_type == 2:                               # leak detector
                                    if sensor.last_read_value[5] != -1.0 and sensor.last_read_value[5] != -127.0:
                                        sensor_result += str(sensor.last_read_value[5]) + ' ' + _(u'l/s')
                                    else:
                                        sensor_result += _(u'Probe Error')
                                if sensor.sens_type == 3:                               # moisture
                                    if sensor.last_read_value[6] != -1.0:
                                        sensor_result += str(sensor.last_read_value[6]) + _(u'%')
                                    else:
                                        sensor_result += _(u'Probe Error')
                                if sensor.sens_type == 4:                               # motion
                                    if sensor.last_read_value[7] != -1:
                                        sensor_result += _(u'Motion Detected') if int(sensor.last_read_value[7])==1 else _(u'No Motion')
                                    else:
                                        sensor_result += _(u'Probe Error')
                                if sensor.sens_type == 5:                               # temperature
                                    if sensor.last_read_value[0] != -127.0:
                                        sensor_result += str(sensor.last_read_value[0])
                                    else:
                                        sensor_result += _(u'Probe Error')
                                if sensor.sens_type == 6:                               # multi sensor
                                    if sensor.multi_type >= 0 and sensor.multi_type <4: # multi temperature DS1-DS4
                                        if sensor.last_read_value[sensor.multi_type] != -127.0: 
                                            sensor_result += str(sensor.last_read_value[sensor.multi_type])
                                        else:
                                            sensor_result += _(u'Probe Error')
                                    if sensor.multi_type == 4:                          #  multi dry contact
                                        if sensor.last_read_value[4] != -1.0  and sensor.last_read_value[4] != -127.0:
                                            sensor_result += _(u'Contact Closed') if int(sensor.last_read_value[4])==1 else _(u'Contact Open')
                                        else:
                                            sensor_result += _(u'Probe Error')
                                    if sensor.multi_type == 5:                          #  multi leak detector
                                        if sensor.last_read_value[5] != -1.0  and sensor.last_read_value[5] != -127.0:
                                            sensor_result += str(sensor.last_read_value[5]) + ' ' + _(u'l/s')
                                        else:
                                            sensor_result += _(u'Probe Error')
                                    if sensor.multi_type == 6:                          #  multi moisture
                                        if sensor.last_read_value[6] != -1.0  and sensor.last_read_value[6] != -127.0:
                                            sensor_result += str(sensor.last_read_value[6]) + _(u'%')
                                        else:
                                            sensor_result += _(u'Probe Error')
                                    if sensor.multi_type == 7:                          #  multi motion
                                        if sensor.last_read_value[7] != -1.0  and sensor.last_read_value[7] != -127.0:
                                            sensor_result += _(u'Motion Detected') if int(sensor.last_read_value[7])==1 else _(u'No Motion')
                                        else:
                                            sensor_result += _(u'Probe Error')
                                    if sensor.multi_type == 8:                          #  multi ultrasonic
                                        if sensor.last_read_value[8] != -1.0  and sensor.last_read_value[8] != -127.0:
                                            get_level = get_tank_cm(sensor.last_read_value[8], sensor.distance_bottom, sensor.distance_top)
                                            get_perc = get_percent(get_level, sensor.distance_bottom, sensor.distance_top)
                                            sensor_result += str(get_cm) + ' ' +  _(u'cm') + '(' + str(get_perc) + ' %)'
                                        else:
                                            sensor_result += _(u'Probe Error')
                            else:
                                sensor_result += sensor.name + ': ' + _(u'No response!')
                        else:
                            sensor_result += sensor.name + ': ' + _(u'Disabled')
                        if sensors.count() > 1:
                            sensor_result += ', '      
                    result = ASCI_convert(sensor_result)
                else:
                    result = ASCI_convert(_(u'No sensors available'))
            except Exception:
                result = ASCI_convert(_(u'Not Available'))
                print(traceback.format_exc())
        else: 
            result = None

    return result


def find_lcd_address():
    search_range = {addr: 'PCF8574' for addr in range(32, 40)}
    search_range.update({addr: 'PCF8574A' for addr in range(56, 63)})

    try:
        import smbus

        bus = smbus.SMBus(0 if helpers.get_rpi_revision() == 1 else 1)
        # DF - alter RPi version test fallback to value that works on BBB

        for addr, pcf_type in search_range.iteritems():
            try:
                # bus.write_quick(addr)
                try_io(lambda: bus.read_byte(addr)) #bus.read_byte(addr) # DF - write_quick doesn't work on BBB
                log.info(NAME, _(u'Found {} on address {}').format(pcf_type, hex(addr)))
                lcd_options['address'] = addr
                break
            except Exception:
                pass
        else:
            log.warning(NAME, _(u'Could not find any PCF8574 controller.'))

    except:
        log.warning(NAME, _(u'Could not import smbus.'))            


def update_lcd(line1, line2=None):
    """Print messages to LCD 16x2"""
    global blocker

    if lcd_options['address'] == 0:
        find_lcd_address()

    if lcd_options['address'] != 0:
        import pylcd  # Library for LCD 16x2 PCF8574

        lcd = pylcd.lcd(lcd_options['address'], 0 if helpers.get_rpi_revision() == 1 else 1, lcd_options['hw_PCF8574']) # (address, bus, hw version for expander)
        # DF - alter RPi version test fallback to value that works on BBB
    else:
        lcd = dummy_lcd

    try_io(lambda: lcd.lcd_clear())
    sleep_time = 1
    while line1 is not None and not blocker:
        try_io(lambda: lcd.lcd_puts(line1[:16], 1))

        if line2 is not None:
           try_io(lambda: lcd.lcd_puts(line2[:16], 2))

        if max(len(line1), len(line2)) <= 16:
           break
 
        if line1 is not None:
           if len(line1) > 16:
              line1 = line1[1:]

        if line2 is not None:
            if len(line2) > 16:
                line2 = line2[1:]

        time.sleep(sleep_time)
        sleep_time = 0.9

### Reboot Linux HW software ###
def notify_rebooted(name, **kw):
    global blocker
    blocker = True
    log.info(NAME, datetime_string() + ': ' + _(u'System rebooting'))
    if lcd_options['address'] == 0:
        find_lcd_address()
    if lcd_options['address'] != 0:
        import pylcd  # Library for LCD 16x2 PCF8574
        lcd = pylcd.lcd(lcd_options['address'], 0 if helpers.get_rpi_revision() == 1 else 1, lcd_options['hw_PCF8574']) # (address, bus, hw version for expander)
        # DF - alter RPi version test fallback to value that works on BBB
    else:
        lcd = dummy_lcd

    try_io(lambda: lcd.lcd_clear())    
    try_io(lambda: lcd.lcd_puts(ASCI_convert(_(u'System Linux')), 1))
    try_io(lambda: lcd.lcd_puts(ASCI_convert(_(u'Rebooting')), 2))

### Restarted OSPy ###
def notify_restarted(name, **kw):
    global blocker
    blocker = True
    log.info(NAME, datetime_string() + ': ' + _(u'System restarting'))
    if lcd_options['address'] == 0:
        find_lcd_address()
    if lcd_options['address'] != 0:
        import pylcd  # Library for LCD 16x2 PCF8574
        lcd = pylcd.lcd(lcd_options['address'], 0 if helpers.get_rpi_revision() == 1 else 1, lcd_options['hw_PCF8574']) # (address, bus, hw version for expander)
        # DF - alter RPi version test fallback to value that works on BBB
    else:
        lcd = dummy_lcd

    try_io(lambda: lcd.lcd_clear())    
    try_io(lambda: lcd.lcd_puts(ASCI_convert(_(u'System OSPy')), 1))
    try_io(lambda: lcd.lcd_puts(ASCI_convert(_(u'Rebooting')), 2))


### Power off Linux HW ###
def notify_poweroff(name, **kw):
    global blocker
    blocker = True
    log.info(NAME, datetime_string() + ': ' + _(u'System poweroff'))
    if lcd_options['address'] == 0:
        find_lcd_address()
    if lcd_options['address'] != 0:
        import pylcd  # Library for LCD 16x2 PCF8574
        lcd = pylcd.lcd(lcd_options['address'], 0 if helpers.get_rpi_revision() == 1 else 1, lcd_options['hw_PCF8574']) # (address, bus, hw version for expander)
        # DF - alter RPi version test fallback to value that works on BBB
    else:
        lcd = dummy_lcd

    try_io(lambda: lcd.lcd_clear())    
    try_io(lambda: lcd.lcd_puts(ASCI_convert(_(u'System Linux')), 1))
    try_io(lambda: lcd.lcd_puts(ASCI_convert(_(u'Power off')), 2))

### OSPy new version availbale ###
def notify_ospyupdate(name, **kw):
    global blocker
    blocker = True
    log.info(NAME, datetime_string() + ': ' + _(u'System OSPy Has Update'))
    if lcd_options['address'] == 0:
        find_lcd_address()
    if lcd_options['address'] != 0:
        import pylcd  # Library for LCD 16x2 PCF8574
        lcd = pylcd.lcd(lcd_options['address'], 0 if helpers.get_rpi_revision() == 1 else 1, lcd_options['hw_PCF8574']) # (address, bus, hw version for expander)
        # DF - alter RPi version test fallback to value that works on BBB
    else:
        lcd = dummy_lcd

    try_io(lambda: lcd.lcd_clear())    
    try_io(lambda: lcd.lcd_puts(ASCI_convert(_(u'System OSPy')), 1))
    try_io(lambda: lcd.lcd_puts(ASCI_convert(_(u'Has Update')), 2))    

################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering lcd adjustments."""

    def GET(self):
        global lcd_sender

        qdict = web.input()
        refind = helpers.get_input(qdict, 'refind', False, lambda x: True)
        if lcd_sender is not None and refind:
            lcd_options['address'] = 0
            log.clear(NAME)
            log.info(NAME, _(u'I2C address has re-finded.'))
            find_lcd_address()
            raise web.seeother(plugin_url(settings_page), True)

        return self.plugin_render.lcd_display(lcd_options, log.events(NAME))
        
 
    def POST(self):
        lcd_options.web_update(web.input())

        lcd_sender.update()
        raise web.seeother(plugin_url(settings_page), True)
        

class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.lcd_display_help()


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(lcd_options)
