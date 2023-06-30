# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'
# this plugins print system info os on web 

import platform
from collections import OrderedDict

import traceback
from ospy import helpers
from ospy.webpages import ProtectedPage
from ospy.options import options
import subprocess
from ospy.log import log

import web


NAME = 'System Information'
MENU =  _(u'Package: System Information')
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

        result.append(_('System release') + ': {}'.format(platform.release()))
        result.append(_('System name') + ': {}'.format(platform.system()))
        result.append(_('Node') + ': {}'.format(platform.node()))
        result.append(_('Machine') + ': {}'.format(platform.machine()))
        try:       # python > 3.9
            import distro
            result.append(_('Distribution') + ': {} {} {}'.format(distro.linux_distribution()[0], distro.linux_distribution()[1], distro.linux_distribution()[2]))
        except:    # python <= 3.9
            result.append(_('Distribution') + ': {} {}'.format(platform.linux_distribution()[0], platform.linux_distribution()[1]))
            pass
        result.append(_('Total memory') + ': {}'.format(meminfo['MemTotal']))
        result.append(_('Free memory') + ': {}'.format(meminfo['MemFree']))
        result.append(_('Python') + ': {}'.format(platform.python_version()))
        if netdevs:
            for dev, info in netdevs.items():
                result.append(_('{}: Rx={}MB Tx={}MB ').format(dev, round(info['rx'],2), round(info['tx'],2)))
        else:
            result.append(_('Network: Unknown'))
        if options.use_ssl or options.use_own_ssl:
            result.append(_('IP address') + (': https://{}:{}').format(helpers.get_ip(), options.web_port))
        else:
            result.append(_('IP address') + (': http://{}:{}').format(helpers.get_ip(), options.web_port))
        result.append(_('Uptime') + ': {}'.format(helpers.uptime()))
        result.append(_('CPU temp') + ': {} {}'.format(helpers.get_cpu_temp(options.temp_unit), options.temp_unit))
        result.append(_('CPU usage') + ': {} %'.format(helpers.get_cpu_usage()))
        result.append(_('CPU serial number') + ': {}'.format(helpers.cpu_info()))
        result.append(_('MAC adress') + ': {}'.format(helpers.get_mac()))
        try:
            result.append(_('Wi-Fi signal') + ': {} %'.format(helpers.read_wifi_signal()))
        except:
            pass    
        result.append(_('I2C HEX Adress') + ': ')
        try:
            result.append(get_all_addr())
        except Exception:
            result.append(_('Could not open any i2c device!'))

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
        log.error(NAME, traceback.format_exc())
        pass

    return result


def get_usb():
    """Returns the usb data."""
    result = []
    try:
        cmd = 'lsusb'
        if (cmd.find('Error') != -1):
            result.append(_('Could not open lsusb!'))
        else:    
            result.append(process(cmd))

    except Exception:
        log.error(NAME, traceback.format_exc())
        pass

    return result


def get_tty():
    """Returns the tty data."""
    result = []
    try:
        cmd = 'ls /dev/tty*'
        if (cmd.find('Error') != -1):
            result.append(_('Could not open ls /dev/tty*!'))
        else:    
            result.append(process(cmd))

    except Exception:
        log.error(NAME, traceback.format_exc())
        pass

    return result

def get_aux():
    """Returns the from aux output."""
    result = []
    try:
        cmd = 'ps aux'
        if (cmd.find('Error') != -1):
            result.append(_('Could not open ps aux!'))
        else:    
            result.append(process(cmd))

    except Exception:
        log.error(NAME, traceback.format_exc())
        pass

    return result

def get_part():
    """Returns the from partitions."""
    result = []
    try:
        cmd = 'cat /proc/partitions'
        if (cmd.find('Error') != -1):
            result.append(_('Could not open cat /proc/partitions!'))
        else:    
            result.append(process(cmd))

    except Exception:
        log.error(NAME, traceback.format_exc())
        pass

    return result

def get_cpu():
    """Returns the CPU info."""
    result = []
    try:
        cmd = 'cat /proc/cpuinfo'
        if (cmd.find('Error') != -1):
            result.append(_('Could not open cat /proc/cpuinfo!'))
        else:    
            result.append(process(cmd))

    except Exception:
        log.error(NAME, traceback.format_exc())
        pass

    return result    


def find_address(search_range, range=False):
    try:
        import smbus
        bus = smbus.SMBus(0 if helpers.get_rpi_revision() == 1 else 1)
        if range:
           for addr, type in search_range.items():
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

    except ImportError:
        log.warning(NAME, _('Could not import smbus.'))

def get_all_addr():
    find_adr = ''
    try:
        import smbus
        bus = smbus.SMBus(0 if helpers.get_rpi_revision() == 1 else 1)
        find_adr += _('Available addresses') + '\n' 
        for addr in range(128):
            try:
                bus.read_byte(addr)
                find_adr += '0x{:02x}\n'.format(addr) 
            except Exception:
                pass

    except ImportError:
        log.warning(NAME, _('Could not import smbus.'))

    return find_adr       


def process(cmd):
    """process in system"""
    proc = subprocess.Popen(
        cmd,
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        shell=True)
    output = proc.communicate()[0]
    return output.decode('utf-8')

################################################################################
# Web pages:                                                                   #
################################################################################
class status_page(ProtectedPage):
    """Load an html page"""

    def GET(self):
        qdict = web.input()
        find_usb = helpers.get_input(qdict, 'find_usb', False, lambda x: True)
        find_tty = helpers.get_input(qdict, 'find_tty', False, lambda x: True)
        aux = helpers.get_input(qdict, 'aux', False, lambda x: True) 
        part = helpers.get_input(qdict, 'part', False, lambda x: True)
        cpu = helpers.get_input(qdict, 'cpu', False, lambda x: True)

        if find_usb:
            return self.plugin_render.system_info(get_usb())

        if find_tty:
            return self.plugin_render.system_info(get_tty())

        if aux:
            return self.plugin_render.system_info(get_aux())

        if part:
            return self.plugin_render.system_info(get_part())

        if cpu:
            return self.plugin_render.system_info(get_cpu())

        return self.plugin_render.system_info(get_overview())
