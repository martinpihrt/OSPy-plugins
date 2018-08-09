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
                   
    def try_mail(self, text, attachment=None, subject=None):
        log.clear(NAME)
        try:
            email(text, attach=attachment)  # send email with attachment from
            log.info(NAME, _('Email was sent') + ':\n' + text)
            if not options.run_logEM:
                log.info(NAME, _('Email logging is disabled in options...'))
            logEM.save_email_log(subject or email_options['emlsubject'], text, _('Sent'))

        except Exception:
            log.error(NAME, _('Email was not sent!') + '\n' + traceback.format_exc())
            logEM.save_email_log(subject or email_options['emlsubject'], text, _('Unsent'))
            if not options.run_logEM:
                log.info(NAME, _('Email logging is disabled in options...'))

    def run(self):
        last_rain = False
        finished_count = len([run for run in log.finished_runs() if not run['blocked']])

        if email_options["emlpwron"]:  # if eml_power_on send email is enable (on)
            body = (datetime_string() + ': ' + _('System was powered on.'))

            if email_options["emllog"]:
                file_exists = os.path.exists(EVENT_FILE)
                if file_exists:
                   self.try_mail(body, EVENT_FILE)
                else:
                   body += '\n' + _('Error -  events.log file not exists!')
                   print body
                   self.try_mail(body)
            else:
                self.try_mail(body)

        while not self._stop.is_set():
            try:
                # Send E-amil if rain is detected
                if email_options["emlrain"]:
                    if inputs.rain_sensed() and not last_rain:
                        body = (datetime_string() + ': ' + _('System detected rain.'))
                        self.try_mail(body)
                    last_rain = inputs.rain_sensed()

                # Send E-mail if a new finished run is found
                if email_options["emlrun"]:
                    finished = [run for run in log.finished_runs() if not run['blocked']]
                    if len(finished) > finished_count:
                        body = datetime_string() + ':\n'
                        for run in finished[finished_count:]:
                            duration = (run['end'] - run['start']).total_seconds()
                            minutes, seconds = divmod(duration, 60)
                            
                            body += _('Finished run') + ':\n'
                            body += '<br>' + _('Program') + ': %s\n' % run['program_name']
                            body += '<br>' + _('Station') + ': %s\n' % stations.get(run['station']).name
                            body += '<br>' + _('Start time') + ': %s \n' % datetime_string(run['start'])
                            body += '<br>' + _('Duration') + ': %02d:%02d\n' % (minutes, seconds)
                            
                            cm = None
                            try:
                                from plugins import tank_humi_monitor
                                cm = tank_humi_monitor.get_sonic_tank_cm()
                                if cm > 0:
                                    cm = str(cm) + " cm"
                                else: 
                                    cm = _('Error - I2C device not found!')
                                    
                                body += '<br>' + _('Water level in tank') + ': %s \n' % (cm)    
                            
                            except Exception:
                                pass
                                
                            result = None    
                            try:
                                from plugins import air_temp_humi
                                result = air_temp_humi.DS18B20_read_string_data()
                                 
                                if result: 
                                    body += '<br>' + _('Temperature DS1-DS6') + ': %s \n' % (result)    
                
                            except Exception:
                                pass

                        self.try_mail(body)
                        
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
                body = (datetime_string() + ': ' + _('This is test e-mail from e-mail notification plugin.'))
                email_sender.try_mail(body)


        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(email_options)
