# -*- coding: utf-8 -*-
# this plugin read E-mail and control OSPy from msg.

__author__ = 'Martin Pihrt' # www.pihrt.com

# local import
import json
import time
import datetime
import traceback
from threading import Thread, Event

import web

# OSPy import
from ospy import helpers
from ospy.options import options
from ospy.log import log, logEM
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string, reboot, restart, poweroff
from ospy.stations import stations
from ospy.runonce import run_once
from ospy.programs import programs
from ospy.scheduler import predicted_schedule, combined_schedule

# E-mail
import email
import email.header
import imaplib
import os
import sys


NAME = 'E-mail Reader'
MENU =  _('Package: E-mail Reader')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {  'use_reader': False,
       'recipient' : '...@gmail.com',
       'user_password' : '',
       'server' : 'imap.gmail.com',
       'use_ssl': True,
       'move_to_trash': True,
       'recipient_folder': 'INBOX',
       'sender': 'xx@yy.zz',
       'check_int': 30,
       'scheduler_on': _('scheduler_on'),
       'scheduler_off': _('scheduler_off'),
       'manual_on': _('manual_on'),
       'manual_off': _('manual_off'),
       'stop_run': _('stop_run'),
       'send_help': _('send_help'),
       'send_state': _('send_state'), 
       'use_reply': True, 
       'eml_subject':  _('Report from OSPy E-mail Reader plugin'),
       'eml_subject_in': 'ospy_1',
       'p0': 'reboot',
       'p1': 'runP1',
       'p2': 'runP2',
       'p3': 'runP3',
       'p4': 'runP4',
       'p5': 'runP5',
       'p6': 'runP6',
       'p7': 'runP7',
       'p8': 'runP8',
       'p9': 'pwrOff',
       'pc0': _('Reboot OS system'),
       'pc1': _('Run program 1'),
       'pc2': _('Run program 2'),
       'pc3': _('Run program 3'),
       'pc4': _('Run program 4'),
       'pc5': _('Run program 5'),
       'pc6': _('Run program 6'),
       'pc7': _('Run program 7'),
       'pc8': _('Run program 8'),                                                      
       'pc9': _('Shutdown OS system'),
       'send_state_airtemp': _('send_temperatures'), 
       'send_state_tank': _('send_tank'), 
       'send_state_wind': _('send_wind')
    }
)

################################################################################
# Main function loop:                                                          #
################################################################################

class Sender(Thread):
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
        last_email_millis = 0    # timer for reading E-mails (ms)
        
        while not self._stop_event.is_set():
            try:
                msgem = ''
                msglog = ''
                attachment = None
                if plugin_options['use_reader']: 
                    email_interval = plugin_options['check_int']*1000   # time for reading E-mails (ms) -> 1 minute = 1000ms*60s -> 60000ms
                    millis = int(round(time.time() * 1000))             # actual time in ms
                    if(millis - last_email_millis) >= email_interval:   # is time for reading?
                        last_email_millis = millis
                        log.clear(NAME)
                        imap = ImapClient(recipient=plugin_options['recipient'], user_password=plugin_options['user_password'], server=plugin_options['server'],\
                            use_ssl=plugin_options['use_ssl'], move_to_trash=plugin_options['move_to_trash'], recipient_folder=plugin_options['recipient_folder'])
                        log.info(NAME, datetime_string() + ' ' + _('Try-ing login to E-mail.'))
                        is_login_ok = imap.login()     
                        if is_login_ok:
                            messages = imap.get_messages(sender=plugin_options['sender']) # retrieve messages from a given sender
                            log.info(NAME, datetime_string() + ' ' + _('Reading messages in inbox.'))   
                            # Do something with the messages                 
                            for msg in messages:               # msg is a dict of {'num': num, 'body': body, 'subj': subj} 
                                cm = '%s' % msg['body']
                                cmd = cm.replace('\r\n', '')   # remove \r\n from {'body': 'scheduler_on\r\n'}
                                subj = msg['subj']

                                log.info(NAME, _('Message: %s') % cmd)      
                                log.info(NAME, _('Subject: %s') % subj)      

                                if  cmd == plugin_options['scheduler_on'] and subj == plugin_options['eml_subject_in']:  # msg for switch scheduler to on
                                    options.scheduler_enabled = True
                                    log.info(NAME, datetime_string() + ' ' + _('Scheduler has switched to enabled.'))
                                    msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                    msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + ' ' + _('Scheduler has switched to enabled.') + '</p>'
                                    msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd

                                elif cmd == plugin_options['scheduler_off'] and subj == plugin_options['eml_subject_in']: # msg for switch scheduler to off 
                                    options.scheduler_enabled = False
                                    log.info(NAME, datetime_string() + ' ' + _('Scheduler has switched to disabled.'))
                                    msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                    msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + ' ' + _('Scheduler has switched to disabled.') + '</p>'
                                    msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd                                    

                                elif cmd == plugin_options['manual_on'] and subj == plugin_options['eml_subject_in']:     # msg for switch to manual   
                                    options.manual_mode = True
                                    log.info(NAME, datetime_string() + ' ' + _('OSPy has switched to manual control.')) 
                                    msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                    msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + ' ' + _('OSPy has switched to manual control.') + '</p>'
                                    msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd                                      

                                elif cmd == plugin_options['manual_off'] and subj == plugin_options['eml_subject_in']:    # msg for switch to scheduler   
                                    options.manual_mode = False
                                    log.info(NAME, datetime_string() + ' ' + _('OSPy has switched to scheduler controler.')) 
                                    msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                    msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + ' ' + _('OSPy has switched to scheduler controler.') + '</p>'
                                    msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd                                     

                                elif cmd == plugin_options['stop_run'] and subj == plugin_options['eml_subject_in']:      # msg for stop all run stations   
                                    programs.run_now_program = None
                                    run_once.clear()
                                    log.finish_run(None)
                                    stations.clear()
                                    log.info(NAME, datetime_string() + ' ' + _('OSPy has stop all running stations.')) 
                                    msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                    msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + ' ' + _('OSPy has stop all running stations.') + '</p>'
                                    msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd  

                                elif cmd == plugin_options['send_state_airtemp'] and subj == plugin_options['eml_subject_in']:      # msg for get temperatures from plugin   
                                    # Air Temperature and Humidity Monitor   
                                    try:
                                      msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                      msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                      from plugins import air_temp_humi  

                                      msgem += '<br><b>' + _('Temperature DS1-DS6') + '</b>'
                                      for i in range(0, air_temp_humi.plugin_options['ds_used']):  
                                        msgem += '<br>' + '%s' % air_temp_humi.plugin_options['label_ds%d' % i] + ': ' + '%.1f \u2103' % air_temp_humi.DS18B20_read_probe(i) + '\n'  
                                      log.info(NAME, datetime_string() + ' ' + _('OSPy has send all temperatures and log file if exists.'))  

                                      if air_temp_humi.plugin_options['enable_log']:
                                        file_name = temperature_json_to_csv()

                                        if file_name:
                                          attachment = file_name
                                          msgem += '<br/><p>' + _('OSPy has send all temperatures and log file.') + '</p>'
                                        else:
                                          log.error(NAME,  _('Log file not exists!'))  
                                          attachment = None
                                          msgem += '<br/><p style="color:red;">' + _('Log file not exists!') + '</p>'

                                      else:    
                                        attachment = None
                                      msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd   

                                    except:
                                      log.info(NAME, _('Command') + _(': %s') % cmd) 
                                      log.info(NAME, _('The command has been not processed!'))
                                      msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _('The command has been not processed!') + '</p>'
                                      msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                      msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been not processed!') + ' ' + _('MSG: %s') % cmd                                      
                                      pass  

                                elif cmd == plugin_options['send_state_tank'] and subj == plugin_options['eml_subject_in']:      # msg for get water tank from plugin   
                                      # Water tank Monitor   
                                      from plugins import tank_monitor 

                                      try:
                                        cm = tank_monitor.get_all_values()[0]
                                        percent = tank_monitor.get_all_values()[1]
                                        ping = tank_monitor.get_all_values()[2]
                                        volume = tank_monitor.get_all_values()[3]
                                        units = tank_monitor.get_all_values()[4]                          
                                        ook = True
                                      except:
                                        ook = False  
                                        pass

                                      try:   
                                        if cm > 0 and ook:
                                          ms = ''
                                          ms += '<p>' + _('Level') + ': ' + str(cm) + ' ' + _('cm')
                                          ms += ' (' + str(percent) + ' %)</p>' 
                                          ms += '<p>' + _('Ping') + ': ' + str(ping) + ' ' + _('cm') + '</p>'
                                          if units:
                                            ms += '<p>' + _('Volume') + ': ' + str(volume) + ' ' + _('liters') + '</p>'
                                          else:
                                            ms += '<p>' + _('Volume') + ': ' + str(volume) + ' ' + _('m3') + '</p>'    
                                          msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                          msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'                                      
                                          msgem += '<br/><b>'  + _('Water') + '</b>'
                                          msgem += '<br/><p>' + '%s' % (ms) + '</p>'
                                          log.info(NAME, datetime_string() + ' ' + _('OSPy has send tank states and log file if exists.'))

                                        if cm < 1 and ook:   
                                          msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _('The command has been not processed!') + '</p>'
                                          msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                          msgem += '<br/><p style="color:red;">' + _('Error - Water tank plugin has water level < 1cm!') + '</p>'
                                          msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been not processed!') + ' ' + _('MSG: %s') % cmd
                                          log.info(NAME, datetime_string() + ' ' + _('Error - Water tank plugin has water level < 1cm!'))  

                                        if not ook:  
                                          msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _('The command has been not processed!') + '</p>'
                                          msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                          msgem += '<br/><p style="color:red;">' + _('Error - Plugin is not correctly setuped or not run!') + '</p>'
                                          msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been not processed!') + ' ' + _('MSG: %s') % cmd
                                          log.info(NAME, datetime_string() + ' ' + _('Error - Plugin water tank is not correctly setuped or not run!'))  

                                        if tank_monitor.tank_options['enable_log'] and ook:
                                          file_name = tank_json_to_csv()
                                          if file_name:
                                            attachment = file_name
                                            msgem += '<br/><p>' + _('OSPy has send tank states and log file.') + '</p>'
                                          else:
                                            log.error(NAME,  _('Log file not exists!'))  
                                            attachment = None
                                            msgem += '<br/><p style="color:red;">' + _('Log file not exists!') + '</p>'
                                        else:    
                                          attachment = None
                                        msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd  

                                      except:
                                        log.info(NAME, _('Command') + _(': %s') % cmd) 
                                        log.info(NAME, _('The command has been not processed!'))
                                        msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _('The command has been not processed!') + '</p>'
                                        msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                        msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been not processed!') + ' ' + _('MSG: %s') % cmd                                      
                                        pass    

                                elif cmd == plugin_options['send_state_wind'] and subj == plugin_options['eml_subject_in']:      # msg for get wind from plugin   
                                    # Wind Monitor   
                                    try:
                                      from plugins import wind_monitor  

                                      try:
                                        speed = wind_monitor.get_all_values()[0]
                                        max_speed = wind_monitor.get_all_values()[1]                          
                                        ook = True
                                      except:
                                        ook = False  
                                        pass                                      

                                      if ook:  
                                        log.info(NAME, datetime_string() + ' ' + _('OSPy has send wind state and log file if exists.'))  
                                        msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                        msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'                                      
                                        msgem += '<br/><b>'  + _('Wind speed') + '</b>'
                                        ms = ''
                                        if wind_monitor.wind_options['use_kmh']:
                                          ms += '<p>' + _('Speed') + ': ' + '%.1f' % (speed) + ' ' + _('km/h') + '</p>'
                                          ms += '<p>' + _('Maximal speed') + ': ' + '%.1f' % (max_speed) + ' ' + _('km/h') + '</p>'
                                        else:
                                          ms += '<p>' + _('Speed') + ': ' + '%.1f' % (speed) + ' ' + _('m/sec') + '</p>'
                                          ms += '<p>' + _('Maximal speed') + ': ' + '%.1f' % (max_speed) + ' ' + _('m/sec') + '</p>'  

                                        msgem += '<br/><p>' + '%s' % (ms) + '</p>'

                                      if not ook:  
                                        msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _('The command has been not processed!') + '</p>'
                                        msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                        msgem += '<br/><p style="color:red;">' + _('Error - Plugin is not correctly setuped or not run!') + '</p>'
                                        msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been not processed!') + ' ' + _('MSG: %s') % cmd
                                        log.info(NAME, datetime_string() + ' ' + _('Error - Plugin wind monitor is not correctly setuped or not run!'))                                         

                                      if wind_monitor.wind_options['enable_log'] and ook:
                                        file_name = wind_json_to_csv()

                                        if file_name:
                                          attachment = file_name
                                          msgem += '<br/><p>' + _('OSPy has send wind state and log file.') + '</p>'
                                        else:
                                          log.error(NAME,  _('Log file not exists!'))  
                                          attachment = None
                                          msgem += '<br/><p style="color:red;">' + _('Log file not exists!') + '</p>'

                                      else:    
                                        attachment = None
                                      msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd   

                                    except:
                                      log.error(NAME, traceback.format_exc())
                                      log.info(NAME, _('Command') + _(': %s') % cmd) 
                                      log.info(NAME, _('The command has been not processed!'))
                                      msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _('The command has been not processed!') + '</p>'
                                      msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                      msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been not processed!') + ' ' + _('MSG: %s') % cmd                                      
                                      pass                                                                                            

                                elif cmd == plugin_options['send_help'] and subj == plugin_options['eml_subject_in']:     # msg for sending back help via email   
                                    log.info(NAME, datetime_string() + ' ' + _('OSPy sends the set commands to the administrator by E-mail.'))  
                                    msgem += '<style>tr:nth-child(even) {background-color: #f2f2f2;} </style>'
                                    msgem += '<div style="overflow-x:auto;">' 
                                    msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                    msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + '</p><p><b>' + _('All available commands in plugin') + ':</p>'
                                    msgem += '<p>' + '<table style="text-align: left; cellspacing="0"; cellpadding="6"; border="1";>'
                                    msgem += '<tr><td>' + _('Switch scheduler to ON') + ':</td>'
                                    msgem += '<td>' + plugin_options["scheduler_on"] + '</td></tr>'
                                    msgem += '<tr><td>' + _('Switch scheduler to OFF') + ':</td>'
                                    msgem += '<td>' + plugin_options["scheduler_off"] + '</td></tr>' 
                                    msgem += '<tr><td>' + _('Switch to manual mode') + ':</td>'
                                    msgem += '<td>' + plugin_options["manual_on"] + '</td></tr>'   
                                    msgem += '<tr><td>' + _('Switch to scheduler mode') + ':</td>'
                                    msgem += '<td>' + plugin_options["manual_off"] + '</td></tr>'   
                                    msgem += '<tr><td>' + _('Stop all running stations') + ':</td>'
                                    msgem += '<td>' + plugin_options["stop_run"] + '</td></tr>'                                                                                                                                          
                                    msgem += '<tr><td>' + _('Send back help') + ':</td>'
                                    msgem += '<td>' + plugin_options["send_help"] + '</td></tr>' 
                                    msgem += '<tr><td>' + _('Sending back temperature states') + ':</td>'
                                    msgem += '<td>' + plugin_options["send_state_airtemp"] + '</td></tr>'
                                    msgem += '<tr><td>' + _('Sending back tank states') + ':</td>'
                                    msgem += '<td>' + plugin_options["send_state_tank"] + '</td></tr>'
                                    msgem += '<tr><td>' + _('Sending back wind states') + ':</td>'
                                    msgem += '<td>' + plugin_options["send_state_wind"] + '</td></tr>'                                                                                                            
                                    for i in range(10):
                                        msgem += '<tr><td>' + _('Selecting command %d') % i + ':</td>'
                                        msgem += '<td>' + '%s' % plugin_options["pc%d" % i] + '</td></tr>'
                                    msgem += '<tr><td>' + _('Sending message in body E-mail as list (use in manual mode)') + ':</td>'
                                    msgem += '<td>' + _('Station 1 -> OFF, 2 -> OFF, 3 -> ON 100 second, 4 -> ON 30 second...') + '</td>'
                                    msgem += '<td>' + _('[0,0,100,30,...]') + '</td></tr>' 
                                    msgem += '<tr><td>' + _('Sending message in body E-mail as dict (use in manual mode)') + ':</td>'
                                    msgem += '<td>' + _('Station 1 -> OFF, 2 -> OFF, 3 -> ON 100 second, 4 -> ON 30 second...') + '</td>'
                                    msgem += '<td>' + _('{"aa":0,"bb":0,"cc":100,"dd":30...}') + '</td></tr>'
                                    msgem += '</table></p></div>' 
                                    msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd    

                                elif cmd == plugin_options['send_state'] and subj == plugin_options['eml_subject_in']:     # msg for sending stations state via email  
                                    log.info(NAME, datetime_string() + ' ' + _('OSPy sends the stations state to the administrator E-mail.'))  
                                    msgem += '<style>tr:nth-child(even) {background-color: #f2f2f2;} </style>'
                                    msgem += '<div style="overflow-x:auto;">' 
                                    msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                    msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + '</p><p>' + _('Actual stations state') + ':</p>'
                                    msgem += '<p>' + '<table style="text-align: left; cellspacing="0"; cellpadding="6"; border="1";>'
                                    msgem += '<tr><td><b>' + _('Station name') + '</b></td><td><b>' + _('State') + '</b></td><td><b>' + _('Main 1') + '</b></td><td><b>' + _('Main 2')
                                    msgem += '</b></td><td><b>' + _('Remaining time in sec') + '</b></td></tr>'
                                    for station in stations.get():
                                        msgem += '<tr><td>' + '%s' % station.name + '</td>'
                                        if station.active:
                                            msgem += '<td>' + _('ON') + '</td>'
                                        else:
                                            msgem += '<td>' + _('OFF') + '</td>'
                                        if station.is_master:
                                            msgem += '<td>' + _('YES') + '</td>'
                                        else:
                                            msgem += '<td>' + _('-') + '</td>'    
                                        if station.is_master_two:    
                                            msgem += '<td>' + _('YES') + '</td>' 
                                        else:
                                            msgem += '<td>' + _('-') + '</td>'
                                        if(station.remaining_seconds == -1):
                                            msgem += '<td>' + _('Forever') + '</td>' 
                                        else:    
                                            msgem += '<td>' + _('%s') % str(int(station.remaining_seconds)) + '</td>'
    
                                    msgem += '</tr></table></p></div>' 
                                    msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd   

                                elif cmd == plugin_options['p0'] or cmd == plugin_options['p1'] or cmd == plugin_options['p2'] or cmd == plugin_options['p3'] or cmd == plugin_options['p4'] or cmd == plugin_options['p5'] or cmd ==plugin_options['p6'] or cmd ==plugin_options['p7'] or cmd ==plugin_options['p8'] or cmd ==plugin_options['p9']:                                      
                                    for i in range(10): 
                                        if cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "reboot" and subj == plugin_options['eml_subject_in']: # msg for reboot via email
                                            log.info(NAME, datetime_string() + ': ' + _('System Linux has now reboot!'))                                             
                                            msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                            msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _('System Linux has now reboot!') + '</p>'
                                            msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd
                                            stations.clear()
                                            reboot(wait=10) # after 10 seconds
                                            break
                                                 
                                        elif cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "pwrOff" and subj == plugin_options['eml_subject_in']: # msg for shuttdown via email
                                            log.info(NAME, datetime_string() + ': ' + _('System Linux has now shutdown!'))
                                            msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                            msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _('System Linux has now shutdown!') + '</p>'
                                            msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd                                            
                                            stations.clear()
                                            poweroff(wait=10) # after 10 seconds
                                            break

                                        elif cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "runP1" and subj == plugin_options['eml_subject_in']: # msg for run program 1 via email
                                            log.info(NAME, datetime_string() + ' ' + _('OSPy has switched to scheduler controler.') + ' ' + _('Run now program 1.')) 
                                            msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                            msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _('Run now program 1.') + ' ' + _('OSPy has switched to scheduler controler.') + '</p>'
                                            msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd                                             
                                            for program in programs.get():
                                                if (program.index == 0):   # Run-now program 1
                                                    options.manual_mode = False   
                                                    log.finish_run(None)
                                                    stations.clear()    
                                                    programs.run_now(program.index)
                                                    break       
                                                program.index+1

                                        elif cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "runP2" and subj == plugin_options['eml_subject_in']: # msg for run program 2 via email
                                            log.info(NAME, datetime_string() + ' ' + _('OSPy has switched to scheduler controler.') + ' ' + _('Run now program 2.')) 
                                            msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                            msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _('Run now program 2.') + ' ' + _('OSPy has switched to scheduler controler.') + '</p>'
                                            msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd                                             
                                            for program in programs.get():
                                                if (program.index == 1):   # Run-now program 2
                                                    options.manual_mode = False   
                                                    log.finish_run(None)
                                                    stations.clear()    
                                                    programs.run_now(program.index) 
                                                    break      
                                                program.index+1 

                                        elif cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "runP3" and subj == plugin_options['eml_subject_in']: # msg for run program 3 via email
                                            log.info(NAME, datetime_string() + ' ' + _('OSPy has switched to scheduler controler.') + ' ' + _('Run now program 3.')) 
                                            msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                            msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _('Run now program 3.') + ' ' + _('OSPy has switched to scheduler controler.') + '</p>'
                                            msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd                                             
                                            for program in programs.get():
                                                if (program.index == 2):   # Run-now program 3
                                                    options.manual_mode = False   
                                                    log.finish_run(None)
                                                    stations.clear()    
                                                    programs.run_now(program.index) 
                                                    break      
                                                program.index+1       

                                        elif cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "runP4" and subj == plugin_options['eml_subject_in']: # msg for run program 4 via email
                                            log.info(NAME, datetime_string() + ' ' + _('OSPy has switched to scheduler controler.') + ' ' + _('Run now program 4.')) 
                                            msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                            msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _('Run now program 4.') + ' ' + _('OSPy has switched to scheduler controler.') + '</p>'
                                            msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd                                             
                                            for program in programs.get():
                                                if (program.index == 3):   # Run-now program 4
                                                    options.manual_mode = False   
                                                    log.finish_run(None)
                                                    stations.clear()    
                                                    programs.run_now(program.index) 
                                                    break      
                                                program.index+1                                                                                                                                                    

                                        elif cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "runP5" and subj == plugin_options['eml_subject_in']: # msg for run program 5 via email
                                            log.info(NAME, datetime_string() + ' ' + _('OSPy has switched to scheduler controler.') + ' ' + _('Run now program 5.')) 
                                            msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                            msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _('Run now program 5.') + ' ' + _('OSPy has switched to scheduler controler.') + '</p>'
                                            msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd                                             
                                            for program in programs.get():
                                                if (program.index == 4):   # Run-now program 5
                                                    options.manual_mode = False   
                                                    log.finish_run(None)
                                                    stations.clear()    
                                                    programs.run_now(program.index)  
                                                    break     
                                                program.index+1    

                                        elif cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "runP6" and subj == plugin_options['eml_subject_in']: # msg for run program 6 via email
                                            log.info(NAME, datetime_string() + ' ' + _('OSPy has switched to scheduler controler.') + ' ' + _('Run now program 6.')) 
                                            msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                            msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _('Run now program 6.') + ' ' + _('OSPy has switched to scheduler controler.') + '</p>'
                                            msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd                                             
                                            for program in programs.get():
                                                if (program.index == 5):   # Run-now program 6
                                                    options.manual_mode = False   
                                                    log.finish_run(None)
                                                    stations.clear()    
                                                    programs.run_now(program.index) 
                                                    break      
                                                program.index+1     

                                        elif cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "runP7" and subj == plugin_options['eml_subject_in']: # msg for run program 7 via email
                                            log.info(NAME, datetime_string() + ' ' + _('OSPy has switched to scheduler controler.') + ' ' + _('Run now program 7.')) 
                                            msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                            msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _('Run now program 7.') + ' ' + _('OSPy has switched to scheduler controler.') + '</p>'
                                            msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd                                             
                                            for program in programs.get():
                                                if (program.index == 6):   # Run-now program 7
                                                    options.manual_mode = False   
                                                    log.finish_run(None)
                                                    stations.clear()    
                                                    programs.run_now(program.index)  
                                                    break     
                                                program.index+1    

                                        elif cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "runP8" and subj == plugin_options['eml_subject_in']: # msg for run program 8 via email
                                            log.info(NAME, datetime_string() + ' ' + _('OSPy has switched to scheduler controler.') + ' ' + _('Run now program 8.')) 
                                            msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                            msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _('Run now program 8.') + ' ' + _('OSPy has switched to scheduler controler.') + '</p>'
                                            msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd                                             
                                            for program in programs.get():
                                                if (program.index == 7):   # Run-now program 8
                                                    options.manual_mode = False   
                                                    log.finish_run(None)
                                                    stations.clear()    
                                                    programs.run_now(program.index) 
                                                    break      
                                                program.index+1
                                        else:  
                                            log.info(NAME, _('Subject in message is') + (': %s') % subj)
                                            log.info(NAME, _('Subject in options is') + (': %s') % plugin_options['eml_subject_in'])  
                                            log.info(NAME, _('Command') + _(': %s') % cmd) 
                                            log.info(NAME, _('The command has been not processed!'))
                                            msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _('The command has been not processed!') + '</p>'
                                            msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                            msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been not processed!') + ' ' + _('MSG: %s') % cmd 
                                            break
                                  
                                else:
                                    if not options.manual_mode:              # not manual mode -> no operations with stations
                                        log.error(NAME, datetime_string() + ' ' + _('OSPy must be first switched to manual mode!'))
                                        msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _('The command has been not processed!') + '</p>'
                                        msgem += '<p>' + datetime_string() + ' ' + _('Command') + _(': %s') % cmd + '</p>'
                                        msgem += '<p style="color:red;">' + _('OSPy must be first switched to manual mode!') + '</p>'
                                        msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been not processed!') + ' ' + _('MSG: %s') % cmd
                                    elif subj != plugin_options['eml_subject_in']:
                                        log.error(NAME, datetime_string() + ' ' + _('Subject is not correct!'))
                                        log.error(NAME, _('Subject in message is') + (': %s') % subj)
                                        log.error(NAME, _('Subject in options is') + (': %s') % plugin_options['eml_subject_in'])
                                        msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _('The command has been not processed!') + '</p>'
                                        msgem += '<p>' + _('Command') + _(': %s') % cmd + '</p>'
                                        msgem += '<p style="color:red;">' + _('Subject in message is') + (': %s') % subj + '<br/>'
                                        msgem +=  _('Subject in options is') + (': %s') % plugin_options['eml_subject_in'] + '</p>'                                        
                                        msgem += '<p>' + datetime_string() + ' ' + _('Subject is not correct!') + '</p>'
                                        msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been not processed!') + ' ' + _('MSG: %s') % cmd                                        
                                    else:                                    # yes is manual mode and subject is correct
                                        try:
                                            log.info(NAME, datetime_string() + ' ' + _('Try-ing to processing command.'))
                                            cmd = json.loads(msg['body'])
                                            num_sta = options.output_count
                                            if type(cmd) is list:            # cmd is list
                                                msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _('The command has been processed.') + '</p>'
                                                msgem += '<p>' + datetime_string() + ' ' + _('Command') + (': %s') % cmd + '</p>'
                                                if len(cmd) < num_sta:
                                                    log.info(NAME, datetime_string() + ' ' + _('Not enough stations specified, assuming first {} of {}').format(len(cmd), num_sta))
                                                    rovals = cmd + ([0] * (num_sta - len(cmd)))              
                                                    msgem += '<p>' +  _('Not enough stations specified, assuming first {} of {}').format(len(cmd), num_sta) + '</p>'                                                    
                                                elif len(cmd) > num_sta:
                                                    log.info(NAME, datetime_string() + ' ' + _('Too many stations specified, truncating to {}').format(num_sta))
                                                    rovals = cmd[0:num_sta]
                                                    msgem += '<p>' + _('Too many stations specified, truncating to {}').format(num_sta) + '</p>'                                                    
                                                else:
                                                    rovals = cmd

                                            elif type(cmd) is dict:          # cmd is dictionary
                                                rovals = [0] * num_sta
                                                snames = station_names()     # Load station names from file
                                                jnames = json.loads(snames)  # Load as json
                                                msgem += '<b>' + _('E-mail Reader plug-in') + '</b>'
                                                for k, v in list(cmd.items()):
                                                    if k not in snames:      # station name in dict is not in OSPy stations name (ERROR)
                                                        log.warning(NAME, _('No station named') + (': %s') % k)
                                                        msgem += '<p style="color:red;>' + _('No station named') + (': %s') % k + '</p>'
                                                    else:                    # station name in dict is in OSPy stations name (OK)
                                                        # v is value for time, k is station name in dict
                                                        rovals[jnames.index(k)] = v  

                                                msgem += '<p style="color:green;">' + _('The command has been processed.') + '</p>' 
                                                msgem += '<p>' +  _('MSG: %s') % cmd  + '<p>'         

                                            else:
                                                log.error(NAME, datetime_string() + ' ' + _('Unexpected command') + (': %s') % cmd)
                                                msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _('The command has been not processed!') + '</p>'
                                                msgem += '<p>' + datetime_string() + ' ' + _('Unexpected command') + (': %s') % cmd + '</p>'
                                                msgem += '<p style="color:red;">' + _('Subject in message is') + (': %s') % subj + '<br/>'
                                                msgem +=  _('Subject in options is') + (': %s') % plugin_options['eml_subject_in'] + '</p>'
                                                msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been not processed!') + ' ' + _('MSG: %s') % cmd                                                 
                                                rovals = []   

                                            if any(rovals):  
                                                for i in range(0, len(rovals)):     
                                                    sid = i                                                                                
                                                    start = datetime.datetime.now()
                                                    end = datetime.datetime.now() + datetime.timedelta(seconds=int(rovals[i]))
                                                    new_schedule = {
                                                        'active': True,
                                                        'program': -1,
                                                        'station': sid,
                                                        'program_name': _('E-mail Reader'),
                                                        'fixed': True,
                                                        'cut_off': 0,
                                                        'manual': True,
                                                        'blocked': False,
                                                        'start': start,
                                                        'original_start': start,
                                                        'end': end,
                                                        'uid': '%s-%s-%d' % (str(start), "Manual", sid),
                                                        'usage': stations.get(sid).usage
                                                    }

                                                    log.start_run(new_schedule)
                                                    stations.activate(new_schedule['station'])

                                                    if int(rovals[i]) < 1:                 # station has no time for run (stoping)
                                                        stations.deactivate(sid)
                                                        active = log.active_runs()
                                                        for interval in active:
                                                            if interval['station'] == sid:
                                                                log.finish_run(interval)                                                    

                                                msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been processed.') + ' ' + _('MSG: %s') % cmd

                                            else:
                                                msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _('The command has been not processed!') + '</p>'
                                                msgem += '<p>' + datetime_string() + ' ' + _('Unexpected command') + (': %s') % cmd + '</p>'
                                                msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been not processed!') + ' ' + _('MSG: %s') % cmd     
                                                        
                                        except ValueError as e:
                                            log.error(NAME, datetime_string() + ' ' + _('Could not decode command') + ': %s' % e)
                                            msgem += '<b>' + _('E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _('The command has been not processed!') + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _('Could not decode command') + ': %s' % e + '</p>'
                                            msglog += _('E-mail Reader plug-in') + ': ' + _('The command has been not processed!') + ' ' + _('MSG: %s') % cmd
                                            pass

                                if plugin_options['use_reply']:          # send reply to administrator
                                    log.info(NAME, datetime_string() + ' ' + _('Sending reply to administrator E-mail.'))
                                    try:
                                        from plugins.email_notifications import try_mail                                    
                                        try_mail(msgem, msglog, attachment=attachment, subject=plugin_options['eml_subject']) # try_mail(text, logtext, attachment=None, subject=None)
                                    except Exception:     
                                        log.error(NAME, _('E-mail Reader plug-in') + ':\n' + traceback.format_exc())      
                        
                                if plugin_options['move_to_trash']:      # you could delete them after viewing     
                                    imap.delete_message(msg['num'])
                                    self._sleep(1)
                        
                            imap.logout()                                # when done, you should log out
   
                self._sleep(1)  

            except Exception:
                log.clear(NAME)
                log.error(NAME, _('E-mail Reader plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)


sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global sender
    if sender is None:
        sender = Sender()


def stop():
    global sender
    if sender is not None:
        sender.stop()
        sender.join()
        sender = None


def station_names():
    """ Return station names as a list. """
    station_list = []

    for station in stations.get():
        station_list.append(station.name)

    return json.dumps(station_list)
 

################################################################################
# read/write:                                                                  #
################################################################################

def read_log(path_name=None):
    """Read log data from json file."""
    try:
        if path_name is not None:
            with open(path_name) as logf:
                return json.load(logf)
        else:
            return []    
    except IOError:
        return [] 


def write_log(data, filename):
  """Write data to csv file."""
  try:
    import io
    with io.open(filename,'w', encoding='utf8') as file:
      file.write(data)
      
  except Exception:
    log.error(NAME, traceback.format_exc())
    pass


################################################################################
# json to csv:                                                                 #
################################################################################

def temperature_json_to_csv():
  """save log data from json file to csv file."""
  try:
    from plugins import air_temp_humi

    name1 = air_temp_humi.plugin_options['label_ds0']
    name2 = air_temp_humi.plugin_options['label_ds1']
    name3 = air_temp_humi.plugin_options['label_ds2']
    name4 = air_temp_humi.plugin_options['label_ds3']
    name5 = air_temp_humi.plugin_options['label_ds4']
    name6 = air_temp_humi.plugin_options['label_ds5']
        
    # open json data from plugin air_tem_humi    
    json_plugin_file = './plugins/air_temp_humi/data/log.json'
    file_exists = os.path.exists(json_plugin_file)

    if not file_exists:
      return None
    
    # read log
    log_records = read_log(path_name=json_plugin_file) 

    data  = '%s' % _('Date/Time')
    data += ';\t %s' % _('Date')
    data += ';\t %s' % _('Time')
    data += ';\t %s' % _('Temperature')
    data += ';\t %s' % _('Humidity')
    data += ';\t %s' % _('Output')
    data += ';\t %s' % name1
    data += ';\t %s' % name2
    data += ';\t %s' % name3
    data += ';\t %s' % name4
    data += ';\t %s' % name5
    data += ';\t %s' % name6
    data += '\n'

    for record in log_records:
      data += '%s' %     record['datetime']
      data += ';\t %s' % record['date']
      data += ';\t %s' % record['time']
      data += ';\t %s' % record['temp']
      data += ';\t %s' % record['humi']
      data += ';\t %s' % record['outp']
      data += ';\t %s' % record['ds0']
      data += ';\t %s' % record['ds1']
      data += ';\t %s' % record['ds2']
      data += ';\t %s' % record['ds3']
      data += ';\t %s' % record['ds4']
      data += ';\t %s' % record['ds5']
      data += '\n'

    # save csv file to email_reader plugin data folder
    filename = 'temperature_log.csv'
    csv_plugin_file = './plugins/email_reader/data/' + filename

    write_log(data=data, filename=csv_plugin_file)

    # verify that the file is saved
    file_exists = os.path.exists(csv_plugin_file)

    if not file_exists:
      return None

    return csv_plugin_file # return file name for attach in sending email

  except Exception:
    log.clear(NAME)
    log.error(NAME, _('Conversion error! Temperature data from json file to csv file') + ':\n' + traceback.format_exc())
    return None
       

def tank_json_to_csv():
  """save log data from json file to csv file."""
  try:
    from plugins import tank_monitor

    minimum = _('Minimum')
    maximum = _('Maximum')
    actual  = _('Actual')
    volume  = _('Volume')
        
    # open json data from plugin tank_monitor    
    json_plugin_file = './plugins/tank_monitor/data/log.json'
    file_exists = os.path.exists(json_plugin_file)

    if not file_exists:
      return None
    
    # read log
    log_records = read_log(path_name=json_plugin_file) 

    data  = '%s' % _('Date/Time')
    data += ';\t %s' % _('Date')
    data += ';\t %s' % _('Time')
    data += ';\t %s' % minimum
    data += ';\t %s' % maximum
    data += ';\t %s' % actual
    if tank_monitor.tank_options['check_liters']:
      data += ';\t %s %s' % (volume, _('liters'))
    else:    
      data += ';\t %s %s' % (volume, _('m3'))
    data += '\n'

    for record in log_records:
      data += '%s' %     record['datetime']
      data += ';\t %s' % record['date']
      data += ';\t %s' % record['time']
      data += ';\t %s' % record['minimum']
      data += ';\t %s' % record['maximum']
      data += ';\t %s' % record['actual']
      data += ';\t %s' % record['volume']
      data += '\n'

    # save csv file to email_reader plugin data folder
    filename = 'water_tank_log.csv'
    csv_plugin_file = './plugins/email_reader/data/' + filename

    write_log(data=data, filename=csv_plugin_file)

    # verify that the file is saved
    file_exists = os.path.exists(csv_plugin_file)

    if not file_exists:
      return None

    return csv_plugin_file # return file name for attach in sending email

  except Exception:
    log.clear(NAME)
    log.error(NAME, _('Conversion error! Water tank data from json file to csv file') + ':\n' + traceback.format_exc())
    return None


def wind_json_to_csv():
  """save log data from json file to csv file."""
  try:
    from plugins import wind_monitor

    maximum = _('Maximum')
    actual  = _('Actual')
        
    # open json data from plugin tank_monitor    
    json_plugin_file = './plugins/wind_monitor/data/log.json'
    file_exists = os.path.exists(json_plugin_file)

    if not file_exists:
      return None
    
    # read log
    log_records = read_log(path_name=json_plugin_file) 

    data  = '%s' % _('Date/Time')
    data += ';\t %s' % _('Date')
    data += ';\t %s' % _('Time')
    if wind_monitor.wind_options['use_kmh']: 
      data += ';\t %s %s'  % (maximum, _('km/h'))
      data += ';\t %s %s'  % (actual, _('km/h'))
    else:                       
      data += ';\t %s %s'  % (maximum, _('m/sec'))
      data += ';\t %s %s'  % (actual, _('m/sec'))
    data += '\n'

    for record in log_records:
      data += '%s' %     record['datetime']
      data += ';\t %s' % record['date']
      data += ';\t %s' % record['time']
      data += ';\t %s' % record['maximum']
      data += ';\t %s' % record['actual']
      data += '\n'

    # save csv file to email_reader plugin data folder
    filename = 'wind_log.csv'
    csv_plugin_file = './plugins/email_reader/data/' + filename

    write_log(data=data, filename=csv_plugin_file)

    # verify that the file is saved
    file_exists = os.path.exists(csv_plugin_file)

    if not file_exists:
      return None

    return csv_plugin_file # return file name for attach in sending email

  except Exception:
    log.clear(NAME)
    log.error(NAME, _('Conversion error! Wind monitor data from json file to csv file') + ':\n' + traceback.format_exc())
    return None

################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        try:
            return self.plugin_render.email_reader(plugin_options, log.events(NAME))
        except:
            log.error(NAME, _('E-mail Reader plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('email_reader -> settings_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            plugin_options.web_update(web.input())

            if sender is not None:
                sender.update()

            log.info(NAME, _('Options has updated.'))
            raise web.seeother(plugin_url(settings_page), True)
        except:
            log.error(NAME, _('E-mail Reader plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('email_reader -> settings_page POST')
            return self.core_render.notice('/', msg)

class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            return self.plugin_render.email_reader_help()        
        except:
            log.error(NAME, _('E-mail Reader plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('email_reader -> help_page GET')
            return self.core_render.notice('/', msg)

class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(plugin_options)
        except:
            return {}

################################################################################
# IMAP client:                                                                 #
################################################################################

class ImapClient: # https://www.timpoulsen.com/2018/reading-email-with-python.html
    imap = None

    def __init__(self,
                 recipient,
                 user_password,
                 server,
                 use_ssl,
                 move_to_trash,
                 recipient_folder):
        # check for required param
        if not recipient:
            log.error(NAME, datetime_string() + ' ' + _('You must provide a recipient E-mail address.'))
            return
        if not user_password:
            log.error(NAME, datetime_string() + ' ' + _('You must provide a recipient E-mail password.'))
            return  
        if not server:
            log.error(NAME, datetime_string() + ' ' + _('You must provide server.'))
            return    
        if not recipient_folder:
            log.error(NAME, datetime_string() + ' ' + _('You must provide recipient folder.'))
            return              

        self.recipient = recipient
        self.user_password = user_password
        self.use_ssl = use_ssl
        self.move_to_trash = move_to_trash
        self.recipient_folder = recipient_folder

        if self.use_ssl:
            self.imap = imaplib.IMAP4_SSL(server)
        else:
            self.imap = imaplib.IMAP4(server)

    def login(self):
        try:
            rv, data = self.imap.login(self.recipient, self.user_password) 
            log.info(NAME, datetime_string() + ' ' + _('Login OK.'))
            return True
        except:
            log.error(NAME, datetime_string() + ' ' + _('Mail account login details are not filled in correctly!'))
            return False

    def logout(self):
        self.imap.close()
        self.imap.logout()
        log.info(NAME, datetime_string() + ' ' + _('Logout OK.'))

    def select_folder(self, folder):
        """
        Select the IMAP folder to read messages from. By default
        the class will read from the INBOX folder
        """
        self.recipient_folder = folder

    def encoded_words_to_text(self, encoded_words):
        try:
            import re
            import base64, quopri

            encoded_word_regex = r'=\?{1}(.+)\?{1}([B|Q])\?{1}(.+)\?{1}='
            charset, encoding, encoded_text = re.match(encoded_word_regex, encoded_words).groups()
            if encoding == 'B':
                byte_string = base64.b64decode(encoded_text)
            elif encoding == 'Q':
                byte_string = quopri.decodestring(encoded_text)
            return byte_string.decode(charset)   

        except Exception:
            return encoded_words    

    def get_messages(self, sender, subject=''):
        """
        Scans for E-mail messages from the given sender and optionally
        with the given subject

        :param sender Email address of sender of messages yo're searching for
        :param subject (Partial) subject line to scan for
        :return List of dicts of {'num': num, 'body': body, 'subj': subj}
        """
        if not sender:
            log.error(NAME, datetime_string() + ' ' + _('You must provide a sender E-mail address!'))
            return

        # select the folder, by default INBOX
        resp, _ = self.imap.select(self.recipient_folder)
        if resp != 'OK':
            log.error(NAME, datetime_string() + ' ' + _('ERROR: Unable to open the folder') + ': ' + self.recipient_folder)
            return

        messages = []

        mbox_response, msgnums = self.imap.search(None, 'FROM', sender)
        if mbox_response == 'OK':
            for num in msgnums[0].split():
                retval, rawmsg = self.imap.fetch(num, '(RFC822)')

                if retval != 'OK':
                    log.error(NAME, datetime_string() + ' ' + _('ERROR: getting message') + ': ' +  num)
                    continue

                try:
                    msg = email.message_from_bytes(rawmsg[0][1])  # In Python3, we call message_from_bytes, but this function doesn't
                except AttributeError:
                    msg = email.message_from_string(rawmsg[0][1]) # exist in Python 2.

                msg_subject = msg["Subject"]
                if subject in msg_subject:
                    body = ""
                    subj = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            type = part.get_content_type()
                            disp = str(part.get('Content-Disposition'))
                            # look for plain text parts, but skip attachments
                            if type == 'text/plain' and 'attachment' not in disp:
                                charset = part.get_content_charset()
                                # decode the base64 unicode bytestring into plain text
                                body = part.get_payload(decode=True).decode(encoding=charset, errors="ignore")
                                # if we've found the plain/text part, stop looping thru the parts
                                break
                    else:
                        # not multipart - i.e. plain text, no attachments
                        charset = msg.get_content_charset()
                        body = msg.get_payload(decode=True).decode(encoding=charset, errors="ignore")
                                          
                    subj = self.encoded_words_to_text(msg_subject) # RAW to string

                    messages.append({'num': num, 'body': body, 'subj': subj})
        return messages

    def delete_message(self, msg_id):
        if not msg_id:
            return
        if self.move_to_trash:
            # move to Trash folder
            self.imap.store(msg_id, '+X-GM-LABELS', '\\Trash')
            self.imap.expunge()
            log.info(NAME, datetime_string() + ' ' + _('Message has moved to trash folder.'))
        else:
            self.imap.store(msg_id, '+FLAGS', '\\Deleted')
            self.imap.expunge()  
            log.info(NAME, datetime_string() + ' ' + _('Message has deleted.'))      