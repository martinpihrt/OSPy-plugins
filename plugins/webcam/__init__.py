# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'
# This plugin save image from webcam to ./data/image.jpg
# fswebcam --list-controls -r 1280x720 --info OpenSprinkler -S 3 --save ./data/image.jpg


import json
import subprocess
import traceback
import re
import os
import mimetypes

import web
from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.options import options
from ospy.helpers import verify_csrf

NAME = 'Webcam Monitor'
MENU =  _(u'Package: Webcam Monitor')
LINK = 'settings_page'

cam_options = PluginOptions(
    NAME,
    {'enabled': False,
     'flip_h': False,
     'flip_v': False,
     'resolution': '1280x720',
     'installed_fswebcam': False
    }
)


################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    pass


stop = start


def get_image_location():
    return os.path.join(plugin_data_dir(), 'image.jpg')


def normalize_options():
    resolution = str(cam_options.get('resolution', '1280x720')).strip().lower()
    if not re.match(r'^\d{2,5}x\d{2,5}$', resolution):
        resolution = '1280x720'
    cam_options['resolution'] = resolution


def get_run_cam():
    try:
        normalize_options()
        if cam_options['enabled']:                  # if cam plugin is enabled
            if os.path.exists('/dev/video0'):              # if usb cam exists
                if not os.path.exists("/usr/bin/fswebcam"): # if fswebcam is installed
                    log.clear(NAME)
                    log.info(NAME, _(u'Fswebcam is not installed.'))
                    log.info(NAME, _(u'Install it from the system package manager and restart this plug-in.'))
                    log.info(NAME, 'sudo apt install fswebcam')
                    cam_options['installed_fswebcam'] = False

                else:
                    cam_options['installed_fswebcam'] = True
                    log.clear(NAME)
                    log.info(NAME, _(u'Please wait...'))

                    cmd = ["fswebcam", "-r", cam_options['resolution']]
                    if cam_options['flip_h']:
                        cmd.extend(["--flip", "h"])
                    if cam_options['flip_v']:
                        cmd.extend(["--flip", "v"])
                    cmd.extend(["--info", "OSPyCAM", "-S", "3", "--save", get_image_location()])
                    proc = subprocess.run(cmd, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, timeout=60)
                    output = proc.stdout.decode('utf-8', errors='replace')
                    text = re.sub('\x1b[^m]*m', '', output) # remove color character from communication in text
                    log.info(NAME, text)
                    log.info(NAME, _(u'Ready...'))
            else:
                log.clear(NAME)
                log.info(NAME, _(u'Cannot find USB camera (/dev/video0).'))
                cam_options['installed_fswebcam'] = False

        else:
            log.clear(NAME)
            log.info(NAME, _(u'Plugin is disabled...'))
            cam_options['installed_fswebcam'] = False

    except Exception:
        log.error(NAME, _(u'Webcam plug-in') + ':\n' + traceback.format_exc())
        cam_options['installed_fswebcam'] = False


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering webcam adjustments."""

    def GET(self):
        get_run_cam()
        return self.plugin_render.webcam(cam_options, log.events(NAME))


    def POST(self):
        qdict = web.input()
        verify_csrf(qdict)
        cam_options.web_update(qdict)
        normalize_options()
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.webcam_help()        


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(cam_options)


class download_page(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        try:
            web.header('Access-Control-Allow-Origin', '*')
            content = mimetypes.guess_type(get_image_location())[0] or 'image/jpeg'
            web.header('Content-type', content)
            web.header('Content-Disposition', 'attachment; filename=' + u'OSPy camera {}.jpg'.format(options.name))
            with open(get_image_location(), 'rb') as f:
                return f.read()
        except:
            log.info(NAME, _(u'No image file from downloading. Retry'))
            raise web.seeother(plugin_url(settings_page), True)

