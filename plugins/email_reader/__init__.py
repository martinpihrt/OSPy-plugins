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
from ospy.helpers import datetime_string
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
       'scheduler_on': u'scheduler_on',
       'scheduler_off': u'scheduler_off',
       'manual_on': u'manual_on',
       'manual_off': u'manual_off',
       'stop_run': u'stop_run',
       'send_help': u'send_help',
       'use_reply': True, 
       'eml_subject':  _(u'Report from OSPy E-mail Reader plugin')
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
                            for msg in messages:                             # msg is a dict of {'num': num, 'body': body} 
                                cm = u'%s' % msg['body']
                                cmd = cm.replace('\r\n', '')   # remove \r\n from {'body': u'scheduler_on\r\n'}

                                log.info(NAME, _(u'Message: %s') % cmd)      

                                if   cmd == plugin_options['scheduler_on']:  # msg for switch scheduler to on
                                    options.scheduler_enabled = True
                                    log.info(NAME, datetime_string() + ' ' + _(u'Scheduler has switched to enabled.'))
                                    msgem  = '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                    msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + ' ' + _(u'Scheduler has switched to enabled.') + '</p>'
                                    msglog = _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd

                                elif cmd == plugin_options['scheduler_off']: # msg for switch scheduler to off 
                                    options.scheduler_enabled = False
                                    log.info(NAME, datetime_string() + ' ' + _(u'Scheduler has switched to disabled.'))
                                    msgem  = '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                    msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + ' ' + _(u'Scheduler has switched to disabled.') + '</p>'
                                    msglog = _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd                                    

                                elif cmd == plugin_options['manual_on']:     # msg for switch to manual   
                                    options.manual_mode = True
                                    log.info(NAME, datetime_string() + ' ' + _(u'OSPy has switched to manual control.')) 
                                    msgem  = '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                    msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + ' ' + _(u'OSPy has switched to manual control.') + '</p>'
                                    msglog = _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd                                      

                                elif cmd == plugin_options['manual_off']:    # msg for switch to scheduler   
                                    options.manual_mode = False
                                    log.info(NAME, datetime_string() + ' ' + _(u'OSPy has switched to scheduler controler.')) 
                                    msgem  = '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                    msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + ' ' + _(u'OSPy has switched to scheduler controler.') + '</p>'
                                    msglog = _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd                                     

                                elif cmd == plugin_options['stop_run']:      # msg for stop all run stations   
                                    programs.run_now_program = None
                                    run_once.clear()
                                    log.finish_run(None)
                                    stations.clear()
                                    log.info(NAME, datetime_string() + ' ' + _(u'OSPy has stop all running stations.')) 
                                    msgem  = '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                    msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + ' ' + _(u'OSPy has stop all running stations.') + '</p>'
                                    msglog = _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd                                     

                                elif cmd == plugin_options['send_help']:     # msg for sending back help via email   
                                    log.info(NAME, datetime_string() + ' ' + _(u'OSPy sends the set commands to the administrator by E-mail.'))    
                                    msgem  = '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                    msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                    msgem += '<p>' + datetime_string() + '</p><p><b>' + _(u'All available commands in plugin') + ':</p>'
                                    msgem += '<p>' + '<table style="text-align: left; width: 100%;" border="0" cellpadding="2" cellspacing="2">'
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
                                    msgem += '<tr><td>' + _('Sending message in body E-mail as list (use in manual mode)') + ':</td>'
                                    msgem += '<td>' + _('Station 1 -> OFF, 2 -> OFF, 3 -> ON 100 second, 4 -> ON 30 second...') + '</td>'
                                    msgem += '<td>' + _('[0,0,100,30,...]') + '</td></tr>' 
                                    msgem += '<tr><td>' + _('Sending message in body E-mail as dict (use in manual mode)') + ':</td>'
                                    msgem += '<td>' + _('Station 1 -> OFF, 2 -> OFF, 3 -> ON 100 second, 4 -> ON 30 second...') + '</td>'
                                    msgem += '<td>' + _('{"aa":0,"bb":0,"cc":100,"dd":30...}') + '</td></tr>'
                                    msgem += '</table></p>' 
                                    msglog = _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd                                    

                                else:
                                    if not options.manual_mode:                      # not manual mode -> no operations with stations
                                        log.error(NAME, datetime_string() + ' ' + _(u'OSPy must be first switched to manual mode!'))
                                        msgem  = '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _(u'The command has been not processed!') + '</p>'
                                        msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                        msgem += '<p>' + datetime_string() + ' ' + _(u'OSPy must be first switched to manual mode!') + '</p>'
                                        msglog = _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been not processed!') + ' ' + _(u'MSG: %s') % cmd
                                    else:                                    # yes is manual mode
                                        try:
                                            log.debug(NAME, datetime_string() + ' ' + _(u'Try-ing to processing command.'))
                                            cmd = json.loads(msg['body'])
                                            num_sta = options.output_count
                                            if type(cmd) is list:            # cmd is list
                                                if len(cmd) < num_sta:
                                                    log.error(NAME, datetime_string() + ' ' + _(u'Not enough stations specified, assuming first {} of {}').format(len(cmd), num_sta))
                                                    rovals = cmd + ([0] * (num_sta - len(cmd)))
                                                    msgem  = '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _(u'The command has been not processed!') + '</p>'
                                                    msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                                    msgem += '<p>' + datetime_string() + ' ' + _(u'Not enough stations specified, assuming first {} of {}').format(len(cmd), num_sta) + '</p>'
                                                    msglog = _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been not processed!') + ' ' + _(u'MSG: %s') % cmd                                                    
                                                elif len(cmd) > num_sta:
                                                    log.error(NAME, datetime_string() + ' ' + _(u'Too many stations specified, truncating to {}').format(num_sta))
                                                    rovals = cmd[0:num_sta]
                                                    msgem  = '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _(u'The command has been not processed!') + '</p>'
                                                    msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                                    msgem += '<p>' + datetime_string() + ' ' + _(u'Too many stations specified, truncating to {}').format(num_sta) + '</p>'
                                                    msglog = _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been not processed!') + ' ' + _(u'MSG: %s') % cmd                                                     
                                                else:
                                                    rovals = cmd
                                            elif type(cmd) is dict:          # cmd is dictionary
                                                rovals = [0] * num_sta
                                                snames = station_names()     # Load station names from file
                                                for k, v in list(cmd.items()):
                                                    if k not in snames:
                                                        log.error(NAME, datetime_string() + ' ' + _(u'No station named') + (u': %s') % k)
                                                        msgem  = '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _(u'The command has been not processed!') + '</p>'
                                                        msgem += '<p>' + _(u'Command') + _(u': %s') % cmd + '</p>'
                                                        msgem += '<p>' + datetime_string() + ' ' + _(u'No station named') + (u': %s') % k + '</p>'
                                                        msglog = _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been not processed!') + ' ' + _(u'MSG: %s') % cmd  
                                                    else:
                                                        try:
                                                            rovals[snames.index(k)] = v
                                                        except IndexError as e:
                                                            pass
                                                            log.error(NAME, datetime_string() + ' ' + _(u'No station named') + (u': %s') % e)    

                                            else:
                                                log.error(NAME, datetime_string() + ' ' + _(u'Unexpected command') + (u': %s') % cmd)
                                                msgem  = '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _(u'The command has been not processed!') + '</p>'
                                                msgem += '<p>' + datetime_string() + ' ' + _(u'Unexpected command') + (u': %s') % cmd + '</p>'
                                                msglog = _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been not processed!') + ' ' + _(u'MSG: %s') % cmd                                                 
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

                                                msgem  = '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'The command has been processed.') + '</p>'
                                                msgem += '<p>' + datetime_string() + ' ' + _(u'Command') + (u': %s') % cmd + '</p>'
                                                msglog = _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been processed.') + ' ' + _(u'MSG: %s') % cmd

                                            else:
                                                msgem  = '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _(u'The command has been not processed!') + '</p>'
                                                msgem += '<p>' + datetime_string() + ' ' + _(u'Unexpected command') + (u': %s') % cmd + '</p>'
                                                msglog = _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been not processed!') + ' ' + _(u'MSG: %s') % cmd     
                                                        
                                        except ValueError as e:
                                            log.error(NAME, datetime_string() + ' ' + _(u'Could not decode command') + u': %s' % e)
                                            msgem  = '<b>' + _(u'E-mail Reader plug-in') + '</b> ' + '<br><p style="color:red;">' + _(u'The command has been not processed!') + '</p>'
                                            msgem += '<p>' + datetime_string() + ' ' + _(u'Could not decode command') + u': %s' % e + '</p>'
                                            msglog = _(u'E-mail Reader plug-in') + ': ' + _(u'The command has been not processed!') + ' ' + _(u'MSG: %s') % cmd
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
        station_list.append(u'%s' % station.name)

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

    def get_messages(self, sender, subject=''):
        """
        Scans for E-mail messages from the given sender and optionally
        with the given subject

        :param sender Email address of sender of messages you're searching for
        :param subject (Partial) subject line to scan for
        :return List of dicts of {'num': num, 'body': body}
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
                    messages.append({'num': num, 'body': body})
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