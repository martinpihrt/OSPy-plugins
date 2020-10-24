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
from ospy.helpers import ASCI_convert
from ospy.stations import stations


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
        "hw_PCF8574": 4               # 0-4, default is 4 www.pihrt.com 16x2 LCD board: "https://pihrt.com/elektronika/315-arduino-uno-deska-i2c-lcd-16x2"
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
        report_index = 0
        while not self._stop.is_set():
            try:
                if lcd_options['use_lcd']:  # if LCD plugin is enabled
                    if lcd_options['debug_line']:
                        log.clear(NAME)

                    line1 = get_report(report_index)
                    line2 = get_report(report_index + 1)

                    if report_index >= 29:
                        report_index = 0

                    line1 = get_report(report_index)
                    line2 = get_report(report_index + 1)
                    
                    update_lcd(line1, line2)
                                           
                    if lcd_options['debug_line'] and line1 is not None:
                        log.info(NAME, line1)
                    if lcd_options['debug_line'] and line2 is not None:
                        log.info(NAME, line2)

                    report_index += 2

                self._sleep(2)

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
        if get_active_state()==False:   
            result = ASCI_convert(_(u'Nothing running')) 
        else:
            result = get_active_state()
    elif index == 26:    
        if lcd_options['d_sched_manu']:    
            result = ASCI_convert(_(u'Control:'))
        else: 
            result = None
    elif index == 27:
        if options.manual_mode:   
            result = ASCI_convert(_(u'Manual mode'))
        else:
            result = ASCI_convert(_(u'Scheduler'))
    elif index == 28:    
        if lcd_options['d_syst_enabl']:    
            result = ASCI_convert(_(u'Scheduler:'))
        else: 
            result = None
    elif index == 29:
        if options.scheduler_enabled:   
            result = ASCI_convert(_(u'Enabled')) 
        else:
            result = ASCI_convert(_(u'Disabled'))         

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
                log.info(NAME, 'Found %s on address 0x%02x' % (pcf_type, addr))
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
    while line1 is not None:
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


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(lcd_options)
