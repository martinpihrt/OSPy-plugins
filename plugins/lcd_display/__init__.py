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

global blocker, L1web, L2web
blocker = False
L1web = ''
L2web = ''

NAME = 'LCD Display'
MENU =  _('Package: LCD Display')
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
        self._stop_event = Event()

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
        
        while not self._stop_event.is_set():
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
                            L1 = line1.decode('utf8')
                            log.info(NAME, L1)
                        if lcd_options['debug_line'] and line2 is not None:
                            L2 = line2.decode('utf8') 
                            log.info(NAME, L2)
                        self._sleep(2)

                    report_index += 2

                    time.sleep(0.1)

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
            self._lines = '{}'.format(text) + self._lines[len(text):]
        elif line == 2:
            self._lines = self._lines[:20] + '{}'.format(text) + self._lines[20 + len(text):]

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
        station_result += '{}'.format(station.index+1) + _(',') + ' ' # station number runing ex: 2, 6, 20,
    if station_state:
      return station_result
    else:
      return False

def maping(OldValue, OldMin, OldMax, NewMin, NewMax):
    ### Convert a number range to another range ###
    OldRange = OldMax - OldMin
    NewRange = NewMax - NewMin
    if OldRange == 0:
        NewValue = NewMin
    else:
        NewRange = NewMax - NewMin
        NewValue = (((OldValue - OldMin) * NewRange) / OldRange) + NewMin
    return NewValue

def get_tank_cm(level, dbot, dtop):
    ### Return level from top and bottom distance ###
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
    ### Return level 0-100% from top and bottom distance ###
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
            result = ASCI_convert(_('System:'))
        else: 
            result = None
    elif index == 1:
        if lcd_options['d_system_name']:
            result = ASCI_convert(options.name)
        else: 
            result = None
    elif index == 2:
        if lcd_options['d_sw_version_date']:
            result = ASCI_convert(_('SW Version:'))
        else: 
            result = None
    elif index == 3:
        if lcd_options['d_sw_version_date']:
            result = ASCI_convert('{} {}'.format(version.ver_str, version.ver_date))
        else: 
            result = None
    elif index == 4:
        if lcd_options['d_ip']:
            result = ASCI_convert(_('My IP is:'))
        else: 
            result = None
    elif index == 5:
        if lcd_options['d_ip']:
            if options.use_ssl or options.use_own_ssl:
                result = ASCI_convert(('https://{}:{}').format(helpers.get_ip(), options.web_port))
            else:
                result = ASCI_convert(('http://{}:{}').format(helpers.get_ip(), options.web_port))
        else: 
            result = None
    elif index == 6:
        if lcd_options['d_port']:
            result = ASCI_convert(_('My Port is:'))
        else: 
            result = None
    elif index == 7:
        if lcd_options['d_port']:
            result = ASCI_convert('{}'.format(options.web_port))
        else: 
            result = None
    elif index == 8:
        if lcd_options['d_cpu_temp']:
            result = ASCI_convert(_('CPU Temperature:'))
        else: 
            result = None
    elif index == 9:
        if lcd_options['d_cpu_temp']:
            result = ASCI_convert('{} {}'.format(helpers.get_cpu_temp(options.temp_unit), options.temp_unit))
        else: 
            result = None
    elif index == 10:
        if lcd_options['d_time_date']:
            result = ASCI_convert(_('Date:') + ' {}'.format(datetime.now().strftime('%d.%m.%Y')))
        else: 
            result = None
    elif index == 11:
        if lcd_options['d_time_date']:
            result = ASCI_convert(_('Time:') + ' {}'.format(datetime.now().strftime('%H:%M:%S')))
        else: 
            result = None
    elif index == 12:
        if lcd_options['d_uptime']:
            result = ASCI_convert(_('System Uptime:'))
        else: 
                result = None
    elif index == 13:
        if lcd_options['d_uptime']:
            result = ASCI_convert(helpers.uptime())
        else: 
            result = None
    elif index == 14:
        if lcd_options['d_rain_sensor']:
            result = ASCI_convert(_('Rain Sensor:'))
        else: 
            result = None
    elif index == 15:
        if lcd_options['d_rain_sensor']:
            if inputs.rain_sensed():
                result = ASCI_convert(_('Active'))
            else:
                result = ASCI_convert(_('Inactive'))
        else: 
            result = None
    elif index == 16:
        if lcd_options['d_last_run']:
            result = ASCI_convert(_('Last Program:'))
        else: 
            result = None
    elif index == 17:
        if lcd_options['d_last_run']:
            finished = [run for run in log.finished_runs() if not run['blocked']]
            if finished:
                str_fin= '{}{}'.format(finished[-1]['program_name'], finished[-1]['start'].strftime(' %d.%m.%Y %H:%M:%S'))
                result = ASCI_convert(str_fin) 
            else:
                result = ASCI_convert(_('None'))
        else: 
            result = None
    elif index == 18:
        if lcd_options['d_pressure_sensor']:
            result = ASCI_convert(_('Pressure Sensor:'))
        else: 
            result = None
    elif index == 19:
        if lcd_options['d_pressure_sensor']:
            try:
                from plugins import pressure_monitor
                state_press = pressure_monitor.get_check_pressure()
                if state_press:
                    result = ASCI_convert(_('Inactive'))
                else:
                    result = ASCI_convert(_('Active'))
            except Exception:
                result = ASCI_convert(_('Not Available'))
        else: 
            result = None
    elif index == 20:
        if lcd_options['d_water_tank_level']:
            result = ASCI_convert(_('Water Tank Level:'))
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
            except Exception:
                cm = -1
                percent = 0
                ping = -1
                volume = 0
                units = -1

            if cm > 0 and units != -1:
                result = ASCI_convert(_('Level') + ' {}'.format(cm) + _('cm') + ' {}'.format(percent) + _('%') + ' {}'.format(int(volume)))
                if units:
                    result += ASCI_convert(_('liter')) 
                else:
                    result += ASCI_convert(_('m3')) 
            elif units == -1:
                result = ASCI_convert(_('Not Available'))
            else:
                result = ASCI_convert(_('Error - I2C Device Not Found!'))
        else: 
            result = None
    elif index == 22:
        if lcd_options['d_temperature']:
            result = ASCI_convert(_('DS Temperature:'))
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
                        air_result += '{}:{} '.format(air_options['label_ds%d' % i], air_temp_humi.DS18B20_read_probe(i))
                    result = ASCI_convert(air_result)
                else:     
                    result = ASCI_convert(_('DS temperature not use'))
            except Exception:
                result = ASCI_convert(_('Not Available'))
        else: 
            result = None
    elif index == 24:
        if lcd_options['d_running_stations']:
            result = ASCI_convert(_('Station running:'))
        else: 
            result = None
    elif index == 25:
        if lcd_options['d_running_stations']:
            if get_active_state()==False:
                result = ASCI_convert(_('Nothing running')) 
            else:
                result = ASCI_convert(get_active_state())
        else:
            result = None
    elif index == 26:
        if lcd_options['d_sched_manu']:
            result = ASCI_convert(_('Control:'))
        else: 
            result = None
    elif index == 27:
        if lcd_options['d_sched_manu']:
            if options.manual_mode:
                result = ASCI_convert(_('Manual mode'))
            else:
                result = ASCI_convert(_('Scheduler'))
        else:
            result = None
    elif index == 28:
        if lcd_options['d_syst_enabl']:
            result = ASCI_convert(_('Scheduler:'))
        else: 
            result = None
    elif index == 29:
        if lcd_options['d_syst_enabl']:
            if options.scheduler_enabled:
                result = ASCI_convert(_('Enabled'))
            else:
                result = ASCI_convert(_('Disabled'))
        else:
            result = None
    ### OSPy sensors ###
    elif index == 30:
        if lcd_options['d_sensors']:
            result = ASCI_convert(_('Sensors:'))
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
                                    if sensor.last_read_value[4] == 1:
                                        sensor_result += _('Contact Closed')
                                    elif sensor.last_read_value[4] == 0:
                                        sensor_result += _('Contact Open')
                                    else:
                                        sensor_result += _('Probe Error')
                                if sensor.sens_type == 2:                               # leak detector
                                    if sensor.last_read_value[5] != -127:
                                        sensor_result += '{}'.format(sensor.last_read_value[5]) + ' ' + _('l/s')
                                    else:
                                        sensor_result += _('Probe Error')
                                if sensor.sens_type == 3:                               # moisture
                                    if sensor.last_read_value[6] != -127:
                                        sensor_result += '{}'.format(sensor.last_read_value[6]) + _('%')
                                    else:
                                        sensor_result += _('Probe Error')
                                if sensor.sens_type == 4:                               # motion
                                    if sensor.last_read_value[7] != -127:
                                        sensor_result += _('Motion Detected') if int(sensor.last_read_value[7])==1 else _('No Motion')
                                    else:
                                        sensor_result += _('Probe Error')
                                if sensor.sens_type == 5:                               # temperature
                                    if sensor.last_read_value[0] != -127:
                                        sensor_result += '{}'.format(sensor.last_read_value[0])
                                    else:
                                        sensor_result += _('Probe Error')
                                if sensor.sens_type == 6:                               # multi sensor
                                    if sensor.multi_type >= 0 and sensor.multi_type <4: # multi temperature DS1-DS4
                                        if sensor.last_read_value[sensor.multi_type] != -127: 
                                            sensor_result += '{}'.format(sensor.last_read_value[sensor.multi_type])
                                        else:
                                            sensor_result += _('Probe Error')
                                    if sensor.multi_type == 4:                          #  multi dry contact
                                        if sensor.last_read_value[4] != -127:
                                            sensor_result += _('Contact Closed') if int(sensor.last_read_value[4])==1 else _('Contact Open')
                                        else:
                                            sensor_result += _('Probe Error')
                                    if sensor.multi_type == 5:                          #  multi leak detector
                                        if sensor.last_read_value[5] != -127:
                                            sensor_result += '{}'.format(sensor.last_read_value[5]) + ' ' + _('l/s')
                                        else:
                                            sensor_result += _('Probe Error')
                                    if sensor.multi_type == 6:                          #  multi moisture
                                        if sensor.last_read_value[6] != -127:
                                            sensor_result += '{}'.format(sensor.last_read_value[6]) + ' ' + _('%')
                                        else:
                                            sensor_result += _('Probe Error')
                                    if sensor.multi_type == 7:                          #  multi motion
                                        if sensor.last_read_value[7] != -127:
                                            sensor_result += _('Motion Detected') if int(sensor.last_read_value[7])==1 else _('No Motion')
                                        else:
                                            sensor_result += _('Probe Error')
                                    if sensor.multi_type == 8:                          #  multi ultrasonic
                                        if sensor.last_read_value[8] != -127:
                                            get_level = get_tank_cm(sensor.last_read_value[8], sensor.distance_bottom, sensor.distance_top)
                                            get_perc = get_percent(get_level, sensor.distance_bottom, sensor.distance_top)
                                            sensor_result += '{}'.format(get_level) + ' ' +  _('cm') + ' (' + '{}'.format(get_perc) + ' %)'
                                        else:
                                            sensor_result += _('Probe Error')
                                    if sensor.multi_type == 9:                          #  multi soil moisture
                                        err_check = 0
                                        calculate_soil = [0.0]*16
                                        state = [-127]*16
                                        for i in range(0, 16):
                                            if type(sensor.soil_last_read_value[i]) == float:
                                                state[i] = sensor.soil_last_read_value[i]
                                                ### voltage from probe to humidity 0-100% with calibration range (for footer info)
                                                if sensor.soil_invert_probe_in[i]:                                  # probe: rotated state 0V=100%, 3V=0% humidity
                                                    calculate_soil[i] = maping(state[i], float(sensor.soil_calibration_max[i]), float(sensor.soil_calibration_min[i]), 0.0, 100.0)
                                                    calculate_soil[i] = round(calculate_soil[i], 1)                 # round to one decimal point
                                                    calculate_soil[i] = 100.0 - calculate_soil[i]                   # ex: 90% - 90% = 10%, 10% is output in invert probe mode
                                                else:                                                               # probe: normal state 0V=0%, 3V=100%
                                                    calculate_soil[i] = maping(state[i], float(sensor.soil_calibration_min[i]), float(sensor.soil_calibration_max[i]), 0.0, 100.0)
                                                    calculate_soil[i] = round(calculate_soil[i], 1)                 # round to one decimal point
                                                if state[i] > 0.1:
                                                    if sensor.soil_show_in_footer[i]:
                                                        sensor_result += '{} {}% ({}V) '.format(sensor.soil_probe_label[i], round(calculate_soil[i], 2), round(state[i], 2))
                                            else:
                                                err_check += 1
                                        if err_check > 15:
                                            sensor_result += _('Probe Error')
                            else:
                                sensor_result += sensor.name + ': ' + _('No response!')
                        else:
                            sensor_result += sensor.name + ': ' + _('Disabled')
                        if sensors.count() > 1:
                            sensor_result += ', '      
                    result = ASCI_convert(sensor_result)
                else:
                    result = ASCI_convert(_('No sensors available'))
            except Exception:
                result = ASCI_convert(_('Not Available'))
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

        for addr, pcf_type in search_range.items():
            try:
                # bus.write_quick(addr)
                try_io(lambda: bus.read_byte(addr)) #bus.read_byte(addr) # DF - write_quick doesn't work on BBB
                log.info(NAME, _('Found {} on address {}').format(pcf_type, hex(addr)))
                lcd_options['address'] = addr
                break
            except Exception:
                pass
        else:
            log.warning(NAME, _('Could not find any PCF8574 controller.'))

    except:
        log.warning(NAME, _('Could not import smbus.'))


def update_lcd(line1, line2=None):
    ### Print messages to LCD 16x2 ###
    global blocker, L1web, L2web

    if lcd_options['address'] == 0:
        find_lcd_address()

    if lcd_options['address'] != 0:
        from . import pylcd  # Library for LCD 16x2 PCF8574

        lcd = pylcd.lcd(lcd_options['address'], 0 if helpers.get_rpi_revision() == 1 else 1, lcd_options['hw_PCF8574']) # (address, bus, hw version for expander)
        # DF - alter RPi version test fallback to value that works on BBB
    else:
        lcd = dummy_lcd

    try_io(lambda: lcd.lcd_clear())
    sleep_time = 1
    L1web = line1
    L2web = line2
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

def notify_rebooted(name, **kw):
    ### Reboot Linux HW software ###
    try:
        global blocker, L1web, L2web
        blocker = True
        log.info(NAME, datetime_string() + ': ' + _('System rebooting'))
        if lcd_options['address'] == 0:
            find_lcd_address()
        if lcd_options['address'] != 0:
            from . import pylcd  # Library for LCD 16x2 PCF8574
            lcd = pylcd.lcd(lcd_options['address'], 0 if helpers.get_rpi_revision() == 1 else 1, lcd_options['hw_PCF8574']) # (address, bus, hw version for expander)
            # DF - alter RPi version test fallback to value that works on BBB
        else:
            lcd = dummy_lcd

        try_io(lambda: lcd.lcd_clear())    
        try_io(lambda: lcd.lcd_puts(ASCI_convert(_('System Linux')), 1))
        try_io(lambda: lcd.lcd_puts(ASCI_convert(_('Rebooting')), 2))
        L1web = ASCI_convert(_('System Linux'))
        L2web = ASCI_convert(_('Rebooting'))
    except:
        log.error(NAME, _('LCD display plug-in:') + '\n' + traceback.format_exc())

def notify_restarted(name, **kw):
    ### Restarted OSPy ###
    try:
        global blocker, L1web, L2web
        blocker = True
        log.info(NAME, datetime_string() + ': ' + _('System restarting'))
        if lcd_options['address'] == 0:
            find_lcd_address()
        if lcd_options['address'] != 0:
            from . import pylcd  # Library for LCD 16x2 PCF8574
            lcd = pylcd.lcd(lcd_options['address'], 0 if helpers.get_rpi_revision() == 1 else 1, lcd_options['hw_PCF8574']) # (address, bus, hw version for expander)
            # DF - alter RPi version test fallback to value that works on BBB
        else:
            lcd = dummy_lcd

        try_io(lambda: lcd.lcd_clear())
        try_io(lambda: lcd.lcd_puts(ASCI_convert(_('System OSPy')), 1))
        try_io(lambda: lcd.lcd_puts(ASCI_convert(_('Rebooting')), 2))
        L1web = ASCI_convert(_('System OSPy'))
        L2web = ASCI_convert(_('Rebooting'))
    except:
        log.error(NAME, _('LCD display plug-in:') + '\n' + traceback.format_exc())

def notify_poweroff(name, **kw):
    ### Power off Linux HW ###
    try:
        global blocker, L1web, L2web
        blocker = True
        log.info(NAME, datetime_string() + ': ' + _('System poweroff'))
        if lcd_options['address'] == 0:
            find_lcd_address()
        if lcd_options['address'] != 0:
            from . import pylcd  # Library for LCD 16x2 PCF8574
            lcd = pylcd.lcd(lcd_options['address'], 0 if helpers.get_rpi_revision() == 1 else 1, lcd_options['hw_PCF8574']) # (address, bus, hw version for expander)
            # DF - alter RPi version test fallback to value that works on BBB
        else:
            lcd = dummy_lcd

        try_io(lambda: lcd.lcd_clear())
        try_io(lambda: lcd.lcd_puts(ASCI_convert(_('System Linux')), 1))
        try_io(lambda: lcd.lcd_puts(ASCI_convert(_('Power off')), 2))
        L1web = ASCI_convert(_('System Linux'))
        L2web = ASCI_convert(_('Power off'))
    except:
        log.error(NAME, _('LCD display plug-in:') + '\n' + traceback.format_exc())

def notify_ospyupdate(name, **kw):
    ### OSPy new version availbale ###
    try:
        global blocker, L1web, L2web
        blocker = True
        log.info(NAME, datetime_string() + ': ' + _('System OSPy Has Update'))
        if lcd_options['address'] == 0:
            find_lcd_address()
        if lcd_options['address'] != 0:
            from . import pylcd  # Library for LCD 16x2 PCF8574
            lcd = pylcd.lcd(lcd_options['address'], 0 if helpers.get_rpi_revision() == 1 else 1, lcd_options['hw_PCF8574']) # (address, bus, hw version for expander)
            # DF - alter RPi version test fallback to value that works on BBB
        else:
            lcd = dummy_lcd

        try_io(lambda: lcd.lcd_clear())
        try_io(lambda: lcd.lcd_puts(ASCI_convert(_('System OSPy')), 1))
        try_io(lambda: lcd.lcd_puts(ASCI_convert(_('Has Update')), 2))
        L1web = ASCI_convert(_('System OSPy'))
        L2web = ASCI_convert(_('Has Update'))
    except:
        log.error(NAME, _('LCD display plug-in:') + '\n' + traceback.format_exc())

################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    ### Load an html page for entering lcd adjustments ###

    def GET(self):
        try:
            global lcd_sender

            qdict = web.input()
            refind = helpers.get_input(qdict, 'refind', False, lambda x: True)
            if lcd_sender is not None and refind:
                lcd_options['address'] = 0
                log.clear(NAME)
                log.info(NAME, _('I2C address has re-finded.'))
                find_lcd_address()
                raise web.seeother(plugin_url(settings_page), True)

            return self.plugin_render.lcd_display(lcd_options, log.events(NAME))
        except:
            log.error(NAME, _('LCD display plug-in:') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('lcd_display -> settings_page GET')
            return self.core_render.notice('/', msg)
 
    def POST(self):
        try:
            lcd_options.web_update(web.input())
            if lcd_sender is not None:
                lcd_sender.update()
            raise web.seeother(plugin_url(settings_page), True)
        except:
            log.error(NAME, _('LCD display plug-in:') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('lcd_display -> settings_page POST')
            return self.core_render.notice('/', msg)    

class help_page(ProtectedPage):
    ### Load an html page for help ###

    def GET(self):
        try:
            return self.plugin_render.lcd_display_help()
        except:
            log.error(NAME, _('LCD display plug-in:') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('lcd_display -> help_page GET')
            return self.core_render.notice('/', msg)

class settings_json(ProtectedPage):
    ### Returns plugin settings in JSON format ###

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(lcd_options)
        except:
            log.error(NAME, _('LCD display plug-in:') + ':\n' + traceback.format_exc())
            return {}

class lcd_json(ProtectedPage):
    """Returns seconds LCD state in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        global L1web, L2web
        data = {}
        try:
            data['L1'] = '{}'.format(L1web.decode('utf8'))
            data['L2'] = '{}'.format(L2web.decode('utf8'))
            return json.dumps(data)
        except:
            log.error(NAME, _('LCD display plug-in:') + ':\n' + traceback.format_exc())
            return data