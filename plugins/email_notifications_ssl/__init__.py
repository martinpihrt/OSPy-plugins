# !/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import re
import time
from datetime import datetime
import os
import os.path
import traceback
import smtplib
import ssl
from threading import Thread, Lock
from random import randint

# standard library imports
from email.encoders import encode_base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.multipart import MIMEBase
from email.message import EmailMessage

# local module imports
import web
from ospy.webpages import ProtectedPage
from plugins import PluginOptions, plugin_url, plugin_data_dir, get_runtime
from ospy.options import options
from ospy.stations import stations
from ospy.log import log, EVENT_FILE, logEM
from ospy.helpers import datetime_string, get_input, verify_csrf
from ospy.sensors import sensors

from blinker import signal


NAME = 'E-mail Notifications SSL'
MENU =  _('Package: E-mail Notifications SSL')
LINK = 'settings_page'
SMTP_TIMEOUT = 10
QUEUE_RETRY_INTERVAL = 10000
QUEUE_FAILURE_INTERVAL = 60000
QUEUE_FAILURE_INTERVAL_MAX = 300000
MAIN_LOOP_SLEEP = 5
PLUGIN_VERSION = '1.1.1'

email_options = PluginOptions(
    NAME,
    {
        'emlpwron': False,              # after power on
        'emllog': False,                # with events.log file
        'emlrain': False,               # rain is activated 
        'emlrainde': False,             # rain is deactivated
        'emlrun': False,                # program has finished
        'emlrdr': False,                # rain delay has expired
        'emlrds': False,                # rain delay has setuped
        'emlusrin': False,              # user logged in
        'eml_plug_tank': False,         # Send data from plugin sonic tank monitor
        'eml_plug_4tank': False,        # Send data from plugin current loop tanks monitor
        'eml_plug_wcounter': False,     # Send data from plugin water consumption counter
        'eml_plug_6ds': False,          # Send data from plugin air temp humidity 6x DS18b20 
        'eml_plug_sensors': False,      # Send data from OSPy sensors
        'eml_plug_shelly': False,       # Send data from Shelly sensors
        'emlserver': 'smtp.seznam.cz',  # SMTP server address
        'emlport': 465,                 # SSL layer (number in range 0-65535)
        'emlusr': '',                   # SMTP username
        'emlpwd': '',                   # SMTP password
        'emlsender': True,              # some SMTP providers prohibit to use another sender than the same mail user
        'emladr0': '',
        'emladr1': '',
        'emladr2': '',
        'emladr3': '',
        'emladr4': '',
        'emlsubject': _('Report from OSPy SYSTEM'),
        'emlrepeater': True             # save and send it later
    }
)

global saved_emails
runtime = get_runtime()
health_lock = Lock()
health_state = {
    'last_success': 0,
    'last_error': 0,
    'last_error_message': '',
}
signals_connected = False


def html_heading(text):
    return '<br><b>' + text + '</b>'


def html_line(text):
    return '<br>&nbsp;&nbsp;' + text


def virtual_water_meter_section(run):
    """Build an optional completed-run report from Water Consumption Counter."""
    try:
        from plugins import water_consumption_counter
        duration = max(0.0, (run['end'] - run['start']).total_seconds())
        report = water_consumption_counter.get_run_report(
            run['station'], duration, run.get('control_master')
        )
        if not report:
            return '', ''

        heading = _('Virtual water meter')
        lines = [
            _('Master') + ': ' + report['master_name'],
            _('Master consumption during this station run') + ': ' +
            report['master_run_display'],
            _('Total master consumption') + ': ' +
            report['master_total_display'],
            _('Station consumption') + ' (' + report['station_name'] + '): ' +
            report['station_run_display'],
        ]
        body = html_heading(heading)
        for line in lines:
            body += html_line(line)
        logtext = heading + '-> \n' + '\n'.join(lines) + '\n'
        return body, logtext
    except (ImportError, AttributeError):
        log.debug(NAME, _('Cannot import plugin: water consumption counter.'))
    except Exception:
        log.debug(
            NAME,
            _('Virtual water meter data is not available.') + '\n' +
            traceback.format_exc()
        )
    return '', ''


################################################################################
# Main function loop:                                                          #
################################################################################
class EmailSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event

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
        self._sleep(randint(3, 10))  # Wait until startup information is printed.

        send_interval = QUEUE_RETRY_INTERVAL # default time for sending between e-mails (ms)
        last_millis   = 0     # timer for repeating sending e-mails (ms)
        queue_failures = 0
        body    = ''
        logtext = ''
        finished_count = len([run for run in log.finished_runs() if not run['blocked']])

        if email_options["emlpwron"]:  # if eml_power_on send email is enable (on)
            body += '<b>' + datetime_string() + '</b>'
            body += '<br><p style="color:red;">' + _('System was powered on.') + '</p>'
            body += add_to_body_local_ospy_name()
            logtext = _('System was powered on.')

            if email_options["emllog"]:
                file_exists = os.path.exists(EVENT_FILE)
                if file_exists:
                   try_mail(body, logtext, EVENT_FILE)
                else:
                   body += '<br>' + _('Error - events.log file not exists!')
                   try_mail(body, logtext)
            else:
                try_mail(body, logtext)

        while not self._stop_event.is_set():
            body    = ''
            logtext = ''
            try:
                # Send E-mail if a new finished run is found
                if email_options["emlrun"]:
                    finished = [run for run in log.finished_runs() if not run['blocked']]
                    if len(finished) > finished_count:
                        for run in finished[finished_count:]:
                            duration = (run['end'] - run['start']).total_seconds()
                            minutes, seconds = divmod(duration, 60)
                            pname = run['program_name']
                            sname = stations.get(run['station']).name
                            body += '<br>'
                            body += '<b>' + datetime_string() + '</b>' 
                            body += '<br><b>'  + _('Finished run') + '</b>'
                            body += html_line(_('Program') + ': %s' % pname)
                            body += html_line(_('Station') + ': %s' % sname)
                            body += html_line(_('Start time') + ': %s' % datetime_string(run['start']))
                            body += html_line(_('Duration') + ': %02d:%02d' % (minutes, seconds))
                            body += add_to_body_local_ospy_name()
                            logtext  =  _('Finished run') + '-> \n' + _('Program') + ': %s\n' % pname 
                            logtext +=  _('Station') + ': %s\n' % sname
                            logtext +=  _('Start time') + ': %s \n' % datetime_string(run['start'])
                            logtext +=  _('Duration') + ': %02d:%02d\n' % (minutes, seconds)

                            # Send data from plugin sonic tank monitor
                            try:
                                if email_options["eml_plug_tank"]:
                                    from plugins import tank_monitor
                                    cm = 0
                                    percent = 0
                                    ping = 0
                                    volume = 0
                                    units = False
                                    try: 
                                        cm = tank_monitor.get_all_values()[0]
                                        percent = tank_monitor.get_all_values()[1]
                                        ping = tank_monitor.get_all_values()[2]
                                        volume = tank_monitor.get_all_values()[3]
                                        units = tank_monitor.get_all_values()[4]
                                    except:
                                        pass
                                    msg = ' '
                                    if cm > 0:
                                        msg =  _('Level') + ': ' + str(cm) + ' ' + _('cm')
                                        msg += ' (' + str(percent) + ' %), '
                                        msg += _('Ping') + ': ' + str(ping) + ' ' + _('cm')
                                        if units:
                                            msg += ', ' + _('Volume') + ': ' + str(volume) + ' ' + _('liters')
                                        else:
                                            msg += ', ' + _('Volume') + ': ' + str(volume) + ' ' + _('m3')
                                        body += html_heading(_('Water'))
                                        body += html_line(_('Water level in tank') + ': %s' % (msg))
                                        logtext += _('Water') + '-> \n' + _('Water level in tank') + ': %s \n' % (msg)
                                    else: 
                                        msg = _('Error - I2C device not found!')
                                        body += html_heading(_('Water'))
                                        body += html_line(_('Water level in tank') + ': %s' % (msg))
                                        logtext += _('Water') + '-> \n' + _('Water level in tank') + ': %s \n' % (msg)

                            except ImportError:
                                log.debug(NAME, _('Cannot import plugin: tank monitor.'))
                                pass

                            # Send data from the virtual water meter. This
                            # section intentionally remains above DS values.
                            if email_options["eml_plug_wcounter"]:
                                water_body, water_log = virtual_water_meter_section(run)
                                body += water_body
                                logtext += water_log

                            # Send data from plugin air temp humidity 6x DS18b20
                            try:
                                if email_options["eml_plug_6ds"]:
                                    from plugins import air_temp_humi
                                    active_ds = air_temp_humi.DS18B20_active_indexes() if hasattr(air_temp_humi, 'DS18B20_active_indexes') else range(0, air_temp_humi.plugin_options['ds_used'])
                                    active_ds = list(active_ds)
                                    if active_ds:
                                        body += html_heading(_('Temperature DS1-DS6'))
                                        logtext += _('Temperature DS1-DS6') + '-> \n'
                                        for i in active_ds:
                                            value = air_temp_humi.DS18B20_read_probe(i)
                                            label = '%s' % air_temp_humi.plugin_options['label_ds%d' % i]
                                            msg = label + ': ' + '%.1f \u2103' % value
                                            body += html_line(msg)
                                            logtext += msg + '\n'
                            except ImportError:
                                log.debug(NAME, _('Cannot import plugin: air temp humi.'))
                                pass

                            # Send data from plugin current loop tanks monitor 4-20mA
                            try:
                                if email_options["eml_plug_4tank"]:
                                    from plugins import current_loop_tanks_monitor
                                    enabled_tanks = [i for i in range(4) if current_loop_tanks_monitor.plugin_options['en_tank{}'.format(i + 1)]]
                                    if enabled_tanks:
                                        body += html_heading(_('Current Loop Tanks Monitor'))
                                        logtext += _('Current Loop Tanks Monitor') + '-> \n'
                                        if current_loop_tanks_monitor.tanks.get('io_error', False):
                                            msg = _('Error: I/O.')
                                            body += html_line(msg)
                                            logtext += msg + '\n'
                                        else:
                                            channel_error = current_loop_tanks_monitor.tanks.get('channel_error', [False, False, False, False])
                                            for i in enabled_tanks:
                                                if channel_error[i]:
                                                    continue
                                                label = current_loop_tanks_monitor.tanks['label'][i]
                                                level_cm = current_loop_tanks_monitor.tanks['levelCm'][i]
                                                level_perc = current_loop_tanks_monitor.tanks['levelPercent'][i]
                                                volt = current_loop_tanks_monitor.tanks['voltage'][i]
                                                volume = current_loop_tanks_monitor.tanks['volumeLiter'][i]
                                                msg = _('{}: {:.2f} cm {:.2f} % {:.2f} V {:.2f} Liters').format(label, level_cm, level_perc, volt, volume)
                                                body += html_line(msg)
                                                logtext += msg + '\n'
                            except ImportError:
                                log.debug(NAME, _('Cannot import plugin: Current Loop Tanks Monitor.'))
                                pass

                            # Send data from OSPy sensors
                            try:
                                if email_options["eml_plug_sensors"]:
                                    body += html_heading(_('Sensors'))
                                    logtext += _('Sensors') + '-> \n'
                                    sensor_result = ''
                                    if sensors.count() > 0:
                                        for sensor in sensors.get():
                                            sensor_result = ''
                                            sensor_result += '{} ({}): '.format(sensor.name, _('by Shelly.com') if sensor.manufacturer == 1 else _('by Pihrt.com'))
                                            if sensor.enabled:
                                                if sensor.manufacturer == 0:                                    # pihrt.com sensor
                                                    if sensor.response == 1:
                                                        if sensor.sens_type == 1:                               # dry contact
                                                            if sensor.last_read_value[4] == 1:
                                                                sensor_result += _('Contact Closed')
                                                            elif sensor.last_read_value[4] == 0:
                                                                sensor_result += _('Contact Open')
                                                            else:
                                                                sensor_result += _('Probe Error')
                                                        if sensor.sens_type == 2:                               # leak detector
                                                            if sensor.last_read_value[5] != -127:
                                                                sensor_result += str(sensor.last_read_value[5]) + ' ' + _('l/s')
                                                            else:
                                                                sensor_result += _('Probe Error')
                                                        if sensor.sens_type == 3:                               # moisture
                                                            if sensor.last_read_value[6] != -127:
                                                                sensor_result += str(sensor.last_read_value[6]) + ' ' + _('%')
                                                            else:
                                                                sensor_result += _('Probe Error')
                                                        if sensor.sens_type == 4:                               # motion
                                                            if sensor.last_read_value[7] != -127:
                                                                sensor_result += _('Motion Detected') if int(sensor.last_read_value[7]) == 1 else _('No Motion')
                                                            else:
                                                                sensor_result += _('Probe Error')
                                                        if sensor.sens_type == 5:                               # temperature
                                                            if sensor.last_read_value[0] != -127:
                                                                sensor_result += '%.1f \u2103' % sensor.last_read_value[0]
                                                            else:
                                                                sensor_result += _('Probe Error')
                                                        if sensor.sens_type == 6:                               # multi sensor
                                                            if sensor.multi_type >= 0 and sensor.multi_type < 4:# multi temperature DS1-DS4
                                                                if sensor.last_read_value[sensor.multi_type] != -127: 
                                                                    sensor_result += '%.1f \u2103' % sensor.last_read_value[sensor.multi_type]
                                                                else:
                                                                    sensor_result += _('Probe Error')
                                                            if sensor.multi_type == 4:                          #  multi dry contact
                                                                if sensor.last_read_value[4] != -127:
                                                                    sensor_result += _('Contact Closed') if int(sensor.last_read_value[4]) == 1 else _('Contact Open')
                                                                else:
                                                                    sensor_result += _('Probe Error')
                                                            if sensor.multi_type == 5:                          #  multi leak detector
                                                                if sensor.last_read_value[5] != -127:
                                                                    sensor_result += str(sensor.last_read_value[5]) + ' ' + _('l/s')
                                                                else:
                                                                    sensor_result += _('Probe Error')
                                                            if sensor.multi_type == 6:                          #  multi moisture
                                                                if sensor.last_read_value[6] != -127:
                                                                    sensor_result += str(sensor.last_read_value[6]) + ' ' + _('%')
                                                                else:
                                                                    sensor_result += _(u'Probe Error')
                                                            if sensor.multi_type == 7:                          #  multi motion
                                                                if sensor.last_read_value[7] != -127:
                                                                    sensor_result += _('Motion Detected') if int(sensor.last_read_value[7])==1 else _('No Motion')
                                                                else:
                                                                    sensor_result += _('Probe Error')
                                                            if sensor.multi_type == 8:                          #  multi ultrasonic
                                                                if sensor.last_read_value[8] != -127:
                                                                    get_level = get_tank_cm(sensor.last_read_value[8], sensor.distance_bottom, sensor.distance_top)
                                                                    get_perc = get_percent(get_level, sensor.distance_bottom, sensor.distance_top)
                                                                    sensor_result += '{} '.format(get_level) + _('cm') + ' ({} %)'.format(get_perc)
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

                                                        if sensor.com_type == 0: # Wi-Fi/LAN
                                                            sensor_result += ' ' + _('Last Wi-Fi signal: {}%, Source: {}V.').format(sensor.rssi, sensor.last_battery)
                                                        if sensor.com_type == 1: # Radio
                                                            sensor_result += ' ' + _('Last Radio signal: {}%, Source: {}V.').format(sensor.rssi, sensor.last_battery)
                                                    else:
                                                        sensor_result += _('No response!')

                                                if sensor.manufacturer == 1:                                    # shelly.com sensor
                                                    if sensor.response == 1:
                                                        if sensor.sens_type == 0:                               ### Voltage ###
                                                            sensor_result += _('Voltage') + ': {} '.format(sensor.last_voltage) + _('V')
                                                        if sensor.sens_type == 1:                               ### Output 1 ###
                                                            try:
                                                                if sensor.last_read_value[0][0]:
                                                                    sensor_result += _('Output 1') + ': ' + _('ON')
                                                                else:
                                                                    sensor_result += _('Output 1') + ': ' + _('OFF')
                                                            except:
                                                                sensor_result += _('Any error')
                                                        if sensor.sens_type == 2:                               ### Output 2 ###
                                                            try:
                                                                if sensor.last_read_value[0][1]:
                                                                    sensor_result += _('Output 2') + ': ' + _('ON')
                                                                else:
                                                                    sensor_result += _('Output 2') + ': ' + _('OFF')
                                                            except:
                                                                sensor_result += _('Any error')
                                                        if sensor.sens_type == 3:                               ### Output 3 ###
                                                            try:
                                                                if sensor.last_read_value[0][2]:
                                                                    sensor_result += _('Output 3') + ': ' + _('ON')
                                                                else:
                                                                    sensor_result += _('Output 3') + ': ' + _('OFF')
                                                            except:
                                                                sensor_result += _('Any error')
                                                        if sensor.sens_type == 4:                               ### Output 4 ###
                                                            try:
                                                                if sensor.last_read_value[0][3]:
                                                                    sensor_result += _('Output 4') + ': ' + _('ON')
                                                                else:
                                                                    sensor_result += _('Output 4') + ': ' + _('OFF')
                                                            except:
                                                                sensor_result += _('Any error')
                                                        if sensor.sens_type == 5:                               ### Temperature 1 ###
                                                            try:
                                                                sensor_result += _('Temperature 1') + ': {} '.format(sensor.last_read_value[2][0]) + _('°C')
                                                            except:
                                                                sensor_result += _('Any error')
                                                        if sensor.sens_type == 6:                               ### Temperature 2 ###
                                                            try:
                                                                sensor_result += _('Temperature 2') + ': {} '.format(sensor.last_read_value[2][1]) + _('°C')
                                                            except:
                                                                sensor_result += _('Any error')
                                                        if sensor.sens_type == 7:                               ### Temperature 3 ###
                                                            try:
                                                                sensor_result += _('Temperature 3') + ': {} '.format(sensor.last_read_value[2][2]) + _('°C')
                                                            except:
                                                                sensor_result += _('Any error')
                                                        if sensor.sens_type == 8:                               ### Temperature 4 ###
                                                            try:
                                                                sensor_result += _('Temperature 4') + ': {} '.format(sensor.last_read_value[2][3]) + _('°C')
                                                            except:
                                                                sensor_result += _('Any error')
                                                        if sensor.sens_type == 9:                               ### Temperature 5 ###
                                                            try:
                                                                sensor_result += _('Temperature 1') + ': {} '.format(sensor.last_read_value[2][4]) + _('°C')
                                                            except:
                                                                sensor_result += _('Any error')
                                                        if sensor.sens_type == 10:                              ### Power 1 ###
                                                            try:
                                                                sensor_result += _('Power 1') + ': {} '.format(sensor.last_read_value[1][0]) + _('W')
                                                            except:
                                                                sensor_result += _('Any error')
                                                        if sensor.sens_type == 11:                              ### Power 2 ###
                                                            try:
                                                                sensor_result += _('Power 2') + ': {} '.format(sensor.last_read_value[1][1]) + _('W')
                                                            except:
                                                                sensor_result += _('Any error')
                                                        if sensor.sens_type == 12:                              ### Power 3 ###
                                                            try:
                                                                sensor_result += _('Power 3') + ': {} '.format(sensor.last_read_value[1][2]) + _('W')
                                                            except:
                                                                sensor_result += _('Any error')
                                                        if sensor.sens_type == 13:                              ### Power 4 ###
                                                            try:
                                                                sensor_result += _('Power 4') + ': {} '.format(sensor.last_read_value[1][3]) + _('W')
                                                            except:
                                                                sensor_result += _('Any error')
                                                        if sensor.sens_type == 14:                              ### Humidity ###
                                                            try:
                                                                sensor_result += _('Humidity') + ': {} '.format(sensor.last_read_value[3][0]) + _('%RV')
                                                            except:
                                                                sensor_result += _('Any error')
                                                        if sensor.sens_type == 15:                              ### PV Power 1 ###
                                                            try:
                                                                sensor_result += _('PV Power 1') + ': {} '.format(sensor.last_read_value[4][0]) + _('W')
                                                            except:
                                                                sensor_result += _('Any error')
                                                        if sensor.sens_type == 16:                              ### PV Power 2 ###
                                                            try:
                                                                sensor_result += _('PV Power 2') + ': {} '.format(sensor.last_read_value[4][1]) + _('W')
                                                            except:
                                                                sensor_result += _('Any error')
                                                        if sensor.sens_type == 17:                              ### PV Power 3 ###
                                                            try:
                                                                sensor_result += _('PV Power 3') + ': {} '.format(sensor.last_read_value[4][2]) + _('W')
                                                            except:
                                                                sensor_result += _('Any error')
                                                        if sensor.sens_type == 18:                              ### Illuminance ###
                                                            try:
                                                                sensor_result += _('Illuminance') + ': {} '.format(sensor.last_read_value[5][0]) + _('Lx')
                                                            except:
                                                                sensor_result += _('Any error')
                                                    else:
                                                        sensor_result += _('No response!')
                                            else:
                                                sensor_result += _('Disabled')

                                            body += html_line(sensor_result)
                                            logtext += sensor_result
                                            logtext += '\n'
                                    else:
                                        sensor_result += _('No sensors available')
                                        body += html_line(sensor_result)
                                        logtext += sensor_result
                                        logtext += '\n'
                            except:
                                log.debug(NAME, _('E-mail plug-in') + ':\n' + traceback.format_exc())
                                pass

                            # Send data from Shelly sensors
                            try:
                                if email_options["eml_plug_shelly"]:
                                    from plugins import shelly_cloud_integrator
                                    body += html_heading(_('Shelly cloud'))
                                    logtext += _('Shelly cloud') + '-> \n'
                                    for i in range(0, shelly_cloud_integrator.plugin_options['number_sensors']):
                                        body += '<br>&nbsp;&nbsp;'
                                        body += '{} '.format(shelly_cloud_integrator.sender.devices[i]['label'])
                                        logtext += '{} '.format(shelly_cloud_integrator.sender.devices[i]['label'])
                                        if shelly_cloud_integrator.sender.devices[i]['temperature']:
                                            body += '{}\u2103 '.format(shelly_cloud_integrator.sender.devices[i]['temperature'][0])
                                            logtext += '{}\u2103 '.format(shelly_cloud_integrator.sender.devices[i]['temperature'][0])
                                        if shelly_cloud_integrator.sender.devices[i]['humidity']:
                                            body += ' {}'.format(shelly_cloud_integrator.sender.devices[i]['humidity'][0]) + _('%RH') + ' '
                                            logtext += ' {}'.format(shelly_cloud_integrator.sender.devices[i]['humidity'][0]) + _('%RH') + ' '
                                        if shelly_cloud_integrator.sender.devices[i]['output']:
                                            if shelly_cloud_integrator.sender.devices[i]['output'][0] == 'stop':    # roller mode
                                                body += ' ' + _('STOP')
                                                logtext += ' ' + _('STOP')
                                            elif shelly_cloud_integrator.sender.devices[i]['output'][0] == 'up':    # roller mode
                                                body += ' ' + _('UP')
                                                logtext += ' ' + _('UP')
                                            elif shelly_cloud_integrator.sender.devices[i]['output'][0] == 'down':  # roller mode
                                                body += ' ' + _('DOWN')
                                                logtext += ' ' + _('DOWN')
                                            else:                                                                   # switch mode
                                                try:
                                                    body += ' ' + _('OUT1:') + ' ' +  _('ON') if shelly_cloud_integrator.sender.devices[i]['output'][0] else _('OFF')
                                                    logtext += ' ' + _('OUT1:') + ' ' +  _('ON') if shelly_cloud_integrator.sender.devices[i]['output'][0] else _('OFF')
                                                except:
                                                    pass
                                                try:
                                                    body += ' ' + _('OUT2:') + ' ' +  _('ON') if shelly_cloud_integrator.sender.devices[i]['output'][1] else _('OFF')
                                                    logtext += ' ' + _('OUT2:') + ' ' +  _('ON') if shelly_cloud_integrator.sender.devices[i]['output'][1] else _('OFF')
                                                except:
                                                    pass
                                                try:
                                                    body += ' ' + _('OUT3:') + ' ' +  _('ON') if shelly_cloud_integrator.sender.devices[i]['output'][2] else _('OFF')
                                                    logtext += ' ' + _('OUT3:') + ' ' +  _('ON') if shelly_cloud_integrator.sender.devices[i]['output'][2] else _('OFF')
                                                except:
                                                    pass
                                                try:
                                                    body += ' ' + _('OUT4:') + ' ' +  _('ON') if shelly_cloud_integrator.sender.devices[i]['output'][3] else _('OFF')
                                                    logtext += ' ' + _('OUT4:') + ' ' +  _('ON') if shelly_cloud_integrator.sender.devices[i]['output'][3] else _('OFF')
                                                except:
                                                    pass
                                        if shelly_cloud_integrator.sender.devices[i]['power']:
                                            body += ' ' + _('PWR1:') + ' {}'.format(shelly_cloud_integrator.sender.devices[i]['power'][0]) + _('W')
                                            logtext += ' ' + _('PWR1:') + ' {}'.format(shelly_cloud_integrator.sender.devices[i]['power'][0]) + _('W')
                                            try:
                                                body += ' ' + _('PWR2:') + ' {}'.format(shelly_cloud_integrator.sender.devices[i]['power'][1]) + _('W')
                                                logtext += ' ' + _('PWR2:') + ' {}'.format(shelly_cloud_integrator.sender.devices[i]['power'][1]) + _('W')
                                            except:
                                                pass
                                            try:
                                                body += ' ' + _('PWR3:') + ' {}'.format(shelly_cloud_integrator.sender.devices[i]['power'][2]) + _('W')
                                                logtext += ' ' + _('PWR3:') + ' {}'.format(shelly_cloud_integrator.sender.devices[i]['power'][2]) + _('W')
                                            except:
                                                pass
                                            try:
                                                body += ' ' + _('PWR4:') + ' {}'.format(shelly_cloud_integrator.sender.devices[i]['power'][3]) + _('W')
                                                logtext += ' ' + _('PWR4:') + ' {}'.format(shelly_cloud_integrator.sender.devices[i]['power'][3]) + _('W')
                                            except:
                                                pass
                                        if shelly_cloud_integrator.sender.devices[i]['voltage'] > 0:
                                            body += ' ' + _('VOLTAGE:') + ' {}'.format(shelly_cloud_integrator.sender.devices[i]['voltage']) + _('V')
                                            logtext += ' ' + _('VOLTAGE:') + ' {}'.format(shelly_cloud_integrator.sender.devices[i]['voltage']) + _('V')
                                        if shelly_cloud_integrator.sender.devices[i]['battery'] > 0:
                                            body += ' ' + _('BATTERY:') + ' {}'.format(shelly_cloud_integrator.sender.devices[i]['battery']) + _('%')
                                            logtext += ' ' + _('BATTERY:') + ' {}'.format(shelly_cloud_integrator.sender.devices[i]['battery']) + _('%')
                                        body += ' ' + _('IP:') + ' {}'.format(shelly_cloud_integrator.sender.devices[i]['ip'])
                                        logtext += ' ' + _('IP:') + ' {}'.format(shelly_cloud_integrator.sender.devices[i]['ip'])
                                        body += ' ' + _('RSSI:') + ' {}'.format(shelly_cloud_integrator.sender.devices[i]['rssi']) + _('dbm') + ' '
                                        logtext += ' ' + _('RSSI:') + ' {}'.format(shelly_cloud_integrator.sender.devices[i]['rssi']) + _('dbm') + ' '
                                        if shelly_cloud_integrator.sender.devices[i]['online']:
                                            body += ' ' + _('Online')
                                            logtext += ' ' + _('Online')
                                        else:
                                            body += ' ' + _('Offline')
                                            logtext += ' ' + _('Offline')
                                        body += '\n'
                                        logtext += '\n'
                            except:
                                pass

                        try_mail(body, logtext)

                    finished_count = len(finished)

                ###Repeating sending e-mails###
                if email_options["emlrepeater"]:                        # saving e-mails is enabled 
                    try:
                        millis = int(round(time.time() * 1000))         # actual time in ms
                        if(millis - last_millis) > send_interval:       # sending timer
                            last_millis = millis                        # save actual time ms
                            try:                                        # exists file: saved_emails.json?
                                saved_emails = read_saved_emails()      # read from file
                            except:                                     # no! create empty file
                                write_email([])                         # create file
                                saved_emails = read_saved_emails()      # read from file 

                            len_saved_emails = len(saved_emails)
                            if len_saved_emails > 0:                    # if there is something in json
                                log.clear(NAME)
                                log.info(NAME, _('Unsent E-mails in queue (in file)') + ': ' + str(len_saved_emails))
                                try:                                    # try send e-mail
                                    sendtext = '%s' % saved_emails[0]["text"]
                                    sendsubject = '%s' % (saved_emails[0]["subject"] + '-' + _('sending from queue.'))
                                    sendattachment = '%s' % saved_emails[0]["attachment"]
                                    email(sendtext, sendsubject, sendattachment) # send e-mail
                                    queue_failures = 0
                                    send_interval = QUEUE_RETRY_INTERVAL
                                    del saved_emails[0]                 # delete sent email in file
                                    write_email(saved_emails)           # save to file after deleting an item
                                    if len(saved_emails) == 0:
                                        log.clear(NAME)
                                        log.info(NAME, _('All unsent E-mails in the queue have been sent.'))

                                except Exception:
                                    #print traceback.format_exc()
                                    record_email_error(traceback.format_exc())
                                    queue_failures += 1
                                    send_interval = min(QUEUE_FAILURE_INTERVAL_MAX, QUEUE_FAILURE_INTERVAL * queue_failures)
                                    log.info(NAME, _('E-mail queue send failed. Next retry later.'))
                    except:
                        record_email_error(traceback.format_exc())
                        log.error(NAME, _('E-mail plug-in') + ':\n' + traceback.format_exc())

                self._sleep(MAIN_LOOP_SLEEP)

            except Exception:
                record_email_error(traceback.format_exc())
                log.error(NAME, _('E-mail plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)

email_sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global email_sender, signals_connected
    if not signals_connected:
        for event_signal, receiver in signal_receivers:
            event_signal.connect(receiver)
        signals_connected = True
    if email_sender is None:
        email_sender = EmailSender()
        runtime.register_thread(email_sender)


def stop():
    global email_sender, signals_connected
    worker = email_sender
    if worker is not None:
        worker.stop()
        worker.join(15)
        if email_sender is worker and not worker.is_alive():
            email_sender = None
    if signals_connected:
        for event_signal, receiver in signal_receivers:
            event_signal.disconnect(receiver)
        signals_connected = False


def record_email_success():
    with health_lock:
        health_state['last_success'] = time.time()
        health_state['last_error_message'] = ''


def record_email_error(message):
    with health_lock:
        health_state['last_error'] = time.time()
        health_state['last_error_message'] = str(message).splitlines()[-1]


def health():
    """Return SMTP SSL, queue, signal receiver and delivery state."""
    with health_lock:
        state = dict(health_state)
    worker_alive = email_sender is not None and email_sender.is_alive()
    configured = all([
        email_options['emlserver'],
        email_options['emlport'],
        email_options['emlusr'],
        email_options['emlpwd'],
        email_options['emladr0'],
    ])
    try:
        queue_size = len(read_saved_emails()) if email_options['emlrepeater'] else 0
    except Exception:
        queue_size = 0
    details = {
        _('Worker thread'): _('Running') if worker_alive else _('Stopped'),
        _('SMTP server'): '{}:{}'.format(email_options['emlserver'], email_options['emlport']),
        _('Signal receivers'): len(signal_receivers) if signals_connected else 0,
        _('Queued E-mails'): queue_size,
        _('Queue retry'): _('Enabled') if email_options['emlrepeater'] else _('Disabled'),
        _('Last successful E-mail'): (
            datetime_string(time.localtime(state['last_success']))
            if state['last_success'] else _('Not available')
        ),
    }
    if state['last_error_message']:
        details[_('Last error')] = state['last_error_message']
    if not worker_alive:
        return {
            'status': 'error',
            'summary': _('E-mail Notifications SSL worker is stopped.'),
            'details': details,
        }
    if not signals_connected:
        return {
            'status': 'error',
            'summary': _('E-mail notification signal receivers are disconnected.'),
            'details': details,
        }
    if not configured:
        return {
            'status': 'warning',
            'summary': _('E-mail plug-in is not properly configured!'),
            'details': details,
        }
    if state['last_error'] and state['last_error'] >= state['last_success']:
        return {
            'status': 'warning' if email_options['emlrepeater'] else 'error',
            'summary': state['last_error_message'],
            'details': details,
        }
    if not state['last_success']:
        return {
            'status': 'warning',
            'summary': _('No E-mail has been sent yet.'),
            'details': details,
        }
    return {
        'status': 'ok',
        'summary': _('E-mail delivery over SSL is working.'),
        'details': details,
    }

def add_to_body_local_ospy_name():
    try:
        from ospy.helpers import ospy_web_url
        ospy_local_name = ospy_web_url()
        if options.use_ssl or options.use_own_ssl:
            ahref = 'https://{}:{}'.format(ospy_local_name, options.web_port)
        else:
            ahref = 'http://{}:{}'.format(ospy_local_name, options.web_port)
        return '<br><span style="color:black;">' + _('OSPy is in the network under the name') + ': <a href="' + ahref + '">' + ahref + '</a></span>'
    except:
        return ""

### login ###
def notify_login(name, **kw):
    try:
        if email_options['emlusrin']:
            body = '<b>' + datetime_string() + '</b>'
            body += '<br><p style="color:blue;">' + _('Someone logged in.') + '</p><br>'
            body += add_to_body_local_ospy_name()
            logtext = _('Someone logged in.')
            try_mail(body, logtext)
    except:
        log.error(NAME, _('E-mail plug-in') + ':\n' + traceback.format_exc())

### rain ###
def notify_rain_active(name, **kw):
    try:
        if email_options['emlrain']:    
            body = '<b>' + datetime_string() + '</b>'
            body += '<br><p style="color:red;">' + _('Rain sensor has activated.') + '</p><br>'
            body += add_to_body_local_ospy_name()
            logtext = _('Rain sensor has activated.')
            try_mail(body, logtext)
    except:
        log.error(NAME, _('E-mail plug-in') + ':\n' + traceback.format_exc())

### no rain ###
def notify_rain_deactive(name, **kw):
    try:
        if email_options['emlrainde']:
            body = '<b>' + datetime_string() + '</b>'
            body += '<br><p style="color:green;">' + _('Rain sensor has deactivated.') + '</p><br>'
            body += add_to_body_local_ospy_name()
            logtext = _('Rain sensor has deactivated.')
            try_mail(body, logtext)
    except:
        log.error(NAME, _('E-mail plug-in') + ':\n' + traceback.format_exc())

### rain delay has setuped ###
def notify_rain_delay_setuped(name, **kw):
    try:
        if email_options['emlrds']:
            body = '<b>' + datetime_string() + '</b>'
            body += '<br><p style="color:red;">' + _('Rain delay is now set a delay {} (h: m: s).').format(kw["txt"]) + '</p><br>'
            body += add_to_body_local_ospy_name()
            logtext = _('Rain delay is now set a delay {} hours.').format(kw["txt"])
            try_mail(body, logtext)
    except:
        log.error(NAME, _('E-mail plug-in') + ':\n' + traceback.format_exc())

### rain delay has expired ###
def notify_rain_delay_expired(name, **kw):
    try:
        if email_options['emlrdr']:
            body = '<b>' + datetime_string() + '</b>'
            body += '<br><p style="color:green;">' + _('Rain delay has now been removed.') + '</p><br>'
            body += add_to_body_local_ospy_name()
            logtext = _('Rain delay has now been removed.')
            try_mail(body, logtext)
    except:
        log.error(NAME, _('E-mail plug-in') + ':\n' + traceback.format_exc())

loggedin = signal('loggedin')  # associations with signal
rain_active = signal('rain_active')
rain_not_active = signal('rain_not_active')
rain_delay_set = signal('rain_delay_set')
rain_delay_remove = signal('rain_delay_remove')
signal_receivers = [
    (loggedin, notify_login),
    (rain_active, notify_rain_active),
    (rain_not_active, notify_rain_deactive),
    (rain_delay_set, notify_rain_delay_setuped),
    (rain_delay_remove, notify_rain_delay_expired),
]


def safeStr(obj):
    try: 
       return str(obj)
    except:
       return "'" + ' '.join(obj).encode('utf-8').strip() + "'"

def email(text, subject=None, attach=None):
    ### Send email with with attachments. If subject is None, the default will be used ###
    if(email_options['emlusr']
        and email_options['emlpwd']
        and email_options['emladr0']
        and email_options['emlserver']
        ):
        recipients_list = [email_options['emladr'+str(i)] for i in range(5) if email_options['emladr'+str(i)]!='']
        SMTP_user = email_options['emlusr']       # SMTP username
        SMTP_pwd = email_options['emlpwd']        # SMTP password
        SMTP_server = email_options['emlserver']  # SMTP server address
        SMTP_port = email_options['emlport']      # SMTP port
        
        mail_from = SMTP_user if email_options['emlsender'] else options.name  # From Name

        # --------------
        msg = MIMEMultipart()

        msg['From'] = mail_from
        msg['Subject'] = subject or email_options['emlsubject']

        html = """\
           <html>
             <head></head>
             <body>
               %s
             </body>
           </html>
               """ % text

        part_text = MIMEText(html.encode('utf-8'), 'html', 'utf-8')
        msg.attach(part_text)

        if len(recipients_list) > 0:
            recipients_str = ', '.join(recipients_list)

            msg['To'] = recipients_str
            if attach is not None and os.path.isfile(attach) and os.access(attach, os.R_OK):  # If insert attachments
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(open(attach, 'rb').read())
                encode_base64(part)
                part.add_header('Content-Disposition', 'attachment; filename="%s"' % os.path.basename(attach))
                msg.attach(part)
            # Create a secure SSL context
            context = ssl.create_default_context()
            try:
                with smtplib.SMTP_SSL(SMTP_server, SMTP_port, timeout=SMTP_TIMEOUT, context=context) as server:
                    server.login(mail_from, SMTP_pwd)
                    server.sendmail(mail_from, recipients_list, msg.as_string())
                record_email_success()
            except Exception:
                record_email_error(traceback.format_exc())
                raise
    else:
        message = _('E-mail plug-in is not properly configured!')
        record_email_error(message)
        raise Exception(message)


def is_configured():
    """Return whether the plug-in has the minimum settings needed to send mail."""
    return bool(
        email_sender is not None
        and email_options['emlserver']
        and email_options['emlport']
        and email_options['emlusr']
        and email_options['emlpwd']
        and email_options['emladr0']
    )


def send_2fa_code(code, expires_minutes=5):
    """Send a login code immediately; never enqueue a time-sensitive message."""
    if not is_configured():
        raise RuntimeError(_('E-mail plug-in is not properly configured!'))
    body = _(
        'Your OSPy verification code is <b>{}</b>. The code expires in {} minutes. '
        'If you did not try to sign in, change your password.'
    ).format(code, expires_minutes)
    email(body, _('OSPy login verification code'))


def read_saved_emails():
    ### Read saved emails from json file ###
    try:
        with open(os.path.join(plugin_data_dir(), 'saved_emails.json')) as saved_emails:
            return json.load(saved_emails)
    except IOError:
        return []

def write_email(json_data):
    ###Write e-mail data to json file ###
    try:
        with open(os.path.join(plugin_data_dir(), 'saved_emails.json'), 'w') as saved_emails:
            json.dump(json_data, saved_emails)
    except:
        log.error(NAME, _('E-mail plug-in') + ':\n' + traceback.format_exc())

def update_saved_emails(data):
    ### Update data in json files ###
    try:                                                              # exists file: saved_emails.json?
        saved_emails = read_saved_emails()
    except:                                                           # no! create empty file
        write_email([])
        saved_emails = read_saved_emails()

    saved_emails.insert(0, data)
    write_email(saved_emails)


def try_mail(text, logtext, attachment=None, subject=None):
    ### Try send e-mail ###
    log.clear(NAME)
    try:
        email(text, subject, attachment)  # send email with attachment from
        log.info(NAME, _('E-mail was sent') + ':\n' + logtext)
        if not options.run_logEM:
            log.info(NAME, _('E-mail logging is disabled in options...'))
        else:    
            logEM.save_email_log(subject or email_options['emlsubject'], logtext, _('Sent'))

    except Exception:
        record_email_error(traceback.format_exc())
        log.error(NAME, _('E-mail plug-in') + ':\n' + traceback.format_exc())
        logEM.save_email_log(subject or email_options['emlsubject'], logtext, traceback.format_exc())
        if not options.run_logEM:
            log.info(NAME, _('E-mail logging is disabled in options...'))
            
        if email_options["emlrepeater"]: # saving e-mails is enabled  
            data = {}
            data['date'] = str(datetime.now().strftime('%d.%m.%Y'))
            data['time'] = str(datetime.now().strftime('%H:%M:%S'))   
            data['text'] = '%s' % text
            data['logtext'] = '%s' % logtext
            data['subject'] = '%s' % email_options['emlsubject']
            data['attachment'] = '%s' % attachment

            update_saved_emails(data)    # saving e-mail data to file: saved_emails.json

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

################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    ### Load an html page for entering email adjustments ###

    def GET(self):
        try:
            return self.plugin_render.email_notifications_ssl(
                email_options, log.events(NAME), PLUGIN_VERSION
            )
        except:
            log.error(NAME, _('E-mail plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('email_notifications_ssl -> settings_page GET')
            return self.core_render.notice('/', msg)


    def POST(self):
        global saved_emails
        
        try:
            qdict = web.input()
            verify_csrf(qdict)
            email_options.web_update(qdict)
            qdict = web.input()
            verify_csrf(qdict)
            test = get_input(qdict, 'test', False, lambda x: True)
            delete = get_input(qdict, 'del', False, lambda x: True)

            if email_sender is not None:
                email_sender.update()

                if test:
                    regex = re.compile(r'([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+')      # SMTP username
                    if not re.fullmatch(regex, email_options['emlusr']):
                        log.clear(NAME)
                        log.info(NAME,datetime_string() + ': ' + _('Sender e-mail address appears to be invalid!'))
                        raise web.seeother(plugin_url(settings_page), True)  

                    body = datetime_string() + ': ' + _('This is test e-mail from OSPy. You can ignore it.')
                    logtext = _('This is test e-mail from OSPy. You can ignore it.')
                    try_mail(body, logtext)
            
                if delete:
                    log.info(NAME, datetime_string() + ': ' + _('Email Queue was deleted.'))
                    write_email([])
                    saved_emails = 0

            raise web.seeother(plugin_url(settings_page), True)

        except:
            log.error(NAME, _('E-mail plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('email_notifications_ssl -> settings_page POST')
            return self.core_render.notice('/', msg)

class help_page(ProtectedPage):
    ### Load an html page for help ###

    def GET(self):
        try:
            return self.plugin_render.email_notifications_ssl_help()
        except:
            log.error(NAME, _('E-mail plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('email_notifications_ssl -> help_page GET')
            return self.core_render.notice('/', msg)

class settings_json(ProtectedPage):
    ### Returns plugin settings in JSON format ###

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(email_options)
        except:
            return {}
