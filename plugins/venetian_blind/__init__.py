# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'

import json
import time
import traceback
import web
import subprocess
import os
import mimetypes

from ospy.options import options
from ospy.helpers import datetime_string
from ospy import helpers 
from ospy.log import log
from threading import Thread, Event
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer

from urllib.request import urlopen
from urllib.parse import quote_plus
from urllib.parse import urlparse

NAME = 'Venetian blind'      ### name for plugin in plugin manager ###
MENU =  _(u'Package: Venetian blind')
LINK = 'home_page'           ### link for page in plugin manager ###

plugin_options = PluginOptions(
    NAME,
    {
        'use_control': False,
        'use_log': False, 
        'number_blinds': 1,
        'use_footer': True,
        'label':  [_('Living room')],
        'open':   ["http://192.168.88.213/roller/0?go=open"],
        'stop':   ["http://192.168.88.213/roller/0?go=stop"],
        'close':  ["http://192.168.88.213/roller/0?go=close"],
        'status': ["http://192.168.88.213/status"],
        'label0':   [_('Closed blind')],
        'label100': [_('Open blind')],
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

        self.status = {}
        self.status['bstatus'] = {}

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
        last_msg = ''
        act_msg = ''
        ven_blind = None
        
        if plugin_options['use_footer']:
            ven_blind = showInFooter()                        #  instantiate class to enable data in footer
            ven_blind.button = "venetian_blind/home"          # button redirect on footer
            ven_blind.label =  _(u'Venetian blind')           # label on footer
        
        while not self._stop_event.is_set():
            try:
                if plugin_options['use_control']:             # if plugin is enabled
                    show_msg = read_blinds_status()
                    if plugin_options['use_footer']:          # if footer is enabled
                        if ven_blind is not None:
                            ven_blind.val = show_msg.encode('utf8').decode('utf8')       # value on footer                    
                else:
                    act_msg = _('Venetian blind is disabled.')
                    if act_msg != last_msg:
                        log.clear(NAME)
                        log.info(NAME, act_msg)
                        last_msg = act_msg
                        if plugin_options['use_footer']:
                            if ven_blind is not None:
                                ven_blind.val = act_msg.encode('utf8').decode('utf8')    # value on footer                            
                
                self._sleep(2)

            except Exception:
                log.error(NAME, _('Venetian blind plug-in') + ':\n' + traceback.format_exc())
                pass

sender = None

################################################################################
# Helper functions:                                                            #
################################################################################

### start ###
def start():
    global sender
    if sender is None:
        sender = Sender()
 
### stop ###
def stop():
    global sender
    if sender is not None:
        sender.stop()
        sender.join()
        sender = None

def uri_validator(x):
    try:
        result = urlparse(x)
        return all([result.scheme, result.netloc])
    except:
        return False

def send_cmd_to_blind(button, position):
    """Send command via REST API to blinds."""
    try:
        url = None
        if position == -1:
            url = plugin_options['close'][button]
            pos_msg =  _('close')
        elif position == 0:
            url = plugin_options['stop'][button]
            pos_msg =  _('stop')
        elif position == 1:
            url = plugin_options['open'][button]
            pos_msg =  _('open')
        else:
            url = None
            pos_msg =  _('unkown state')
        if url is not None:
            if uri_validator(url):
                try:
                    data = urlopen(url)
                    data = json.loads(data.read().decode(data.info().get_content_charset('utf-8')))
                    msg_log = '{}: {}'.format(_('Answer ok'), data)
                    update_log(pos_msg, msg_log)
                    return _('The command has been executed.')
                except OSError:
                    pass
                    update_log(pos_msg, _('No route to host {}.').format(url))
                    log.debug(NAME, _('No route to host {}.').format(url))
                    return _('No route to host {}.').format(url) 
            else:
                log.error(NAME, _('URL {} is invalid.').format(url))
                update_log(pos_msg, _('URL {} is invalid.').format(url))
                return _('URL {} is invalid.').format(url)
    except:
        pass
        log.error(NAME, _('Venetian blind plug-in') + ':\n' + traceback.format_exc())
        return _('Any error.')

def read_blinds_status():
    """Read status json data from blinds via REST API."""
    global sender
    footer_msg = ''
    try:
        from datetime import datetime
        today =  datetime.today()
        footer_msg += '{} '.format(today.strftime("%H:%M:%S"))

        for i in range(0, plugin_options['number_blinds']):
            if plugin_options['status'][i] != '':
                if uri_validator(plugin_options['status'][i]):
                    try:
                        url = plugin_options['status'][i]
                        data = urlopen(url)
                        data = json.loads(data.read().decode(data.info().get_content_charset('utf-8')))
                        if len(data) > 0:
                            # eg: data [{'state': 'stop', 'source': 'input', 'power': 0.0, 'is_valid': True, 'safety_switch': False, 'overtemperature': False, 'stop_reason': 'normal', 'last_direction': 'close', 'current_pos': 0, 'calibrating': False, 'positioning': True}]
                            rol_state = data['rollers'][0]['state']
                            rol_current_pos = data['rollers'][0]['current_pos']
                            rol_positioning = data['rollers'][0]['positioning']
                            rol_power = data['rollers'][0]['power']
                            if rol_state == 'open':
                                rol_msg = _('opening')
                            elif rol_state == 'stop':
                                rol_msg = _('stopped')
                            elif rol_state == 'close':
                                rol_msg = _('closing')
                            else:
                                rol_msg = _('unkown state')
                            if rol_positioning:
                                if rol_current_pos == 0:
                                    rol_pos_msg = '{}'.format(plugin_options['label0'][i])
                                elif rol_current_pos == 100:
                                    rol_pos_msg = '{}'.format(plugin_options['label100'][i])
                                else:
                                    rol_pos_msg = _('position')
                                    rol_pos_msg += ': {}%'.format(rol_current_pos)    
                                #sender.status['bstatus'][int(i)] = _('{} ({}, power {}W)').format(rol_msg, rol_pos_msg, rol_power)
                                sender.status['bstatus'][int(i)] = _('{} ({})').format(rol_msg, rol_pos_msg)
                                footer_msg += '{}: {} '.format(plugin_options['label'][i], sender.status['bstatus'][int(i)])
                            else:
                                rol_pos_msg = ''
                                footer_msg += '{}: {} '.format(plugin_options['label'][i], sender.status['bstatus'][int(i)])
                    except OSError:
                        url = plugin_options['status'][i]
                        log.debug(NAME, _('No route to host {}.').format(url))
                        sender.status['bstatus'][int(i)] = '{}'.format(_('No route to host.'))
                        footer_msg += '{}: {} '.format(plugin_options['label'][i], sender.status['bstatus'][int(i)])
                        pass
                else:
                    url = plugin_options['status'][i]
                    log.error(NAME, _('URL {} is invalid.').format(url))
                    sender.status['bstatus'][int(i)] = '{} {}'.format(datetime_string(), _('URL invalid.'))
                    footer_msg += '{}: {} '.format(plugin_options['label'][i], sender.status['bstatus'][int(i)])
            else:
                sender.status['bstatus'][int(i)] = '{} {}'.format(datetime_string(), _('URL is not setuped.'))
                footer_msg += '{}: {} '.format(plugin_options['label'][i], sender.status['bstatus'][int(i)])
        
        return footer_msg

    except Exception:
        log.error(NAME, _('Venetian blind plug-in') + ':\n' + traceback.format_exc())
        pass
        return _('Any error.')

def read_log():
    """Read log data from json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'log.json')) as logf:
            return json.load(logf)
    except IOError:
        return []

def write_log(json_data):
    """Write data to log json file."""
    with open(os.path.join(plugin_data_dir(), 'log.json'), 'w') as outfile:
        json.dump(json_data, outfile)

def update_log(cmd, status):
    """Update data in json files."""
    try:
        log_data = read_log()
    except:   
        write_log([])
        log_data = read_log()

    from datetime import datetime 

    data = {}
    data['cmd'] = cmd
    data['status'] = status
    data['datetime'] = datetime_string()

    log_data.insert(0, data)
    write_log(log_data)
    log.info(NAME, _('Saving to log files OK'))

################################################################################
# Web pages:                                                                   #
################################################################################

class home_page(ProtectedPage):
    """Load an html page for entering control."""

    def GET(self):
        global sender
        qdict = web.input()
        position = None
        button = helpers.get_input(qdict, 'btn', False, lambda x: True)
        if sender is not None and button:
            if 'pos' in qdict:
                position = int(qdict['pos'])
                button = int(qdict['btn'])
                if position is not None and position == -1:
                    pos_msg =  _('close')
                elif position is not None and position == 0:
                    pos_msg =  _('stop')
                elif position is not None and position == 1:
                    pos_msg =  _('open')
                else:
                    pos_msg = _('unkown state')
                log.info(NAME, _('Button for blind {}, position {}.').format(button+1, pos_msg))
                send_cmd_to_blind(button, position)        

        return self.plugin_render.venetian_blind(plugin_options)

    def POST(self):
        raise web.seeother(plugin_url(home_page), True)

class setup_page(ProtectedPage):
    """Load an html setup page."""

    def GET(self):
        global sender
        qdict = web.input()
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)
        test = helpers.get_input(qdict, 'test', False, lambda x: True)
        msg = 'none'
        position = None
        test_btn = None
        if sender is not None and delete:
            write_log([])
            log.info(NAME, _('Deleted all log files OK.'))
            raise web.seeother(plugin_url(setup_page), True)
        
        if sender is not None and test:
            if 'pos' in qdict:
                position = int(qdict['pos'])
            test_btn = int(qdict['test'])
            if position is not None and position == -1:
                pos_msg =  _('close')
            elif position is not None and position == 0:
                pos_msg =  _('stop')
            elif position is not None and position == 1:
                pos_msg =  _('open')
            else:
                pos_msg = _('unkown state.')    
            log.info(NAME, _('Test for blind {}, position {}.').format(test_btn+1, pos_msg))
            msg = send_cmd_to_blind(test_btn, position)
            #raise web.seeother(plugin_url(setup_page), True)
            return self.plugin_render.venetian_blind_setup(plugin_options, msg)

        return self.plugin_render.venetian_blind_setup(plugin_options, msg)

    def POST(self):
        try:
            qdict = web.input()

            if 'use_control' in qdict:
                if qdict['use_control']=='on':
                    plugin_options.__setitem__('use_control', True)
            else:  
                plugin_options.__setitem__('use_control', False)

            if 'use_log' in qdict:
                if qdict['use_log']=='on':
                    plugin_options.__setitem__('use_log', True)
            else:
                plugin_options.__setitem__('use_log', False)

            if 'use_footer' in qdict:
                if qdict['use_footer']=='on':
                    plugin_options.__setitem__('use_footer', True)
            else:
                plugin_options.__setitem__('use_footer', False)

            if 'number_blinds' in qdict:
                plugin_options.__setitem__('number_blinds', int(qdict['number_blinds']))

            commands = {'open': [], 'stop': [], 'close': [], 'label': [], 'status': [], 'label0': [], 'label100': []}

            for i in range(0, plugin_options['number_blinds']):
                commands['open'].append(qdict['open'+str(i)] if qdict['open'+str(i)] else '')
                commands['stop'].append(qdict['stop'+str(i)] if qdict['stop'+str(i)] else '')
                commands['close'].append(qdict['close'+str(i)] if qdict['close'+str(i)] else '')
                commands['label'].append(qdict['label'+str(i)] if qdict['label'+str(i)] else '')
                commands['status'].append(qdict['status'+str(i)] if qdict['status'+str(i)] else '')
                commands['label0'].append(qdict['label0'+str(i)] if qdict['label0'+str(i)] else '')
                commands['label100'].append(qdict['label100'+str(i)] if qdict['label100'+str(i)] else '')

            plugin_options.__setitem__('open', commands['open'])
            plugin_options.__setitem__('stop', commands['stop'])
            plugin_options.__setitem__('close', commands['close'])
            plugin_options.__setitem__('label', commands['label'])
            plugin_options.__setitem__('status', commands['status'])
            plugin_options.__setitem__('label0', commands['label0'])
            plugin_options.__setitem__('label100', commands['label100'])

            if sender is not None:
                sender.update()

        except Exception:
            log.debug(NAME, _('Venetian blind plug-in') + ':\n' + traceback.format_exc())
            pass

        msg = 'saved'
        return self.plugin_render.venetian_blind_setup(plugin_options, msg)

class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.venetian_blind_help()

class log_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.venetian_blind_log(read_log())

class settings_json(ProtectedPage): 
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)

class log_json(ProtectedPage):
    """Returns data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(read_log())

class log_csv(ProtectedPage):
    """Simple Log API"""

    def GET(self):
        data = "Date/Time; Command; State \n"
        log_file = read_log()
        for interval in log_file:
            data += '; '.join([
                interval['datetime'],
                u'{}'.format(interval['cmd']),
                u'{}'.format(interval['status']),
            ]) + '\n'

        content = mimetypes.guess_type(os.path.join(plugin_data_dir(), 'log.json')[0])
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-type', content) 
        web.header('Content-Disposition', 'attachment; filename="log.csv"')
        return data

class blind_status_json(ProtectedPage):
    """Returns status in JSON format."""

    def GET(self):
        global sender
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data=[]
        for i in range(0, plugin_options['number_blinds']):
            try:
                data.append(sender.status['bstatus'][i])
            except:
                data.append(_('unkown state'))
                pass    
        return json.dumps(data)        
