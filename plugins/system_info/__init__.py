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
        if netdevs:
            for dev, info in netdevs.iteritems():
                result.append('%-16s %s MiB %s MiB' % (dev + ': ', info['rx'], info['tx']))
        else:
            result.append(_('Network: Unknown'))
        result.append(_('Uptime') + ': ' + helpers.uptime())
        result.append(_('CPU temp') + ': ' + helpers.get_cpu_temp(options.temp_unit) + ' ' + options.temp_unit)
        result.append(_('MAC adress') + ': ' + helpers.get_mac())
        try:
            result.append(_('I2C HEX Adress') + ': ')
            rev = str(0 if helpers.get_rpi_revision() == 1 else 1)
            cmd = 'sudo i2cdetect -y ' + rev
            result.append(process(cmd))
        except Exception:
          result.append(_('System info plug-in') + ':\n' + traceback.format_exc())

    except:
        result.append(_('System info plug-in') + ':\n' + traceback.format_exc())
    return result


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
