# !/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# this plugins send email at google email

import json
import time
import os
import os.path
import traceback
import smtplib
from threading import Thread, Event

from email.encoders import encode_base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.multipart import MIMEBase

import web
from ospy.webpages import ProtectedPage
from plugins import PluginOptions, plugin_url
from ospy.options import options
from ospy.stations import stations
from ospy.inputs import inputs
from ospy.log import log, EVENT_FILE, logEM
from ospy.helpers import datetime_string, get_input

import i18n


NAME = 'Email Notifications'
LINK = 'settings_page'

email_options = PluginOptions(
    NAME,
    {
        'emlpwron': False,
        'emllog': False,
        'emlrain': False,
        'emlrun': False,
        'emlusr': '',
        'emlpwd': '',
        'emladr0': '',
        'emladr1': '',
        'emladr2': '',
        'emladr3': '',
        'emladr4': '',
        'emlsubject': _('Report from OSPy SYSTEM')
    }
)


################################################################################
# Main function loop:                                                          #
################################################################################
class EmailSender(Thread):
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
                   
    def try_mail(self, text, logtext, attachment=None, subject=None):
        log.clear(NAME)
        try:
            email(text, attach=attachment)  # send email with attachment from
            log.info(NAME, _('Email was sent') + ':\n' + text)
            if not options.run_logEM:
                log.info(NAME, _('Email logging is disabled in options...'))
            logEM.save_email_log(subject or email_options['emlsubject'], logtext, _('Sent'))

        except Exception:
            log.error(NAME, _('Email was not sent!') + '\n' + traceback.format_exc())
            logEM.save_email_log(subject or email_options['emlsubject'], logtext, _('Email was not sent!'))
            if not options.run_logEM:
                log.info(NAME, _('Email logging is disabled in options...'))

    def run(self):
        last_rain = False
        body    = ""
        logtext = ""
        finished_count = len([run for run in log.finished_runs() if not run['blocked']])

        if email_options["emlpwron"]:  # if eml_power_on send email is enable (on)
            body += '<b>' + _('System') + '</b> ' + datetime_string()
            body += '<br><p style="color:red;">' + _('System was powered on.') + '</p>'
            logtext = _('System was powered on.')

            if email_options["emllog"]:
                file_exists = os.path.exists(EVENT_FILE)
                if file_exists:
                   self.try_mail(body, logtext, EVENT_FILE)
                else:
                   body += '<br>' + _('Error -  events.log file not exists!') 
                   #print body
                   self.try_mail(body, logtext)
            else:
                self.try_mail(body, logtext)

        while not self._stop.is_set():
            body    = ""
            logtext = ""
            try:
                # Send E-amil if rain is detected
                if email_options["emlrain"]:
                    if inputs.rain_sensed() and not last_rain:
                        body += '<b>' + _('System') + '</b> ' + datetime_string() 
                        body += '<br><p style="color:red;">' + _('System detected rain.') + '</p>'
                        logtext = _('System detected rain.')
                        self.try_mail(body, logtext)
                        self._sleep(1)
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
                            body += '<b>' + _('System') + '</b> ' + datetime_string()
                            body += '<br><b>'  + _('Finished run') + '</b>'
                            body += '<br>' + _('Program') + u': %s \n' % pname
                            body += '<br>' + _('Station') + u': %s \n' % sname
                            body += '<br>' + _('Start time') + ': %s \n' % datetime_string(run['start'])
                            body += '<br>' + _('Duration') + ': %02d:%02d\n' % (minutes, seconds)
                            logtext  =  _('Finished run') + '-> ' + _('Program') + u': %s\n' % pname + ', ' 
                            logtext +=  _('Station') + u': %s\n' % sname + ', '
                            logtext +=  _('Start time') + ': %s \n' % datetime_string(run['start'])  + ', '
                            logtext +=  _('Duration') + ': %02d:%02d\n' % (minutes, seconds)

                            # Water Tank Monitor
                            try:
                                from plugins import tank_monitor

                                cm = tank_monitor.get_all_values()[0]
                                percent = tank_monitor.get_all_values()[1]
                                ping = tank_monitor.get_all_values()[2]
                                volume = tank_monitor.get_all_values()[3]
                                msg = ' '
                                if cm > 0:
                                    msg =  _('Level') + ': ' + str(cm) + ' ' + _('cm')
                                    msg += ' (' + str(percent) + ' %), '
                                    msg += _('Ping') + ': ' + str(ping) + ' ' + _('cm')
                                    msg += ', ' + _('Volume') + ': ' + str(volume) + ' ' + _('m3')
                                else: 
                                    msg = _('Error - I2C device not found!')

                                body += '<br><b>'  + _('Water') + '</b>'                                    
                                body += '<br>' + _('Water level in tank') + ': %s \n' % (msg)
                                logtext += ', ' + _('Water') + '-> ' + _('Water level in tank') + ': %s \n' % (msg)   
                            
                            except:
                                pass


                            # Water Consumption Counter
                            try:
                                self._sleep(2) # wait for the meter to save consumption

                                from plugins import water_consumption_counter

                                consum_from = water_consumption_counter.get_all_values()[0]
                                consum_one  = water_consumption_counter.get_all_values()[1]
                                consum_two  = water_consumption_counter.get_all_values()[2]

                                msg = ' '
                                msg +=  _('Measured from day') + ': ' + str(consum_from) + ', '
                                msg +=  _('Master Station') + ': ' 
                                if consum_one < 1000:
                                    msg += str(consum_one) + ' ' 
                                    msg += _('Liter') + ', '
                                else: 
                                    msg += str(round((consum_one/1000.0), 2)) + ' ' 
                                    msg += _('m3') + ', '

                                msg +=  _('Second Master Station') + ': '  
                                if consum_two < 1000:
                                    msg += str(consum_two) + ' '
                                    msg += _('Liter') 
                                else: 
                                    msg += str(round((consum_two/1000.0), 2)) + ' ' 
                                    msg += _('m3')

                                body += '<br><b>'  + _('Water Consumption Counter') + '</b>'                                    
                                body += '<br>%s \n' % (msg)
                                logtext += ', ' + _('Water Consumption Counter') + ': %s \n' % (msg)   
                            
                            except:
                                pass
                                
                            # Air Temperature and Humidity Monitor   
                            try:
                                from plugins import air_temp_humi    

                                body += '<br><b>' + _('Temperature DS1-DS6') + '</b>'
                                logtext += ', ' + _('Temperature DS1-DS6') + '-> '
                                for i in range(0, air_temp_humi.plugin_options['ds_used']):  
                                    body += '<br>' + u'%s' % air_temp_humi.plugin_options['label_ds%d' % i] + ': ' + u'%.1f \u2103' % air_temp_humi.DS18B20_read_probe(i) + '\n'  
                                    logtext +=  u'%s' % air_temp_humi.plugin_options['label_ds%d' % i] + ': ' + u'%.1f \u2103' % air_temp_humi.DS18B20_read_probe(i) + ' ' 

                            except:
                                pass

                        self.try_mail(body, logtext)
                        
                    self._sleep(1)
                    finished_count = len(finished)

                self._sleep(1)

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

def safeStr(obj):
    try: 
       return str(obj)
    except:
       return "u'" + u' '.join(obj).encode('utf-8').strip() + "'"

def email(text, subject=None, attach=None):
    """Send email with with attachments. If subject is None, the default will be used."""
    if email_options['emlusr'] != '' and email_options['emlpwd'] != '' and email_options['emladr0'] != '':
        recipients_list = [email_options['emladr'+str(i)] for i in range(5) if email_options['emladr'+str(i)]!='']
        gmail_user = email_options['emlusr']  # User name
        gmail_pwd = email_options['emlpwd']  # User password
        mail_server = smtplib.SMTP("smtp.gmail.com", 587)
        mail_server.ehlo()
        mail_server.starttls()
        mail_server.ehlo()
        mail_server.login(gmail_user, gmail_pwd)
        # --------------
        msg = MIMEMultipart()

        msg['From'] = options.name
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
            mail_server.sendmail('OSPy email sender', recipients_list, msg.as_string())   # name + e-mail address in the From: field

        mail_server.quit()    

    else:
        raise Exception(_('E-mail plug-in is not properly configured!'))


################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering email adjustments."""

    def GET(self):
        return self.plugin_render.email_notifications(email_options, log.events(NAME))

    def POST(self):
        email_options.web_update(web.input())
        qdict = web.input()
        test = get_input(qdict, 'test', False, lambda x: True)

        if email_sender is not None:
            email_sender.update()

            if test:
                body = datetime_string() + ': ' + _('This is test e-mail from e-mail notification plugin.')
                logtext = _('This is test e-mail from e-mail notification plugin.')
                email_sender.try_mail(body, logtext)


        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(email_options)
