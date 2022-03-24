# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'
# this plugins send E-mail

import json
import time
from datetime import datetime
import os
import os.path
import traceback
import smtplib
from threading import Thread, Event
from random import randint

from email.encoders import encode_base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.multipart import MIMEBase

import web
from ospy.webpages import ProtectedPage
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.options import options
from ospy.stations import stations
from ospy.inputs import inputs
from ospy.log import log, EVENT_FILE, logEM
from ospy.helpers import datetime_string, get_input
from ospy.sensors import sensors


NAME = 'E-mail Notifications'
MENU =  _(u'Package: E-mail Notifications')
LINK = 'settings_page'

email_options = PluginOptions(
    NAME,
    {
        'emlpwron': False,
        'emllog': False,
        'emlrain': False,
        'emlrun': False,
        'emlserver': 'smtp.gmail.com',
        'emlport': '587',
        'emlusr': '',
        'emlpwd': '',
        'emlsender': False,
        'emladr0': '',
        'emladr1': '',
        'emladr2': '',
        'emladr3': '',
        'emladr4': '',
        'emlsubject': _(u'Report from OSPy SYSTEM'),
        'emlrepeater': True
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
        last_rain = False
        body    = u''
        logtext = u''
        finished_count = len([run for run in log.finished_runs() if not run['blocked']])

        if email_options["emlpwron"]:  # if eml_power_on send email is enable (on)
            body += u'<b>' + _(u'System') + u'</b> ' + datetime_string()
            body += u'<br><p style="color:red;">' + _(u'System was powered on.') + u'</p>'
            logtext = _(u'System was powered on.')

            if email_options["emllog"]:
                file_exists = os.path.exists(EVENT_FILE)
                if file_exists:
                   try_mail(body, logtext, EVENT_FILE)
                else:
                   body += u'<br>' + _(u'Error -  events.log file not exists!')
                   try_mail(body, logtext)
            else:
                try_mail(body, logtext)

        while not self._stop_event.is_set():
            body    = u''
            logtext = u''
            try:
                # Send E-amil if rain is detected
                if email_options["emlrain"]:
                    if inputs.rain_sensed() and not last_rain:
                        body += u'<b>' + _(u'System') + u'</b> ' + datetime_string() 
                        body += u'<br><p style="color:red;">' + _(u'System detected rain.') + u'</p><br>'
                        logtext = _(u'System detected rain.')
                        try_mail(body, logtext)
                    last_rain = inputs.rain_sensed()

                # Send E-mail if a new finished run is found
                if email_options["emlrun"]:
                    finished = [run for run in log.finished_runs() if not run['blocked']]
                    if len(finished) > finished_count:
                        for run in finished[finished_count:]:
                            duration = (run['end'] - run['start']).total_seconds()
                            minutes, seconds = divmod(duration, 60)
                            pname = run['program_name']
                            sname = stations.get(run['station']).name
                            body += u'<br>'
                            body += u'<b>' + _(u'System') + u'</b> ' + datetime_string()
                            body += u'<br><b>'  + _(u'Finished run') + u'</b>'
                            body += u'<ul><li>' + _(u'Program') + u': %s \n' % pname + u'</li>'
                            body += u'<li>' + _(u'Station') + u': %s \n' % sname + u'</li>'
                            body += u'<li>' + _(u'Start time') + u': %s \n' % datetime_string(run['start']) + u'</li>'
                            body += u'<li>' + _(u'Duration') + u': %02d:%02d\n' % (minutes, seconds) + u'</li></ul>'
                            logtext  =  _(u'Finished run') + u'-> \n' + _(u'Program') + u': %s\n' % pname 
                            logtext +=  _(u'Station') + u': %s\n' % sname
                            logtext +=  _(u'Start time') + u': %s \n' % datetime_string(run['start'])
                            logtext +=  _(u'Duration') + u': %02d:%02d\n' % (minutes, seconds)

                            # Water Tank Monitor
                            try:
                                from plugins import tank_monitor

                                cm = tank_monitor.get_all_values()[0]
                                percent = tank_monitor.get_all_values()[1]
                                ping = tank_monitor.get_all_values()[2]
                                volume = tank_monitor.get_all_values()[3]
                                units = tank_monitor.get_all_values()[4]

                                msg = ' '
                                if cm > 0:
                                    msg =  _(u'Level') + u': ' + str(cm) + u' ' + _(u'cm')
                                    msg += u' (' + str(percent) + u' %), '
                                    msg += _(u'Ping') + u': ' + str(ping) + u' ' + _(u'cm')
                                    if units:
                                        msg += u', ' + _(u'Volume') + u': ' + str(volume) + u' ' + _(u'liters')
                                    else:
                                        msg += u', ' + _(u'Volume') + u': ' + str(volume) + u' ' + _(u'm3')
                                else: 
                                    msg = _(u'Error - I2C device not found!')

                                body += u'<b>'  + _(u'Water') + u'</b>'
                                body += u'<br><ul><li>' + _(u'Water level in tank') + u': %s \n</li></ul>' % (msg)
                                logtext += _(u'Water') + u'-> \n' + _(u'Water level in tank') + u': %s \n' % (msg)
                            
                            except ImportError:
                                log.debug(NAME, _(u'Cannot import plugin: tank monitor.'))
                                pass

                            # Water Consumption Counter
                            try:
                                from plugins import water_consumption_counter
                                self._sleep(2) # wait for the meter to save consumption

                                consum_from = water_consumption_counter.get_all_values()[0]
                                consum_one  = water_consumption_counter.get_all_values()[1]
                                consum_two  = water_consumption_counter.get_all_values()[2]

                                msg = u' '
                                msg +=  _(u'Measured from day') + u': ' + str(consum_from) + u', '
                                msg +=  _(u'Master Station') + u': '
                                if consum_one < 1000:
                                    msg += str(consum_one) + u' '
                                    msg += _(u'Liter') + u', '
                                else: 
                                    msg += str(round((consum_one/1000.0), 2)) + u' '
                                    msg += _(u'm3') + ', '

                                msg +=  _(u'Second Master Station') + u': '
                                if consum_two < 1000:
                                    msg += str(consum_two) + u' '
                                    msg += _(u'Liter') 
                                else:
                                    msg += str(round((consum_two/1000.0), 2)) + u' '
                                    msg += _(u'm3')

                                body += u'<br><b>'  + _(u'Water Consumption Counter') + u'</b>'
                                body += u'<br><ul><li>%s \n</li></ul>' % (msg)
                                logtext += _(u'Water Consumption Counter') + u': %s \n' % (msg)

                            except ImportError:
                                log.debug(NAME, _(u'Cannot import plugin: water consumption counter.'))
                                pass

                            # Air Temperature and Humidity Monitor
                            try:
                                from plugins import air_temp_humi

                                body += u'<br><b>' + _(u'Temperature DS1-DS6') + u'</b><ul>'
                                logtext += _(u'Temperature DS1-DS6') + u'-> \n'
                                for i in range(0, air_temp_humi.plugin_options['ds_used']):
                                    body += u'<li>' + u'%s' % air_temp_humi.plugin_options['label_ds%d' % i] + u': ' + u'%.1f \u2103' % air_temp_humi.DS18B20_read_probe(i) + u'\n</li>'  
                                    logtext += u'%s' % air_temp_humi.plugin_options['label_ds%d' % i] + u': ' + u'%.1f \u2103\n' % air_temp_humi.DS18B20_read_probe(i) 
                                body += u'</ul>'    

                            except ImportError:
                                log.debug(NAME, _(u'Cannot import plugin: air temp humi.'))
                                pass

                            # OSPy Sensors
                            try:
                                body += u'<br><b>' + _(u'Sensors') + u'</b>'
                                logtext += _(u'Sensors') + u'-> \n'
                                sensor_result = ''
                                if sensors.count() > 0:
                                    body += u'<ul>'
                                    for sensor in sensors.get():
                                        sensor_result = ''
                                        body += u'<li>'
                                        sensor_result += u'{}: '.format(sensor.name)
                                        if sensor.enabled:
                                            if sensor.response == 1:
                                                if sensor.sens_type == 1:                               # dry contact
                                                    if sensor.last_read_value[4] == 1:
                                                        sensor_result += _(u'Contact Closed')
                                                    elif sensor.last_read_value[4] == 0:
                                                        sensor_result += _(u'Contact Open')
                                                    else:
                                                        sensor_result += _(u'Probe Error')
                                                if sensor.sens_type == 2:                               # leak detector
                                                    if sensor.last_read_value[5] != -127:
                                                        sensor_result += str(sensor.last_read_value[5]) + ' ' + _(u'l/s')
                                                    else:
                                                        sensor_result += _(u'Probe Error')
                                                if sensor.sens_type == 3:                               # moisture
                                                    if sensor.last_read_value[6] != -127:
                                                        sensor_result += str(sensor.last_read_value[6]) + ' ' + _(u'%')
                                                    else:
                                                        sensor_result += _(u'Probe Error')
                                                if sensor.sens_type == 4:                               # motion
                                                    if sensor.last_read_value[7] != -127:
                                                        sensor_result += _(u'Motion Detected') if int(sensor.last_read_value[7]) == 1 else _(u'No Motion')
                                                    else:
                                                        sensor_result += _(u'Probe Error')
                                                if sensor.sens_type == 5:                               # temperature
                                                    if sensor.last_read_value[0] != -127:
                                                        sensor_result += u'%.1f \u2103' % sensor.last_read_value[0]
                                                    else:
                                                        sensor_result += _(u'Probe Error')
                                                if sensor.sens_type == 6:                               # multi sensor
                                                    if sensor.multi_type >= 0 and sensor.multi_type < 4:# multi temperature DS1-DS4
                                                        if sensor.last_read_value[sensor.multi_type] != -127: 
                                                            sensor_result += u'%.1f \u2103' % sensor.last_read_value[sensor.multi_type]
                                                        else:
                                                            sensor_result += _(u'Probe Error')
                                                    if sensor.multi_type == 4:                          #  multi dry contact
                                                        if sensor.last_read_value[4] != -127:
                                                            sensor_result += _(u'Contact Closed') if int(sensor.last_read_value[4]) == 1 else _(u'Contact Open')
                                                        else:
                                                            sensor_result += _(u'Probe Error')
                                                    if sensor.multi_type == 5:                          #  multi leak detector
                                                        if sensor.last_read_value[5] != -127:
                                                            sensor_result += str(sensor.last_read_value[5]) + ' ' + _(u'l/s')
                                                        else:
                                                            sensor_result += _(u'Probe Error')
                                                    if sensor.multi_type == 6:                          #  multi moisture
                                                        if sensor.last_read_value[6] != -127:
                                                            sensor_result += str(sensor.last_read_value[6]) + ' ' + _(u'%')
                                                        else:
                                                            sensor_result += _(u'Probe Error')
                                                    if sensor.multi_type == 7:                          #  multi motion
                                                        if sensor.last_read_value[7] != -127:
                                                            sensor_result += _(u'Motion Detected') if int(sensor.last_read_value[7])==1 else _(u'No Motion')
                                                        else:
                                                            sensor_result += _(u'Probe Error')
                                                    if sensor.multi_type == 8:                          #  multi ultrasonic
                                                        if sensor.last_read_value[8] != -127:
                                                            get_level = get_tank_cm(sensor.last_read_value[8], sensor.distance_bottom, sensor.distance_top)
                                                            get_perc = get_percent(get_level, sensor.distance_bottom, sensor.distance_top)
                                                            sensor_result += u'{} '.format(get_level) + _(u'cm') + u' ({} %)'.format(get_perc)
                                                        else:
                                                            sensor_result += _(u'Probe Error')
                                                    if sensor.multi_type == 9:                          #  multi soil moisture
                                                        err_check = 0
                                                        calculate_soil = [0.0]*16
                                                        state = [-127]*16
                                                        for i in range(0, 16):
                                                            if type(sensor.soil_last_read_value[i]) == float:
                                                                state[i] = sensor.soil_last_read_value[i]
                                                                val = state[i]
                                                                if sensor.soil_invert_probe_in[i]:
                                                                    if val < sensor.soil_calibration_max[i]:
                                                                        val = sensor.soil_calibration_max[i]
                                                                    if val > sensor.soil_calibration_min[i]:
                                                                        val = sensor.soil_calibration_min[i]
                                                                    val = sensor.soil_calibration_min[i] - val
                                                                    calculate_soil[i] = maping(val, float(sensor.soil_calibration_max[i]), float(sensor.soil_calibration_min[i]), 0.0, 100.0)
                                                                    calculate_soil[i] = round(calculate_soil[i], 1)
                                                                else:
                                                                    if val > sensor.soil_calibration_max[i]:
                                                                        val = sensor.soil_calibration_max[i]
                                                                    if val < sensor.soil_calibration_min[i]:
                                                                        val = sensor.soil_calibration_min[i]
                                                                    calculate_soil[i] = maping(val, float(sensor.soil_calibration_min[i]), float(sensor.soil_calibration_max[i]), 0.0, 100.0)
                                                                    calculate_soil[i] = round(calculate_soil[i], 1)
                                                                if calculate_soil[i] > 100:
                                                                    calculate_soil[i] = 100
                                                                if calculate_soil[i] < 0:
                                                                    calculate_soil[i] = 0
                                                                if state[i] > 0.1:   
                                                                    sensor_result += u'{}: {}% '.format(sensor.soil_probe_label[i], calculate_soil[i])
                                                            else:
                                                                err_check += 1
                                                        if err_check > 15:
                                                            sensor_result += _(u'Probe Error')

                                                    if sensor.com_type == 0: # Wi-Fi/LAN
                                                        sensor_result += u' ' + _(u'Last Wi-Fi signal: {}%, Source: {}V.').format(sensor.rssi, sensor.last_battery)
                                                    if sensor.com_type == 1: # Radio
                                                        sensor_result += u' ' + _(u'Last Radio signal: {}%, Source: {}V.').format(sensor.rssi, sensor.last_battery)
                                            else:
                                                sensor_result += _(u'No response!')
                                        else:
                                            sensor_result += _(u'Disabled')

                                        body += sensor_result
                                        body += u'</li>'
                                        logtext += sensor_result
                                        logtext += u'\n'
                                    body += u'</ul>'
                                    body += u'<br>'
                                        
                                else:
                                    sensor_result += _(u'No sensors available')
                                    body += u'<ul><li>'
                                    body += sensor_result
                                    body += u'</li></ul>'
                                    body += u'<br>'
                                    logtext += sensor_result
                                    logtext += u'\n'
                                    
                            except:
                                log.debug(NAME, _(u'E-mail plug-in') + ':\n' + traceback.format_exc())
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
                                log.info(NAME, _(u'Unsent E-mails in queue (in file)') + ': ' + str(len_saved_emails))
                                try:                                    # try send e-mail
                                    sendtext = u'%s' % saved_emails[0]["text"]
                                    sendsubject = u'%s' % (saved_emails[0]["subject"] + '-' + _(u'sending from queue.'))
                                    sendattachment = u'%s' % saved_emails[0]["attachment"]
                                    email(sendtext, sendsubject, sendattachment) # send e-mail  
                                    send_interval = 10000               # repetition of 10 seconds
                                    del saved_emails[0]                 # delete sent email in file
                                    write_email(saved_emails)           # save to file after deleting an item
                                    if len(saved_emails) == 0:
                                        log.clear(NAME)
                                        log.info(NAME, _(u'All unsent E-mails in the queue have been sent.'))

                                except Exception:
                                    #print traceback.format_exc()
                                    send_interval = 60000               # repetition of 60 seconds   
                    except:
                        log.error(NAME, _(u'E-mail plug-in') + ':\n' + traceback.format_exc())  

                self._sleep(2)

            except Exception:
                log.error(NAME, _(u'E-mail plug-in') + ':\n' + traceback.format_exc())
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

def safeStr(obj):
    try: 
       return str(obj)
    except:
       return "u'" + u' '.join(obj).encode('utf-8').strip() + "'"

def email(text, subject=None, attach=None):
    """Send email with with attachments. If subject is None, the default will be used."""
    if email_options['emlusr'] != '' and email_options['emlpwd'] != '' and email_options['emladr0'] != '' and email_options['emlserver'] != '' and email_options['emlport'] != '':
        recipients_list = [email_options['emladr'+str(i)] for i in range(5) if email_options['emladr'+str(i)]!='']
        SMTP_user = email_options['emlusr']       # SMTP username
        SMTP_pwd = email_options['emlpwd']        # SMTP password
        SMTP_server = email_options['emlserver']  # SMTP server address
        SMTP_port = email_options['emlport']      # SMTP port
        mail_server = smtplib.SMTP(SMTP_server, int(SMTP_port)) # mail_server = smtplib.SMTP("smtp.gmail.com", 587)
        mail_server.ehlo()
        mail_server.starttls()
        mail_server.ehlo()
        mail_server.login(SMTP_user, SMTP_pwd)
        # --------------
        msg = MIMEMultipart()

        mail_from = SMTP_user if email_options['emlsender'] else options.name  # From Name
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
            mail_server.sendmail(mail_from, recipients_list, msg.as_string())   # name + e-mail address in the From: field

        mail_server.quit()    

    else:
        raise Exception(_(u'E-mail plug-in is not properly configured!'))


def read_saved_emails():
###Read saved emails from json file.###
    try:
        with open(os.path.join(plugin_data_dir(), 'saved_emails.json')) as saved_emails:
            return json.load(saved_emails)
    except IOError:
        return []     

def write_email(json_data):
###Write e-mail data to json file.###
    with open(os.path.join(plugin_data_dir(), 'saved_emails.json'), 'w') as saved_emails:
        json.dump(json_data, saved_emails)  

def update_saved_emails(data):
###Update data in json files.### 
    try:                                                              # exists file: saved_emails.json?
        saved_emails = read_saved_emails()                       
    except:                                                           # no! create empty file
        write_email([])
        saved_emails = read_saved_emails()
        
    saved_emails.insert(0, data)
    write_email(saved_emails)

                   
def try_mail(text, logtext, attachment=None, subject=None):
###Try send e-mail###   
    log.clear(NAME)
    try:
        email(text, subject, attachment)  # send email with attachment from
        log.info(NAME, _(u'E-mail was sent') + ':\n' + logtext)
        if not options.run_logEM:
            log.info(NAME, _(u'E-mail logging is disabled in options...'))
        else:    
            logEM.save_email_log(subject or email_options['emlsubject'], logtext, _(u'Sent'))

    except Exception:
        log.error(NAME, _(u'E-mail was not sent! Connection to Internet not ready.'))
        logEM.save_email_log(subject or email_options['emlsubject'], logtext, _(u'E-mail was not sent! Connection to Internet not ready.'))
        if not options.run_logEM:
            log.info(NAME, _(u'E-mail logging is disabled in options...'))
            
        if email_options["emlrepeater"]: # saving e-mails is enabled  
            data = {}
            data['date'] = str(datetime.now().strftime('%d.%m.%Y'))
            data['time'] = str(datetime.now().strftime('%H:%M:%S'))   
            data['text'] = u'%s' % text
            data['logtext'] = u'%s' % logtext
            data['subject'] = u'%s' % email_options['emlsubject']
            data['attachment'] = u'%s' % attachment

            update_saved_emails(data)    # saving e-mail data to file: saved_emails.json        

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

################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering email adjustments."""

    def GET(self):
        return self.plugin_render.email_notifications(email_options, log.events(NAME))

    def POST(self):
        global saved_emails
        
        email_options.web_update(web.input())
        qdict = web.input()
        test = get_input(qdict, 'test', False, lambda x: True)
        delete = get_input(qdict, 'del', False, lambda x: True)

        if email_sender is not None:
            email_sender.update()

            if test:
                body = datetime_string() + ': ' + _(u'This is test e-mail from OSPy. You can ignore it.')
                logtext = _(u'This is test e-mail from OSPy. You can ignore it.')
                try_mail(body, logtext)
            
            if delete:
                log.info(NAME, datetime_string() + ': ' + _(u'Email Queue was deleted.'))         
                write_email([])
                saved_emails = 0

        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.email_notifications_help()


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(email_options)
