# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# this plugins print debug info from ./data/events.log 

from ospy.webpages import ProtectedPage
from ospy import log
from ospy import helpers

from plugins import plugin_url
from plugins import PluginOptions
import web
import os
import json
import mimetypes


NAME = 'System Debug Information'
MENU =  _('Package: System Debug Information')
LINK = 'status_page'

debug_options = PluginOptions(
    NAME,
    {
        "log_records": 500
    }
)


################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    pass


stop = start

def tail(f, lines=20):
    total_lines_wanted = lines

    BLOCK_SIZE = 1024
    f.seek(0, 2)
    block_end_byte = f.tell()
    lines_to_go = total_lines_wanted+1
    block_number = -1
    blocks = [] # blocks of size BLOCK_SIZE, in reverse order starting
                # from the end of the file
    while lines_to_go > 0 and block_end_byte > 0:
        if (block_end_byte - BLOCK_SIZE > 0):
            # read the last block we haven't yet read
            f.seek(block_number*BLOCK_SIZE, 2)
            blocks.append(f.read(BLOCK_SIZE))
        else:
            # file too small, start from begining
            f.seek(0,0)
            # only read what was not read
            blocks.append(f.read(block_end_byte))
        lines_found = blocks[-1].count(b'\n') 
        lines_to_go -= lines_found
        block_end_byte -= BLOCK_SIZE
        block_number -= 1
    all_read_text = (b''.join(reversed(blocks))).decode('utf-8')
    return all_read_text.splitlines()[-total_lines_wanted:]

def get_overview():
    """Returns the info data as a list of lines."""
    result = []    
    max_res = int(debug_options['log_records'])
    try:
        with open(log.EVENT_FILE, 'rb') as fh:
            result = tail(fh, max_res) 
           
    except Exception:
        pass
        #import traceback
        #result = traceback.format_exc().split('\n')
        result.append(_('Error: Log file missing. Enable it in system options.'))

    return result

def read_log():
    """Read log from json file."""
    try:                
        logf = open(log.EVENT_FILE,"r")
        return logf.read()

    except IOError:
        return []

################################################################################
# Web pages:                                                                   #
################################################################################
class status_page(ProtectedPage):
    """Load an html page"""

    def GET(self):
        qdict = web.input()
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)
        if delete:
            try:
                os.remove(log.EVENT_FILE)
            except Exception:
                pass
            raise web.seeother(plugin_url(status_page), True)

        return self.plugin_render.system_debug(debug_options,get_overview())


class settings_page(ProtectedPage):
    """Save an html page for entering."""

    def POST(self):
        debug_options.web_update(web.input())
        raise web.seeother(plugin_url(status_page), True)


class log_page(ProtectedPage):
    """Return log."""

    def GET(self):
        result = ''
        try:
            result = json.dumps(read_log())
        except Exception:
            pass
            result = _('Error: Log file missing. Enable it in system options.')

        content = mimetypes.guess_type(log.EVENT_FILE)[0]
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-type', content)  
        web.header('Content-Disposition', 'attachment; filename=debuglog.txt')
        return result
