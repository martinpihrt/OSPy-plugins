# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import web


from blinker import signal ### for this example ###

from ospy.helpers import datetime_string, verify_csrf 
from ospy.log import log
from plugins import plugin_url
from ospy.webpages import ProtectedPage

NAME = 'Signaling Examples'
MENU =  _('Package: Signaling Examples')
LINK = 'settings_page'

SIGNAL_NAMES = [
    'loggedin',
    'value_change',
    'option_change',
    'rebooted',
    'restarted',
    'station_names',
    'program_change',
    'program_deleted',
    'program_toggled',
    'program_runnow',
    'zone_change',
    'rain_active',
    'rain_not_active',
    'master_one_on',
    'master_one_off',
    'master_two_on',
    'master_two_off',
    'pressurizer_master_relay_on',
    'pressurizer_master_relay_off',
    'poweroff',
    'ospyupdate',
    'station_on',
    'station_off',
    'station_clear',
    'internet_available',
    'internet_not_available',
    'rain_delay_set',
    'rain_delay_remove',
    'hass_plugin_update',
    'core_30_sec_tick',
    'air_temp_humi_plugin_update',
]

SIGNAL_RECEIVERS = {}
connected_signals = set()
last_signal = ''

################################################################################
# Helper functions:                                                            #
################################################################################

### start ###
def start():
    for signal_name in SIGNAL_NAMES:
        signal(signal_name).connect(receiver_for(signal_name), weak=False)
        connected_signals.add(signal_name)
 
### stop ###
def stop():
    for signal_name in list(connected_signals):
        signal(signal_name).disconnect(receiver_for(signal_name))
        connected_signals.discard(signal_name)


def health():
    """Return signal receiver registration and latest activity."""
    details = {
        _('Registered signals'): '{}/{}'.format(
            len(connected_signals), len(SIGNAL_NAMES)
        ),
        _('Last signal'): last_signal or _('None'),
    }
    if len(connected_signals) != len(SIGNAL_NAMES):
        return {
            'status': 'error',
            'summary': _('Signal receivers are not fully registered.'),
            'details': details,
        }
    return {
        'status': 'ok',
        'summary': _('Signal receivers are registered.'),
        'details': details,
    }


def signal_message(signal_name, kw):
    messages = {
        'loggedin': _('Someone logged in'),
        'value_change': _('Value_change'),
        'option_change': _('Options settings changed'),
        'rebooted': _('System rebooted'),
        'restarted': _('System restarted'),
        'station_names': _('Station names changed'),
        'program_change': _('Programs changed'),
        'program_deleted': _('Program deleted'),
        'program_toggled': _('Program toggled on or off'),
        'program_runnow': _('Program runnow'),
        'zone_change': _('Zone change'),
        'rain_active': _('Rain active'),
        'rain_not_active': _('Rain not active'),
        'master_one_on': _('Master one on'),
        'master_one_off': _('Master one off'),
        'master_two_on': _('Master two on'),
        'master_two_off': _('Master two off'),
        'pressurizer_master_relay_on': _('Pressurizer plugin master relay on'),
        'pressurizer_master_relay_off': _('Pressurizer plugin master relay off'),
        'poweroff': _('Linux system now powering off'),
        'ospyupdate': _('OSPy system update available'),
        'station_clear': _('OSPy all stations OFF'),
        'internet_available': _('Internet is available (external IP)'),
        'internet_not_available': _('Internet is not available (external IP)'),
        'rain_delay_remove': _('Rain delay has now been removed'),
        'hass_plugin_update': _('Home Assistant update'),
        'core_30_sec_tick': _('Core tick interval 30 second'),
        'air_temp_humi_plugin_update': _('Air Temperature and Humidity Monitor update'),
    }
    if signal_name == 'station_on':
        return _('OSPy stations ON, index: {}').format(kw.get('txt', ''))
    if signal_name == 'station_off':
        return _('OSPy stations OFF, index: {}').format(kw.get('txt', ''))
    if signal_name == 'rain_delay_set':
        return _('Rain delay is now set a delay {} hours').format(kw.get('txt', ''))
    return messages.get(signal_name, _('Signal received'))


def record_signal(signal_name, name=None, **kw):
    global last_signal
    message = signal_message(signal_name, kw)
    text = "{}: signal('{}') - {}".format(datetime_string(), signal_name, message)
    last_signal = text
    log.info(NAME, text)


def receiver_for(signal_name):
    if signal_name not in SIGNAL_RECEIVERS:
        def receiver(name, **kw):
            record_signal(signal_name, name, **kw)
        SIGNAL_RECEIVERS[signal_name] = receiver
    return SIGNAL_RECEIVERS[signal_name]

### login ###
def notify_login(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Someone logged in'))
    
### System settings ###
def notify_value_change(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Value_change'))

### Option settings ###
def notify_option_change(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Options settings changed'))

### Reboot ###
def notify_rebooted(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('System rebooted'))

### Restarted ###
def notify_restarted(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('System restarted'))

### station names ###
def notify_station_names(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Station names changed'))

### program change ##
def notify_program_change(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Programs changed'))

### program deleted ###
def notify_program_deleted(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Program deleted'))

### program toggled ###
def notify_program_toggled(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Program toggled on or off'))

### program runnow ###
def notify_program_runnow(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Program runnow'))

### zone change ###
def notify_zone_change(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Zone change'))

### rain ###
def notify_rain_active(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Rain active'))

### not rain ###
def notify_rain_not_active(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Rain not active'))    

### master 1 on ###
def notify_master_one_on(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Master one on'))    

### master 1 off ###
def notify_master_one_off(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Master one off'))    

### master 2 on ###
def notify_master_two_on(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Master two on'))    

### master 2 off ###
def notify_master_two_off(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Master two off'))  

### pressurizer plugin master relay on ###
def notify_pressurizer_master_relay_on(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Pressurizer plugin master relay on')) 

### pressurizer plugin master relay off ###
def notify_pressurizer_master_relay_off(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Pressurizer plugin master relay off')) 

### Linux system power off ###
def notify_poweroff(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Linux system now powering off')) 

### OSPy system update available ###
def notify_ospyupdate(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('OSPy system update available'))

### Stations ON ###
def notify_station_on(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('OSPy stations ON, index: {}').format(kw[u"txt"]))
    #print(u"Messge from {}!: {}".format(name, kw[u"txt"]))

### Stations OFF ###
def notify_station_off(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('OSPy stations OFF, index: {}').format(kw[u"txt"]))
    #print(u"Messge from {}!: {}".format(name, kw[u"txt"]))

### All stations set to OFF ###
def notify_station_clear(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('OSPy all stations OFF'))

### Internet available ###
def notify_internet_available(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Internet is available (external IP)'))

### Internet not available ###
def notify_internet_not_available(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Internet is not available (external IP)'))

### Rain delay has setuped ###
def notify_rain_delay_setuped(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Rain delay is now set a delay {} hours').format(kw[u"txt"]))

### Rain delay has expired ###
def notify_rain_delay_expired(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Rain delay has now been removed'))

### HASS plugin update ###
def notify_hass_update(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Home Assistant update'))

### OSPy core tick in loop 30 second ###
def notify_core_30_sec_tick(name, **kw):
    log.clear(NAME)
    log.info(NAME, datetime_string() + ': ' + _('Core tick interval 30 second'))

### Airtemp humi plugin update ###
def notify_air_temp_humi_plugin_update(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Air Temperature and Humidity Monitor update'))

################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        return self.plugin_render.signaling_examples(SIGNAL_NAMES)

    def POST(self):
        verify_csrf()
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.signaling_examples_help(SIGNAL_NAMES)


class settings_json(ProtectedPage):            ### return plugin_options as JSON data ###
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps({'signals': SIGNAL_NAMES})


class signal_json(ProtectedPage):
    """Returns log info state in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data = {}
        data['loginfo'] = log.events(NAME)
        data['last_signal'] = last_signal
        return json.dumps(data)

