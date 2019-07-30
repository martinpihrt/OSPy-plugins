
#!/usr/bin/env python
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

import i18n

NAME = 'LCD Display'
LINK = 'settings_page'

lcd_options = PluginOptions(
    NAME,
    {
        "use_lcd": True,
        "debug_line": False,
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

                    if report_index >= 25:
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
                log.error(NAME, _('LCD display plug-in:') + '\n' + traceback.format_exc())
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
        station_result += str(station.index+1) + ', ' # station number runing ex: 2, 6, 20,
    if station_state:
      return station_result
    else:
      return False


def get_report(index):
    result = None
    if (options.lang == 'cs_CZ'):
           if index == 0:  # start text to 16x1
             if lcd_options['d_system_name']:
                result = "ID systemu:"
             else: 
                result = None
           elif index == 1:
             if lcd_options['d_system_name']:
                result = options.name
             else:
                result = None 

           elif index == 2:
             if lcd_options['d_sw_version_date']:
                result = "FW Verze:"
             else: 
                result = None
           elif index == 3:
             if lcd_options['d_sw_version_date']:
                result = version.ver_str + ' (' + version.ver_date + ')' 
             else: 
                result = None

           elif index == 4:
             if lcd_options['d_ip']:
                result = "Mistni IP adresa:" 
             else: 
                result = None
           elif index == 5:
             if lcd_options['d_ip']:
                 ip = "http"
                 if options.use_ssl:
                    ip += "s"
                 ip += "://" + helpers.get_ip() + ':' + str(options.web_port)
                 result = str(ip)
             else: 
                result = None

           elif index == 6:
             if lcd_options['d_port']:
                result = "Port:"
             else: 
                result = None
           elif index == 7:
             if lcd_options['d_port']:
                result = str(options.web_port)
             else: 
                result = None

           elif index == 8:
             if lcd_options['d_cpu_temp']:
                result = "Teplota CPU:"
             else: 
                result = None
           elif index == 9:
             if lcd_options['d_cpu_temp']:
                result = helpers.get_cpu_temp(options.temp_unit) + ' ' + options.temp_unit
             else: 
                result = None

           elif index == 10:
             if lcd_options['d_time_date']:
                result = datetime.now().strftime('Dat %d.%m.%Y')
             else: 
                result = None
           elif index == 11:
             if lcd_options['d_time_date']:
                result = datetime.now().strftime('Cas %H:%M:%S')
             else: 
                result = None

           elif index == 12:
             if lcd_options['d_uptime']:
                result = "V provozu:"
             else: 
                result = None
           elif index == 13:
             if lcd_options['d_uptime']:
                result = helpers.uptime() 
             else: 
                result = None

           elif index == 14:
             if lcd_options['d_rain_sensor']:
                result = "Cidlo deste:"
             else: 
                result = None
           elif index == 15:
             if lcd_options['d_rain_sensor']:
                if inputs.rain_sensed():
                    result = "aktivni"
                else:
                    result = "neaktivni"
             else: 
                result = None

           elif index == 16:
             if lcd_options['d_last_run']:
                result = 'Naposledy bezel'
             else: 
                result = None
           elif index == 17:
             if lcd_options['d_last_run']:
                finished = [run for run in log.finished_runs() if not run['blocked']]
                if finished:
                   result = finished[-1]['start'].strftime('%d-%m-%Y v %H:%M:%S program: ') + finished[-1]['program_name']
                   result = result.replace('Run-Once', 'Jednorazovy')
                   result = result.replace('Manual', 'Rucne')
                else:
                   result = 'zadny program'
             else: 
                result = None

           elif index == 18:
             if lcd_options['d_pressure_sensor']:
                result = "Cidlo tlaku:"
             else: 
                result = None
           elif index == 19:
             if lcd_options['d_pressure_sensor']:
                try:
                   from plugins import pressure_monitor
                   state_press = pressure_monitor.get_check_pressure()
                   if state_press:
                      result = "neaktivni"
                   else:
                      result = "aktivni"

                except Exception:
                   result = "neni k dispozici"
             else: 
                result = None

           elif index == 20:    
             if lcd_options['d_water_tank_level']:    
                result = "Nadrz s vodou:"
             else: 
                result = None
           elif index == 21:
             if lcd_options['d_water_tank_level']:
                try:
                   from plugins import tank_humi_monitor
                   cm = tank_humi_monitor.get_sonic_tank_cm()
                   if cm > 0: 
                      result = str(cm) + ' cm'
                   else:
                      result = "chyba - I2C zarizeni nenalezeno!"

                except Exception:
                   result = "neni k dispozici"
             else: 
                result = None

           elif index == 22:    
             if lcd_options['d_temperature']:    
                result = "Teplota DS1-6:"
             else: 
                result = None
           elif index == 23:
             if lcd_options['d_temperature']:
                try:
                   from plugins import air_temp_humi
                 
                   result = air_temp_humi.DS18B20_read_string_data()
                  
                except Exception:
                   result = "neni k dispozici"
             else: 
                result = None

           elif index == 24:    
             if lcd_options['d_running_stations']:    
                result = "Stanice v chodu:"
             else: 
                result = None
           elif index == 25:
             if get_active_state()==False:   
                result = "nic nebezi" 
             else:
                result = get_active_state()

           return ASCI_convert(result)


    if (options.lang == 'sk_SK'):
           if index == 0:  # start text to 16x1
             if lcd_options['d_system_name']:
                result = "ID systemu:"
             else: 
                result = None
           elif index == 1:
             if lcd_options['d_system_name']:
                result = options.name
             else:
                result = None 

           elif index == 2:
             if lcd_options['d_sw_version_date']:
                result = "FW Verzia:"
             else: 
                result = None
           elif index == 3:
             if lcd_options['d_sw_version_date']:
                result = version.ver_str + ' (' + version.ver_date + ')' 
             else: 
                result = None

           elif index == 4:
             if lcd_options['d_ip']:
                result = "IP adresa:" 
             else: 
                result = None
           elif index == 5:
             if lcd_options['d_ip']:
                 ip = helpers.get_ip()
                 result = str(ip)
             else: 
                result = None

           elif index == 6:
             if lcd_options['d_port']:
                result = "Port:"
             else: 
                result = None
           elif index == 7:
             if lcd_options['d_port']:
                result = str(options.web_port)
             else: 
                result = None

           elif index == 8:
             if lcd_options['d_cpu_temp']:
                result = "Teplota CPU:"
             else: 
                result = None
           elif index == 9:
             if lcd_options['d_cpu_temp']:
                result = helpers.get_cpu_temp(options.temp_unit) + ' ' + options.temp_unit
             else: 
                result = None

           elif index == 10:
             if lcd_options['d_time_date']:
                result = datetime.now().strftime('Dat %d.%m.%Y')
             else: 
                result = None
           elif index == 11:
             if lcd_options['d_time_date']:
                result = datetime.now().strftime('Cas %H:%M:%S')
             else: 
                result = None

           elif index == 12:
             if lcd_options['d_uptime']:
                result = "V prevadzke:"
             else: 
                result = None
           elif index == 13:
             if lcd_options['d_uptime']:
                result = helpers.uptime() 
             else: 
                result = None

           elif index == 14:
             if lcd_options['d_rain_sensor']:
                result = "Cidlo dazda:"
             else: 
                result = None
           elif index == 15:
             if lcd_options['d_rain_sensor']:
                if inputs.rain_sensed():
                    result = "aktivny"
                else:
                    result = "neaktivny"
             else: 
                result = None

           elif index == 16:
             if lcd_options['d_last_run']:
                result = 'Naposledy bezal'
             else: 
                result = None
           elif index == 17:
             if lcd_options['d_last_run']:
                finished = [run for run in log.finished_runs() if not run['blocked']]
                if finished:
                   result = finished[-1]['start'].strftime('%d-%m-%Y v %H:%M:%S program: ') + finished[-1]['program_name']
                   result = result.replace('Run-Once', 'Jednorazovy')
                   result = result.replace('Manual', 'Rucne')
                else:
                   result = 'ziadny program'
             else: 
                result = None

           elif index == 18:
             if lcd_options['d_pressure_sensor']:
                result = "Cidlo tlaku:"
             else: 
                result = None
           elif index == 19:
             if lcd_options['d_pressure_sensor']:
                try:
                   from plugins import pressure_monitor
                   state_press = pressure_monitor.get_check_pressure()
                   if state_press:
                      result = "neaktivny"
                   else:
                      result = "aktivny"

                except Exception:
                   result = "neni k dispozicii"
             else: 
                result = None

           elif index == 20:    
             if lcd_options['d_water_tank_level']:    
                result = "Nadrz s vodou:"
             else: 
                result = None
           elif index == 21:
             if lcd_options['d_water_tank_level']:
                try:
                   from plugins import tank_humi_monitor
                   cm = tank_humi_monitor.get_sonic_tank_cm()
                   if cm > 0: 
                      result = str(cm) + ' cm'
                   else:
                      result = "chyba - I2C zarizeni nenajdene!"

                except Exception:
                   result = "neni k dispozicii"
             else: 
                result = None

           elif index == 22:    
             if lcd_options['d_temperature']:    
                result = "Teplota DS1-6:"
             else: 
                result = None
           elif index == 23:
             if lcd_options['d_temperature']:
                try:
                   from plugins import air_temp_humi
                 
                   result = air_temp_humi.DS18B20_read_string_data()
                  
                except Exception:
                   result = "neni k dispozicii"
             else: 
                result = None

           elif index == 24:    
             if lcd_options['d_running_stations']:    
                result = "Stanice v chode:"
             else: 
                result = None
           elif index == 25:
             if get_active_state()==False:   
                result = "nic nebezi" 
             else:
                result = get_active_state()

           return ASCI_convert(result)

    if (options.lang == 'en_US') or (options.lang == 'default'):
          if index == 0:  
             if lcd_options['d_system_name']:
                result = options.name
             else: 
                result = None
          elif index == 1:
             if lcd_options['d_system_name']:
                result = "Irrigation system"
             else: 
                result = None

          elif index == 2:
             if lcd_options['d_sw_version_date']:
                result = "SW Version:"
             else: 
                result = None
          elif index == 3:
             if lcd_options['d_sw_version_date']:
                result = version.ver_str + ' (' + version.ver_date + ')'
             else: 
                result = None

          elif index == 4:
             if lcd_options['d_ip']:
                result = "My IP is:"
             else: 
                result = None
          elif index == 5:
             if lcd_options['d_ip']:
                ip = helpers.get_ip()
                result = str(ip)
             else: 
                result = None

          elif index == 6:
             if lcd_options['d_port']:
                result = "My Port is:"
             else: 
                result = None
          elif index == 7:
             if lcd_options['d_port']:
                result = str(options.web_port)
             else: 
                result = None

          elif index == 8:
             if lcd_options['d_cpu_temp']:
                result = "CPU Temperature:"
             else: 
                result = None
          elif index == 9:
             if lcd_options['d_cpu_temp']:
                result = helpers.get_cpu_temp(options.temp_unit) + ' ' + options.temp_unit
             else: 
                result = None

          elif index == 10:
             if lcd_options['d_time_date']:
                result = datetime.now().strftime('Date: %d.%m.%Y')
             else: 
                result = None
          elif index == 11:
             if lcd_options['d_time_date']:
                result = datetime.now().strftime('Time: %H:%M:%S')
             else: 
                result = None

          elif index == 12:
             if lcd_options['d_uptime']:
                result = "System Uptime:"
             else: 
                result = None
          elif index == 13:
             if lcd_options['d_uptime']:
                result = helpers.uptime()
             else: 
                result = None

          elif index == 14:
             if lcd_options['d_rain_sensor']:
                result = "Rain Sensor:"
             else: 
                result = None
          elif index == 15:
             if lcd_options['d_rain_sensor']:
                if inputs.rain_sensed():
                   result = "Active"
                else:
                   result = "Inactive"
             else: 
                result = None

          elif index == 16:
             if lcd_options['d_last_run']:
                result = 'Last Program:'
             else: 
                result = None
          elif index == 17:
             if lcd_options['d_last_run']:
                finished = [run for run in log.finished_runs() if not run['blocked']]
                if finished:
                   result = finished[-1]['start'].strftime('%H:%M: ') + finished[-1]['program_name']
                   result = result.replace('Run-Once', 'Jednorazovy') 
                else:
                   result = 'None'
             else: 
                result = None

          elif index == 18:
             if lcd_options['d_pressure_sensor']:
                result = "Pressure Sensor:"
             else: 
                result = None
          elif index == 19:
             if lcd_options['d_pressure_sensor']:
                try:
                   from plugins import pressure_monitor
                   state_press = pressure_monitor.get_check_pressure()
                   if state_press:
                       result = "GPIO is HIGH"
                   else:
                       result = "GPIO is LOW"

                except Exception:
                   result = "Not Available"
             else: 
                result = None


          elif index == 20:    
             if lcd_options['d_water_tank_level']:        
                result = "Water Tank Level:"
             else: 
                result = None
          elif index == 21:
             if lcd_options['d_water_tank_level']:    
                try:
                   from plugins import tank_humi_monitor
                   cm = tank_humi_monitor.get_sonic_tank_cm()
                   if cm > 0: 
                      result = str(cm) + ' cm'
                   else:
                      result = "Error - I2C Device Not Found!"

                except Exception:
                   result = "Not Available"
             else: 
                result = None

          elif index == 22:    
            if lcd_options['d_temperature']:    
               result = "DS Temperature:"
            else: 
               result = None
          elif index == 23:
            if lcd_options['d_temperature']:
               try:
                  from plugins import air_temp_humi
                 
                  result = air_temp_humi.DS18B20_read_string_data()
                                     
               except Exception:
                  result = "Not Available"
            else: 
               result = None

          elif index == 24:    
            if lcd_options['d_running_stations']:    
               result = "Station running:"
            else: 
                result = None
          elif index == 25:
            if get_active_state()==False:   
               result = "nothing running" 
            else:
               result = get_active_state()

          return result


def find_lcd_address():
    search_range = {addr: 'PCF8574' for addr in range(32, 40)}
    search_range.update({addr: 'PCF8574A' for addr in range(56, 63)})

    try:
        import smbus

        bus = smbus.SMBus(0 if helpers.get_rpi_revision() == 1 else 1)
        # DF - alter RPi version test fallback to value that works on BBB
    except ImportError:
        log.warning(NAME, _('Could not import smbus.'))
    else:

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
            log.warning(NAME, _('Could not find any PCF8574 controller.'))


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
        sleep_time = 0.25


################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering lcd adjustments."""

    def GET(self):
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
