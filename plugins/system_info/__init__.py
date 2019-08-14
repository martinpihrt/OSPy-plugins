#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# this plugins print system info os on web 

import platform
from collections import OrderedDict

import traceback
from ospy import helpers
from ospy.webpages import ProtectedPage
from ospy.options import options
import subprocess
from ospy.log import log

import sys
reload(sys)
sys.setdefaultencoding('utf8')

import i18n

NAME = 'System Information'
LINK = 'status_page'


################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    pass


stop = start

def get_overview():
    """Returns the info data as a list of lines."""
    result = []
    try:
        meminfo = helpers.get_meminfo()
        netdevs = helpers.get_netdevs()

        result.append(_('System release') + ': ' + platform.release())
        result.append(_('System name') + ': ' + platform.system())
        result.append(_('Node') + ': ' + platform.node())
        result.append(_('Machine') + ': ' + platform.machine())
        result.append(_('Distribution') + ': ' + (platform.linux_distribution()[0]) + ' ' + (platform.linux_distribution()[1]))
        result.append(_('Total memory') + ': ' + meminfo['MemTotal'])
        result.append(_('Free memory') + ': ' + meminfo['MemFree'])
        result.append(_('Python') + ': ' + platform.python_version())
        if netdevs:
            for dev, info in netdevs.iteritems():
                result.append('%-16s %s MiB %s MiB' % (dev + ': ', info['rx'], info['tx']))
        else:
            result.append(_('Network: Unknown'))
        result.append(_('Uptime') + ': ' + helpers.uptime())
        result.append(_('CPU temp') + ': ' + helpers.get_cpu_temp(options.temp_unit) + ' ' + options.temp_unit)
        result.append(_('CPU usage') + ': ' + str(helpers.get_cpu_usage()) + ' %')
        result.append(_('MAC adress') + ': ' + helpers.get_mac())
        try:
            result.append(_('I2C HEX Adress') + ': ')
            rev = str(0 if helpers.get_rpi_revision() == 1 else 1)
            cmd = 'sudo i2cdetect -y ' + rev
            result.append(process(cmd))
        except Exception:
            result.append(_('System info plug-in') + ':\n' + traceback.format_exc())

        # I2C test for Air Temperature and Humidity Monitor plugin
        if find_address(0x03):
            result.append(_('Found ATMEGA328 for Air Temperature and Humidity Monitor plugin (0x03).'))

        # I2C test for Water Tank Monitor plugin
        if find_address(0x04):
            result.append(_('Found ATMEGA328 for Water Tank Monitor plugin (0x04).'))

        # I2C test for Humidity Monitor plugin
        if find_address(0x05):
            result.append(_('Found ATMEGA328 for Humidity Monitor plugin (0x05).'))

        # I2C test for Button Control plugin
        if find_address(0x27):
            result.append(_('Found MCP23017 for Button Control plugin (0x27).'))

        # I2C test for LCD Display plugin
        search_range = {addr: 'PCF8574' for addr in range(32, 40)}
        search_range.update({addr: 'PCF8574A' for addr in range(56, 63)})    
        if find_address(search_range, range=True):
            if find_address(0x27):
                result.append(_('Warning: MCP23017 found for Button Control plugin (0x27). The address for PCF8574 must be different, not 0x27! If it is the same, change it on the LCD display board.'))
            result.append(_('Found PCF8574 for LCD Display plugin (0x20-0x28, 0x38-0x3F).'))

        # I2C test for Wind Speed Monitor/ Water Meter meter plugin
        search_range = {addr: 'PCF8583' for addr in range(80, 81)}
        if find_address(search_range, range=True):
            result.append(_('Found PCF8583 for Wind Speed Monitor or Water Meter plugin (0x50-0x51).'))

        # I2C test for Real Time and NTP time plugin
        if find_address(0x68):
            result.append(_('Found DS1307 for Real Time and NTP time plugin (0x68).'))
        

    except Exception:
        result.append(_('System info plug-in') + ':\n' + traceback.format_exc())

    return result


def find_address(search_range, range=False):
    try:
        import smbus
        bus = smbus.SMBus(0 if helpers.get_rpi_revision() == 1 else 1)
    except ImportError:
        log.warning(NAME, _('Could not import smbus.'))
    else:
        if range:
           for addr, type in search_range.iteritems():
               try:
                   bus.read_byte(addr) 
                   return True
                   break
               except Exception:
                   pass
               else:
                   return False
        else:
           try:
               bus.read_byte(search_range) 
               return True
           except Exception:
               pass
           else:
               return False


def process(cmd):
    """process in system"""
    proc = subprocess.Popen(
        cmd,
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        shell=True)
    output = proc.communicate()[0]
    return output
################################################################################
# Web pages:                                                                   #
################################################################################
class status_page(ProtectedPage):
    """Load an html page"""

    def GET(self):
        return self.plugin_render.system_info(get_overview())
