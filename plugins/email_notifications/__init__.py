# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
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


NAME = 'E-mail Notifications'
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
        'emlsubject': _('Report from OSPy SYSTEM'),
        'emlrepeater': True
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

    def run(self):
        time.sleep(
            randint(3, 10)
        )  # Sleep some time to prevent printing before startup information

        send_interval = 5000  # default time for sending between e-mails (ms)
        last_millis   = 0     # timer for repeating sending e-mails (ms)
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
                   try_mail(body, logtext, EVENT_FILE)
                else:
                   body += '<br>' + _('Error -  events.log file not exists!') 
                   try_mail(body, logtext)
            else:
                try_mail(body, logtext)

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
                        try_mail(body, logtext)
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
                            logtext  =  _('Finished run') + '-> ' + _('Program') + u': %s\n' % pname 
                            logtext +=  _('Station') + u': %s\n' % sname
                            logtext +=  _('Start time') + ': %s \n' % datetime_string(run['start'])
                            logtext +=  _('Duration') + ': %02d:%02d\n' % (minutes, seconds)

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
                                    msg =  _('Level') + ': ' + str(cm) + ' ' + _('cm')
                                    msg += ' (' + str(percent) + ' %), '
                                    msg += _('Ping') + ': ' + str(ping) + ' ' + _('cm')
                                    if units:
                                        msg += ', ' + _('Volume') + ': ' + str(volume) + ' ' + _('liters')
                                    else:
                                        msg += ', ' + _('Volume') + ': ' + str(volume) + ' ' + _('m3')    
                                else: 
                                    msg = _('Error - I2C device not found!')

                                body += '<br><b>'  + _('Water') + '</b>'                                    
                                body += '<br>' + _('Water level in tank') + ': %s \n' % (msg)
                                logtext += ' ' + _('Water') + '-> ' + _('Water level in tank') + ': %s \n' % (msg)   
                            
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
                                logtext += ' ' + _('Water Consumption Counter') + ': %s \n' % (msg)   
                            
                            except:
                                pass
                                
                            # Air Temperature and Humidity Monitor   
                            try:
                                from plugins import air_temp_humi    

                                body += '<br><b>' + _('Temperature DS1-DS6') + '</b>'
                                logtext += ' ' + _('Temperature DS1-DS6') + '-> '
                                for i in range(0, air_temp_humi.plugin_options['ds_used']):  
                                    body += '<br>' + u'%s' % air_temp_humi.plugin_options['label_ds%d' % i] + ': ' + u'%.1f \u2103' % air_temp_humi.DS18B20_read_probe(i) + '\n'  
                                    logtext +=  u'%s \n' % air_temp_humi.plugin_options['label_ds%d' % i] + ': ' + u'%.1f \u2103' % air_temp_humi.DS18B20_read_probe(i) + ' ' 

                            except:
                                pass

                        try_mail(body, logtext)
                        
                    self._sleep(1)
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
                                    sendtext = u'%s' % saved_emails[0]["text"]
                                    sendsubject = u'%s' % (saved_emails[0]["subject"] + '-' + _('sending from queue.'))
                                    sendattachment = u'%s' % saved_emails[0]["attachment"]
                                    email(sendtext, sendsubject, sendattachment) # send e-mail  
                                    send_interval = 2000                # repetition of 2 seconds
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
        raise Exception(_('E-mail plug-in is not properly configured!'))


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
        log.info(NAME, _('E-mail was sent') + ':\n' + logtext)
        if not options.run_logEM:
            log.info(NAME, _('E-mail logging is disabled in options...'))
        else:    
            logEM.save_email_log(subject or email_options['emlsubject'], logtext, _('Sent'))

    except Exception:
        log.error(NAME, _('E-mail was not sent! Connection to Internet not ready.'))
        logEM.save_email_log(subject or email_options['emlsubject'], logtext, _('E-mail was not sent! Connection to Internet not ready.'))
        if not options.run_logEM:
            log.info(NAME, _('E-mail logging is disabled in options...'))
            
        if email_options["emlrepeater"]: # saving e-mails is enabled  
            data = {}
            data['date'] = str(datetime.now().strftime('%d.%m.%Y'))
            data['time'] = str(datetime.now().strftime('%H:%M:%S'))   
            data['text'] = u'%s' % text
            data['logtext'] = u'%s' % logtext
            data['subject'] = u'%s' % email_options['emlsubject']
            data['attachment'] = u'%s' % attachment

            update_saved_emails(data)    # saving e-mail data to file: saved_emails.json        


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
                body = datetime_string() + ': ' + _('This is test e-mail from OSPy. You can ignore it.')
                logtext = _('This is test e-mail from OSPy. You can ignore it.')
                try_mail(body, logtext)


        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(email_options)
