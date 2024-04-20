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
from threading import Thread, Event
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
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.options import options
from ospy.stations import stations
from ospy.log import log, EVENT_FILE, logEM
from ospy.helpers import datetime_string, get_input
from ospy.sensors import sensors

from blinker import signal


NAME = 'E-mail Notifications SSL'
MENU =  _('Package: E-mail Notifications SSL')
LINK = 'settings_page'

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

################################################################################
# Main function loop:                                                          #
################################################################################
class EmailSender(Thread):
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
        time.sleep(
            randint(3, 10)
        )  # Sleep some time to prevent printing before startup information 

        send_interval = 10000 # default time for sending between e-mails (ms)
        last_millis   = 0     # timer for repeating sending e-mails (ms)
        body    = u''
        logtext = u''
        finished_count = len([run for run in log.finished_runs() if not run['blocked']])

        if email_options["emlpwron"]:  # if eml_power_on send email is enable (on)
            body += '<b>' + _('System') + '</b> ' + datetime_string()
            body += '<br><p style="color:red;">' + _('System was powered on.') + u'</p>'
            logtext = _('System was powered on.')

            if email_options["emllog"]:
                file_exists = os.path.exists(EVENT_FILE)
                if file_exists:
                   try_mail(body, logtext, EVENT_FILE)
                else:
                   body += '<br>' + _('Error -  events.log file not exists!')
                   try_mail(body, logtext)
            else:
                try_mail(body, logtext)

        while not self._stop_event.is_set():
            body    = u''
            logtext = u''
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
                            body += '<b>' + _('System') + '</b> ' + datetime_string()
                            body += '<br><b>'  + _('Finished run') + '</b>'
                            body += '<ul><li>' + _('Program') + ': %s \n' % pname + '</li>'
                            body += '<li>' + _('Station') + ': %s \n' % sname + '</li>'
                            body += '<li>' + _('Start time') + ': %s \n' % datetime_string(run['start']) + '</li>'
                            body += '<li>' + _('Duration') + ': %02d:%02d\n' % (minutes, seconds) + '</li></ul>'
                            logtext  =  _('Finished run') + '-> \n' + _('Program') + ': %s\n' % pname 
                            logtext +=  _('Station') + ': %s\n' % sname
                            logtext +=  _('Start time') + ': %s \n' % datetime_string(run['start'])
                            logtext +=  _('Duration') + ': %02d:%02d\n' % (minutes, seconds)

                            # Water Tank Monitor
                            try:
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

                                    body += '<b>'  + _('Water') + '</b>'
                                    body += '<br><ul><li>' + _('Water level in tank') + ': %s \n</li></ul>' % (msg)
                                    logtext += _('Water') + '-> \n' + _('Water level in tank') + ': %s \n' % (msg)                                        
                                else: 
                                    msg = _('Error - I2C device not found!')
                                    body += '<b>'  + _('Water') + '</b>'
                                    body += '<br><ul><li>' + _('Water level in tank') + ': %s \n</li></ul>' % (msg)
                                    logtext += _('Water') + '-> \n' + _('Water level in tank') + ': %s \n' % (msg)

                            except ImportError:
                                log.debug(NAME, _('Cannot import plugin: tank monitor.'))
                                pass

                            # Water Consumption Counter
                            try:
                                from plugins import water_consumption_counter
                                self._sleep(2) # wait for the meter to save consumption

                                consum_from = water_consumption_counter.get_all_values()[0]
                                consum_one  = float(water_consumption_counter.get_all_values()[1])
                                consum_two  = float(water_consumption_counter.get_all_values()[2])

                                msg = ' '
                                msg +=  _('Measured from day') + ': ' + str(consum_from) + ', '
                                msg +=  _('Master Station') + ': '
                                if consum_one < 1000.0:
                                    msg += str(consum_one) + ' '
                                    msg += _('Liter') + ', '
                                else: 
                                    msg += str(round((consum_one/1000.0), 2)) + ' '
                                    msg += _('m3') + ', '

                                msg +=  _('Second Master Station') + ': '
                                if consum_two < 1000.0:
                                    msg += str(consum_two) + ' '
                                    msg += _('Liter') 
                                else:
                                    msg += str(round((consum_two/1000.0), 2)) + ' '
                                    msg += _('m3')

                                body += '<br><b>'  + _('Water Consumption Counter') + '</b>'
                                body += '<br><ul><li>%s \n</li></ul>' % (msg)
                                logtext += _('Water Consumption Counter') + ': %s \n' % (msg)

                            except ImportError:
                                log.debug(NAME, _('Cannot import plugin: water consumption counter.'))
                                pass

                            # Air Temperature and Humidity Monitor
                            try:
                                from plugins import air_temp_humi

                                body += '<br><b>' + _('Temperature DS1-DS6') + '</b><ul>'
                                logtext += _('Temperature DS1-DS6') + '-> \n'
                                for i in range(0, air_temp_humi.plugin_options['ds_used']):
                                    body += '<li>' + '%s' % air_temp_humi.plugin_options['label_ds%d' % i] + ': ' + '%.1f \u2103' % air_temp_humi.DS18B20_read_probe(i) + '\n</li>'  
                                    logtext += '%s' % air_temp_humi.plugin_options['label_ds%d' % i] + ': ' + '%.1f \u2103\n' % air_temp_humi.DS18B20_read_probe(i) 
                                body += '</ul>'    

                            except ImportError:
                                log.debug(NAME, _('Cannot import plugin: air temp humi.'))
                                pass

                            # OSPy Sensors
                            try:
                                body += '<br><b>' + _('Sensors') + '</b>'
                                logtext += _('Sensors') + '-> \n'
                                sensor_result = ''
                                if sensors.count() > 0:
                                    body += '<ul>'
                                    for sensor in sensors.get():
                                        sensor_result = ''
                                        body += '<li>'
                                        sensor_result += '{}: '.format(sensor.name)
                                        if sensor.enabled:
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
                                        else:
                                            sensor_result += _('Disabled')

                                        body += sensor_result
                                        body += '</li>'
                                        logtext += sensor_result
                                        logtext += '\n'
                                    body += '</ul>'
                                    body += '<br>'
                                        
                                else:
                                    sensor_result += _('No sensors available')
                                    body += '<ul><li>'
                                    body += sensor_result
                                    body += '</li></ul>'
                                    body += '<br>'
                                    logtext += sensor_result
                                    logtext += '\n'
                                    
                            except:
                                log.debug(NAME, _('E-mail plug-in') + ':\n' + traceback.format_exc())
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
                                    send_interval = 10000               # repetition of 10 seconds
                                    del saved_emails[0]                 # delete sent email in file
                                    write_email(saved_emails)           # save to file after deleting an item
                                    if len(saved_emails) == 0:
                                        log.clear(NAME)
                                        log.info(NAME, _('All unsent E-mails in the queue have been sent.'))

                                except Exception:
                                    #print traceback.format_exc()
                                    send_interval = 60000               # repetition of 60 seconds   
                    except:
                        log.error(NAME, _('E-mail plug-in') + ':\n' + traceback.format_exc())  

                self._sleep(2)

            except Exception:
                log.error(NAME, _('E-mail plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)

email_sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global email_sender
    if email_sender is None:
        email_sender = EmailSender()


def stop():
    global email_sender
    if email_sender is not None:
        email_sender.stop()
        email_sender.join()
        email_sender = None

### login ###
def notify_login(name, **kw):
    if email_options['emlusrin']:
        body = '<b>' + _('System') + '</b> ' + datetime_string() 
        body += '<br><p style="color:blue;">' + _('Someone logged in.') + '</p><br>'
        logtext = _('Someone logged in.')
        try_mail(body, logtext)

### rain ###
def notify_rain_active(name, **kw):
    if email_options['emlrain']:    
        body = '<b>' + _('System') + '</b> ' + datetime_string() 
        body += '<br><p style="color:red;">' + _('Rain sensor has activated.') + '</p><br>'
        logtext = _('Rain sensor has activated.')
        try_mail(body, logtext)

### no rain ###
def notify_rain_deactive(name, **kw):
    if email_options['emlrainde']:
        body = '<b>' + _('System') + '</b> ' + datetime_string() 
        body += '<br><p style="color:green;">' + _('Rain sensor has deactivated.') + '</p><br>'
        logtext = _('Rain sensor has deactivated.')
        try_mail(body, logtext)

### rain delay has setuped ###
def notify_rain_delay_setuped(name, **kw):
    if email_options['emlrds']:    
        body = '<b>' + _('System') + '</b> ' + datetime_string() 
        body += '<br><p style="color:red;">' + _('Rain delay is now set a delay {} (h: m: s).').format(kw["txt"]) + '</p><br>'
        logtext = _('Rain delay is now set a delay {} hours.').format(kw["txt"])
        try_mail(body, logtext)

### rain delay has expired ###
def notify_rain_delay_expired(name, **kw):
    if email_options['emlrdr']:    
        body = '<b>' + _('System') + '</b> ' + datetime_string() 
        body += '<br><p style="color:green;">' + _('Rain delay has now been removed.') + '</p><br>'
        logtext = _('Rain delay has now been removed.')
        try_mail(body, logtext)


loggedin = signal('loggedin')  # associations with signal
loggedin.connect(notify_login) # define which subroutine will be triggered
rain_active = signal('rain_active')
rain_active.connect(notify_rain_active)
rain_not_active = signal('rain_not_active')
rain_not_active.connect(notify_rain_deactive)
rain_delay_set = signal('rain_delay_set')
rain_delay_set.connect(notify_rain_delay_setuped) 
rain_delay_remove = signal('rain_delay_remove')
rain_delay_remove.connect(notify_rain_delay_expired)                       


def safeStr(obj):
    try: 
       return str(obj)
    except:
       return "u'" + ' '.join(obj).encode('utf-8').strip() + "'"

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
               <p>
                 %s
               </p>
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
            with smtplib.SMTP_SSL(SMTP_server, SMTP_port, context=context) as server:
                server.login(mail_from, SMTP_pwd)
                server.sendmail(mail_from, recipients_list, msg.as_string())
    else:
        raise Exception(_('E-mail plug-in is not properly configured!'))


def read_saved_emails():
    ### Read saved emails from json file ###
    try:
        with open(os.path.join(plugin_data_dir(), 'saved_emails.json')) as saved_emails:
            return json.load(saved_emails)
    except IOError:
        return []     

def write_email(json_data):
    ###Write e-mail data to json file ###
    with open(os.path.join(plugin_data_dir(), 'saved_emails.json'), 'w') as saved_emails:
        json.dump(json_data, saved_emails)  

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
        return self.plugin_render.email_notifications_ssl(email_options, log.events(NAME))

    def POST(self):
        global saved_emails
        
        email_options.web_update(web.input())
        qdict = web.input()
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


class help_page(ProtectedPage):
    ### Load an html page for help ###

    def GET(self):
        return self.plugin_render.email_notifications_ssl_help()


class settings_json(ProtectedPage):
    ### Returns plugin settings in JSON format ###

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(email_options)