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
MENU =  _(u'Package: E-mail Reader')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {  'use_reader': False,
       'recipient' : u'...@gmail.com',
       'user_password' : u'',
       'server' : u'imap.gmail.com',
       'use_ssl': True,
       'move_to_trash': True,
       'recipient_folder': u'INBOX',
       'sender': u'xx@yy.zz',
       'check_int': 30,
       'scheduler_on': _(u'scheduler_on'),
       'scheduler_off': _(u'scheduler_off'),
       'manual_on': _(u'manual_on'),
       'manual_off': _(u'manual_off'),
       'stop_run': _(u'stop_run'),
       'send_help': _(u'send_help'),
       'send_state': _(u'send_state'), 
       'use_reply': True, 
       'eml_subject':  _(u'Report from OSPy E-mail Reader plugin'),
       'eml_subject_in': u'ospy_1',
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
       'pc0': _(u'Reboot OS system'),
       'pc1': _(u'Run program 1'),
       'pc2': _(u'Run program 2'),
       'pc3': _(u'Run program 3'),
       'pc4': _(u'Run program 4'),
       'pc5': _(u'Run program 5'),
       'pc6': _(u'Run program 6'),
       'pc7': _(u'Run program 7'),
       'pc8': _(u'Run program 8'),                                                      
       'pc9': _(u'Shutdown OS system')
    }
)

################################################################################
# Main function loop:                                                          #
################################################################################

class Sender(Thread):
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
        last_email_millis = 0    # timer for reading E-mails (ms)
        
        while not self._stop.is_set():
            try:
                msgem = ''
                msglog = ''
                if plugin_options['use_reader']: 
                    email_interval = plugin_options['check_int']*1000   # time for reading E-mails (ms) -> 1 minute = 1000ms*60s -> 60000ms
                    millis = int(round(time.time() * 1000))             # actual time in ms
                    if(millis - last_email_millis) >= email_interval:   # is time for reading?
                        last_email_millis = millis
                        log.clear(NAME)
                        imap = ImapClient(recipient=plugin_options['recipient'], user_password=plugin_options['user_password'], server=plugin_options['server'],\
                            use_ssl=plugin_options['use_ssl'], move_to_trash=plugin_options['move_to_trash'], recipient_folder=plugin_options['recipient_folder'])
                        log.info(NAME, datetime_string() + ' ' + _(u'Try-ing login to E-mail.'))
                        is_login_ok = imap.login()     
                        if is_login_ok:
                            messages = imap.get_messages(sender=plugin_options['sender']) # retrieve messages from a given sender
                            log.info(NAME, datetime_string() + ' ' + _(u'Reading messages in inbox.'))   
                            # Do something with the messages                 
                            for msg in messages:               # msg is a dict of {'num': num, 'body': body, 'subj': subj} 
                                cm = u'%s' % msg['body']
                                cmd = cm.replace('\r\n', '')   # remove \r\n from {'body': u'scheduler_on\r\n'}
                                subj = msg['subj']

                                log.info(NAME, _(u'Message: %s') % cmd)      
                                log.info(NAME, _(u'Subject: %s') % subj)      

                                if  cmd == plugin_options['scheduler_on'] and subj == plugin_options['eml_subject_in']:  # msg for switch scheduler to on
                                    options.scheduler_enabled = True
                                    log.info(NAME, datetime_string() + ' ' + _(u'Scheduler has switched to enabled.'))
                                    msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                    msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + ' ' + _(u'Scheduler has switched to enabled.') + '</p>'
                                    msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd

                                elif cmd == plugin_options['scheduler_off'] and subj == plugin_options['eml_subject_in']: # msg for switch scheduler to off 
                                    options.scheduler_enabled = False
                                    log.info(NAME, datetime_string() + ' ' + _(u'Scheduler has switched to disabled.'))
                                    msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                    msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + ' ' + _(u'Scheduler has switched to disabled.') + '</p>'
                                    msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd                                    

                                elif cmd == plugin_options['manual_on'] and subj == plugin_options['eml_subject_in']:     # msg for switch to manual   
                                    options.manual_mode = True
                                    log.info(NAME, datetime_string() + ' ' + _(u'OSPy has switched to manual control.')) 
                                    msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                    msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + ' ' + _(u'OSPy has switched to manual control.') + '</p>'
                                    msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd                                      

                                elif cmd == plugin_options['manual_off'] and subj == plugin_options['eml_subject_in']:    # msg for switch to scheduler   
                                    options.manual_mode = False
                                    log.info(NAME, datetime_string() + ' ' + _(u'OSPy has switched to scheduler controler.')) 
                                    msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                    msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + ' ' + _(u'OSPy has switched to scheduler controler.') + '</p>'
                                    msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd                                     

                                elif cmd == plugin_options['stop_run'] and subj == plugin_options['eml_subject_in']:      # msg for stop all run stations   
                                    programs.run_now_program = None
                                    run_once.clear()
                                    log.finish_run(None)
                                    stations.clear()
                                    log.info(NAME, datetime_string() + ' ' + _(u'OSPy has stop all running stations.')) 
                                    msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                    msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + ' ' + _(u'OSPy has stop all running stations.') + '</p>'
                                    msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd                                     

                                elif cmd == plugin_options['send_help'] and subj == plugin_options['eml_subject_in']:     # msg for sending back help via email   
                                    log.info(NAME, datetime_string() + ' ' + _(u'OSPy sends the set commands to the administrator by E-mail.'))  
                                    msgem += '<style>tr:nth-child(even) {background-color: #f2f2f2;} </style>'
                                    msgem += '<div style="overflow-x:auto;">' 
                                    msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                    msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + '</p><p><b>' + _(u'All available commands in plugin') + ':</p>'
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
                                    for i in range(10):
                                        msgem += '<tr><td>' + _('Selecting command %d') % i + ':</td>'
                                        msgem += '<td>' + u'%s' % plugin_options["pc%d" % i] + '</td></tr>'
                                    msgem += '<tr><td>' + _('Sending message in body E-mail as list (use in manual mode)') + ':</td>'
                                    msgem += '<td>' + _('Station 1 -> OFF, 2 -> OFF, 3 -> ON 100 second, 4 -> ON 30 second...') + '</td>'
                                    msgem += '<td>' + _('[0,0,100,30,...]') + '</td></tr>' 
                                    msgem += '<tr><td>' + _('Sending message in body E-mail as dict (use in manual mode)') + ':</td>'
                                    msgem += '<td>' + _('Station 1 -> OFF, 2 -> OFF, 3 -> ON 100 second, 4 -> ON 30 second...') + '</td>'
                                    msgem += '<td>' + _('{"aa":0,"bb":0,"cc":100,"dd":30...}') + '</td></tr>'
                                    msgem += '</table></p></div>' 
                                    msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd    

                                elif cmd == plugin_options['send_state'] and subj == plugin_options['eml_subject_in']:     # msg for sending stations state via email  
                                    log.info(NAME, datetime_string() + ' ' + _(u'OSPy sends the stations state to the administrator E-mail.'))  
                                    msgem += '<style>tr:nth-child(even) {background-color: #f2f2f2;} </style>'
                                    msgem += '<div style="overflow-x:auto;">' 
                                    msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                    msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + '</p><p>' + _(u'Actual stations state') + ':</p>'
                                    msgem += '<p>' + '<table style="text-align: left; cellspacing="0"; cellpadding="6"; border="1";>'
                                    msgem += '<tr><td><b>' + _(u'Station name') + '</b></td><td><b>' + _(u'State') + '</b></td><td><b>' + _(u'Main 1') + '</b></td><td><b>' + _(u'Main 2')
                                    msgem += '</b></td><td><b>' + _(u'Remaining time in sec') + '</b></td></tr>'
                                    for station in stations.get():
                                        msgem += '<tr><td>' + u'%s' % station.name + '</td>'
                                        if station.active:
                                            msgem += '<td>' + _(u'ON') + '</td>'
                                        else:
                                            msgem += '<td>' + _(u'OFF') + '</td>'
                                        if station.is_master:
                                            msgem += '<td>' + _(u'YES') + '</td>'
                                        else:
                                            msgem += '<td>' + _(u'-') + '</td>'    
                                        if station.is_master_two:    
                                            msgem += '<td>' + _(u'YES') + '</td>' 
                                        else:
                                            msgem += '<td>' + _(u'-') + '</td>'
                                        if(station.remaining_seconds == -1):
                                            msgem += '<td>' + _(u'Forever') + '</td>' 
                                        else:    
                                            msgem += '<td>' + _(u'%s') % str(int(station.remaining_seconds)) + '</td>'
    
                                    msgem += '</tr></table></p></div>' 
                                    msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd   

                                elif cmd == plugin_options['p0'] or cmd == plugin_options['p1'] or cmd == plugin_options['p2'] or cmd == plugin_options['p3'] or cmd == plugin_options['p4'] or cmd == plugin_options['p5'] or cmd ==plugin_options['p6'] or cmd ==plugin_options['p7'] or cmd ==plugin_options['p8'] or cmd ==plugin_options['p9']:                                      
                                    for i in range(10): 
                                        if cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "reboot" and subj == plugin_options['eml_subject_in']: # msg for reboot via email
                                            log.info(NAME, datetime_string() + ': ' + _(u'System Linux has now reboot!'))                                             
                                            msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                            msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _(u'System Linux has now reboot!') + '</p>'
                                            msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd
                                            stations.clear()
                                            reboot(wait=10) # after 10 seconds
                                            break
                                                 
                                        elif cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "pwrOff" and subj == plugin_options['eml_subject_in']: # msg for shuttdown via email
                                            log.info(NAME, datetime_string() + ': ' + _(u'System Linux has now shutdown!'))
                                            msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                            msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _(u'System Linux has now shutdown!') + '</p>'
                                            msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd                                            
                                            stations.clear()
                                            poweroff(wait=10) # after 10 seconds
                                            break

                                        elif cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "runP1" and subj == plugin_options['eml_subject_in']: # msg for run program 1 via email
                                            log.info(NAME, datetime_string() + ' ' + _(u'OSPy has switched to scheduler controler.') + ' ' + _(u'Run now program 1.')) 
                                            msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                            msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _(u'Run now program 1.') + ' ' + _(u'OSPy has switched to scheduler controler.') + '</p>'
                                            msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd                                             
                                            for program in programs.get():
                                                if (program.index == 0):   # Run-now program 1
                                                    options.manual_mode = False   
                                                    log.finish_run(None)
                                                    stations.clear()    
                                                    programs.run_now(program.index)
                                                    break       
                                                program.index+1

                                        elif cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "runP2" and subj == plugin_options['eml_subject_in']: # msg for run program 2 via email
                                            log.info(NAME, datetime_string() + ' ' + _(u'OSPy has switched to scheduler controler.') + ' ' + _(u'Run now program 2.')) 
                                            msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                            msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _(u'Run now program 2.') + ' ' + _(u'OSPy has switched to scheduler controler.') + '</p>'
                                            msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd                                             
                                            for program in programs.get():
                                                if (program.index == 1):   # Run-now program 2
                                                    options.manual_mode = False   
                                                    log.finish_run(None)
                                                    stations.clear()    
                                                    programs.run_now(program.index) 
                                                    break      
                                                program.index+1 

                                        elif cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "runP3" and subj == plugin_options['eml_subject_in']: # msg for run program 3 via email
                                            log.info(NAME, datetime_string() + ' ' + _(u'OSPy has switched to scheduler controler.') + ' ' + _(u'Run now program 3.')) 
                                            msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                            msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _(u'Run now program 3.') + ' ' + _(u'OSPy has switched to scheduler controler.') + '</p>'
                                            msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd                                             
                                            for program in programs.get():
                                                if (program.index == 2):   # Run-now program 3
                                                    options.manual_mode = False   
                                                    log.finish_run(None)
                                                    stations.clear()    
                                                    programs.run_now(program.index) 
                                                    break      
                                                program.index+1       

                                        elif cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "runP4" and subj == plugin_options['eml_subject_in']: # msg for run program 4 via email
                                            log.info(NAME, datetime_string() + ' ' + _(u'OSPy has switched to scheduler controler.') + ' ' + _(u'Run now program 4.')) 
                                            msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                            msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _(u'Run now program 4.') + ' ' + _(u'OSPy has switched to scheduler controler.') + '</p>'
                                            msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd                                             
                                            for program in programs.get():
                                                if (program.index == 3):   # Run-now program 4
                                                    options.manual_mode = False   
                                                    log.finish_run(None)
                                                    stations.clear()    
                                                    programs.run_now(program.index) 
                                                    break      
                                                program.index+1                                                                                                                                                    

                                        elif cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "runP5" and subj == plugin_options['eml_subject_in']: # msg for run program 5 via email
                                            log.info(NAME, datetime_string() + ' ' + _(u'OSPy has switched to scheduler controler.') + ' ' + _(u'Run now program 5.')) 
                                            msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                            msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _(u'Run now program 5.') + ' ' + _(u'OSPy has switched to scheduler controler.') + '</p>'
                                            msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd                                             
                                            for program in programs.get():
                                                if (program.index == 4):   # Run-now program 5
                                                    options.manual_mode = False   
                                                    log.finish_run(None)
                                                    stations.clear()    
                                                    programs.run_now(program.index)  
                                                    break     
                                                program.index+1    

                                        elif cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "runP6" and subj == plugin_options['eml_subject_in']: # msg for run program 6 via email
                                            log.info(NAME, datetime_string() + ' ' + _(u'OSPy has switched to scheduler controler.') + ' ' + _(u'Run now program 6.')) 
                                            msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                            msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _(u'Run now program 6.') + ' ' + _(u'OSPy has switched to scheduler controler.') + '</p>'
                                            msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd                                             
                                            for program in programs.get():
                                                if (program.index == 5):   # Run-now program 6
                                                    options.manual_mode = False   
                                                    log.finish_run(None)
                                                    stations.clear()    
                                                    programs.run_now(program.index) 
                                                    break      
                                                program.index+1     

                                        elif cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "runP7" and subj == plugin_options['eml_subject_in']: # msg for run program 7 via email
                                            log.info(NAME, datetime_string() + ' ' + _(u'OSPy has switched to scheduler controler.') + ' ' + _(u'Run now program 7.')) 
                                            msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                            msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _(u'Run now program 7.') + ' ' + _(u'OSPy has switched to scheduler controler.') + '</p>'
                                            msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd                                             
                                            for program in programs.get():
                                                if (program.index == 6):   # Run-now program 7
                                                    options.manual_mode = False   
                                                    log.finish_run(None)
                                                    stations.clear()    
                                                    programs.run_now(program.index)  
                                                    break     
                                                program.index+1    

                                        elif cmd == plugin_options['pc%d' % i] and plugin_options['p%d' % i] == "runP8" and subj == plugin_options['eml_subject_in']: # msg for run program 8 via email
                                            log.info(NAME, datetime_string() + ' ' + _(u'OSPy has switched to scheduler controler.') + ' ' + _(u'Run now program 8.')) 
                                            msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                            msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _(u'Run now program 8.') + ' ' + _(u'OSPy has switched to scheduler controler.') + '</p>'
                                            msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd                                             
                                            for program in programs.get():
                                                if (program.index == 7):   # Run-now program 8
                                                    options.manual_mode = False   
                                                    log.finish_run(None)
                                                    stations.clear()    
                                                    programs.run_now(program.index) 
                                                    break      
                                                program.index+1
                                        else:  
                                            log.info(NAME, _(u'Subject in message is') + (u': %s') % subj)
                                            log.info(NAME, _(u'Subject in options is') + (u': %s') % plugin_options['eml_subject_in'])  
                                            log.info(NAME, _(u'Command') + _(u': %s') % cmd) 
                                            log.info(NAME, _(u'The command has been not processed!'))
                                            msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _(u'The command has been not processed!') + '</p>'
                                            msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                            msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been not processed!') + ' ' + _(u'MSG: %s') % cmd 
                                            break
                                  
                                else:
                                    if not options.manual_mode:              # not manual mode -> no operations with stations
                                        log.error(NAME, datetime_string() + ' ' + _(u'OSPy must be first switched to manual mode!'))
                                        msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _(u'The command has been not processed!') + '</p>'
                                        msgem += '<p>' + datetime_string() + ' ' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                        msgem += '<p style="color:red;">' + _(u'OSPy must be first switched to manual mode!') + '</p>'
                                        msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been not processed!') + ' ' + _(u'MSG: %s') % cmd
                                    elif subj != plugin_options['eml_subject_in']:
                                        log.error(NAME, datetime_string() + ' ' + _(u'Subject is not correct!'))
                                        log.error(NAME, _(u'Subject in message is') + (u': %s') % subj)
                                        log.error(NAME, _(u'Subject in options is') + (u': %s') % plugin_options['eml_subject_in'])
                                        msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _(u'The command has been not processed!') + '</p>'
                                        msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                        msgem += '<p style="color:red;">' + _(u'Subject in message is') + (u': %s') % subj + '<br/>'
                                        msgem +=  _(u'Subject in options is') + (u': %s') % plugin_options['eml_subject_in'] + '</p>'                                        
                                        msgem += '<p>' + datetime_string() + ' ' + _(u'Subject is not correct!') + '</p>'
                                        msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been not processed!') + ' ' + _(u'MSG: %s') % cmd                                        
                                    else:                                    # yes is manual mode and subject is correct
                                        try:
                                            log.info(NAME, datetime_string() + ' ' + _(u'Try-ing to processing command.'))
                                            cmd = json.loads(msg['body'])
                                            num_sta = options.output_count
                                            if type(cmd) is list:            # cmd is list
                                                msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                                msgem += '<p>' + datetime_string() + ' ' + _(u'Command') + (u': %s') % cmd + '</p>'
                                                if len(cmd) < num_sta:
                                                    log.info(NAME, datetime_string() + ' ' + _(u'Not enough stations specified, assuming first {} of {}').format(len(cmd), num_sta))
                                                    rovals = cmd + ([0] * (num_sta - len(cmd)))              
                                                    msgem += '<p>' +  _(u'Not enough stations specified, assuming first {} of {}').format(len(cmd), num_sta) + '</p>'                                                    
                                                elif len(cmd) > num_sta:
                                                    log.info(NAME, datetime_string() + ' ' + _(u'Too many stations specified, truncating to {}').format(num_sta))
                                                    rovals = cmd[0:num_sta]
                                                    msgem += '<p>' + _(u'Too many stations specified, truncating to {}').format(num_sta) + '</p>'                                                    
                                                else:
                                                    rovals = cmd

                                            elif type(cmd) is dict:          # cmd is dictionary
                                                rovals = [0] * num_sta
                                                snames = station_names()     # Load station names from file
                                                jnames = json.loads(snames)  # Load as json
                                                msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b>'
                                                for k, v in list(cmd.items()):
                                                    if k not in snames:      # station name in dict is not in OSPy stations name (ERROR)
                                                        log.warning(NAME, _(u'No station named') + (u': %s') % k)
                                                        msgem += '<p style="color:red;>' + _(u'No station named') + (u': %s') % k + '</p>'
                                                    else:                    # station name in dict is in OSPy stations name (OK)
                                                        # v is value for time, k is station name in dict
                                                        rovals[jnames.index(k)] = v  

                                                msgem += '<p style="color:green;">' + _(u'The command has been processed.') + '</p>' 
                                                msgem += '<p>' +  _(u'MSG: %s') % cmd  + '<p>'         

                                            else:
                                                log.error(NAME, datetime_string() + ' ' + _(u'Unexpected command') + (u': %s') % cmd)
                                                msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _(u'The command has been not processed!') + '</p>'
                                                msgem += '<p>' + datetime_string() + ' ' + _(u'Unexpected command') + (u': %s') % cmd + '</p>'
                                                msgem += '<p style="color:red;">' + _(u'Subject in message is') + (u': %s') % subj + '<br/>'
                                                msgem +=  _(u'Subject in options is') + (u': %s') % plugin_options['eml_subject_in'] + '</p>'
                                                msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been not processed!') + ' ' + _(u'MSG: %s') % cmd                                                 
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
                                                        'program_name': _(u'E-mail Reader'),
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

                                                msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd

                                            else:
                                                msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _(u'The command has been not processed!') + '</p>'
                                                msgem += '<p>' + datetime_string() + ' ' + _(u'Unexpected command') + (u': %s') % cmd + '</p>'
                                                msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been not processed!') + ' ' + _(u'MSG: %s') % cmd     
                                                        
                                        except ValueError as e:
                                            log.error(NAME, datetime_string() + ' ' + _(u'Could not decode command') + u': %s' % e)
                                            msgem += '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _(u'The command has been not processed!') + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _(u'Could not decode command') + u': %s' % e + '</p>'
                                            msglog += _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been not processed!') + ' ' + _(u'MSG: %s') % cmd
                                            pass

                                if plugin_options['use_reply']:          # send reply to administrator
                                    log.info(NAME, datetime_string() + ' ' + _(u'Sending reply to administrator E-mail.'))
                                    try:
                                        from plugins.email_notifications import try_mail                                    
                                        try_mail(msgem, msglog, attachment=None, subject=plugin_options['eml_subject']) # try_mail(text, logtext, attachment=None, subject=None)
                                    except Exception:     
                                        log.error(NAME, _(u'E-mail Reader plug-in') + ':\n' + traceback.format_exc())      
                        
                                if plugin_options['move_to_trash']:      # you could delete them after viewing     
                                    imap.delete_message(msg['num'])
                                    self._sleep(1)
                        
                            imap.logout()                                # when done, you should log out
   
                self._sleep(1)  

            except Exception:
                log.clear(NAME)
                log.error(NAME, _(u'E-mail Reader plug-in') + ':\n' + traceback.format_exc())
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
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):

        return self.plugin_render.email_reader(plugin_options, log.events(NAME))


    def POST(self):
        plugin_options.web_update(web.input())

        if sender is not None:
            sender.update()

        log.info(NAME, _('Options has updated.'))
        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)


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
            log.error(NAME, datetime_string() + ' ' + _(u'You must provide a recipient E-mail address.'))
            return
        if not user_password:
            log.error(NAME, datetime_string() + ' ' + _(u'You must provide a recipient E-mail password.'))
            return  
        if not server:
            log.error(NAME, datetime_string() + ' ' + _(u'You must provide server.'))
            return    
        if not recipient_folder:
            log.error(NAME, datetime_string() + ' ' + _(u'You must provide recipient folder.'))
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
            log.info(NAME, datetime_string() + ' ' + _(u'Login OK.'))
            return True
        except:
            log.error(NAME, datetime_string() + ' ' + _(u'Mail account login details are not filled in correctly!'))
            return False

    def logout(self):
        self.imap.close()
        self.imap.logout()
        log.info(NAME, datetime_string() + ' ' + _(u'Logout OK.'))

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
            if encoding is 'B':
                byte_string = base64.b64decode(encoded_text)
            elif encoding is 'Q':
                byte_string = quopri.decodestring(encoded_text)
            return byte_string.decode(charset)   

        except Exception:
            return encoded_words    

    def get_messages(self, sender, subject=''):
        """
        Scans for E-mail messages from the given sender and optionally
        with the given subject

        :param sender Email address of sender of messages you're searching for
        :param subject (Partial) subject line to scan for
        :return List of dicts of {'num': num, 'body': body, 'subj': subj}
        """
        if not sender:
            log.error(NAME, datetime_string() + ' ' + _(u'You must provide a sender E-mail address!'))
            return

        # select the folder, by default INBOX
        resp, _ = self.imap.select(self.recipient_folder)
        if resp != 'OK':
            log.error(NAME, datetime_string() + ' ' + _(u'ERROR: Unable to open the folder') + ': ' + self.recipient_folder)
            return

        messages = []

        mbox_response, msgnums = self.imap.search(None, 'FROM', sender)
        if mbox_response == 'OK':
            for num in msgnums[0].split():
                retval, rawmsg = self.imap.fetch(num, '(RFC822)')

                if retval != 'OK':
                    log.error(NAME, datetime_string() + ' ' + _(u'ERROR: getting message') + ': ' +  num)
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
            log.info(NAME, datetime_string() + ' ' + _(u'Message has moved to trash folder.'))
        else:
            self.imap.store(msg_id, '+FLAGS', '\\Deleted')
            self.imap.expunge()  
            log.info(NAME, datetime_string() + ' ' + _(u'Message has deleted.'))      