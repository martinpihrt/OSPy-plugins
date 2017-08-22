#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# This plugin save image from webcam to ./data/image.jpg
# fswebcam --list-controls -r 1280x720 --info OpenSprinkler -S 3 --save ./data/image.jpg


import json
import subprocess
import traceback
import re
import os

import web
from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage

import i18n

NAME = 'Webcam Monitor'
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


def get_run_cam():
    try:
        if cam_options['enabled']:                  # if cam plugin is enabled

            if cam_options['flip_h']:
                flip_img_h = ' --flip h'
            else:
                flip_img_h = ''

            if cam_options['flip_v']:
                flip_img_v = ' --flip v'
            else:
                flip_img_v = ''

            if os.path.exists('/dev/video0'):              # if usb cam exists
                if not os.path.exists("/usr/bin/fswebcam"): # if fswebcam is installed
                    log.clear(NAME)
                    log.info(NAME, _('Fswebcam is not installed.'))
                    log.info(NAME, _('Please wait installing....'))
                    cmd = "sudo apt-get install fswebcam"
                    proc = subprocess.Popen(
                        cmd,
                        stderr=subprocess.STDOUT, # merge stdout and stderr
                        stdout=subprocess.PIPE,
                        shell=True)
                    output = proc.communicate()[0]
                    log.info(NAME, output)
                    cam_options['installed_fswebcam'] = False

                else:
                    cam_options['installed_fswebcam'] = True
                    log.clear(NAME)
                    log.info(NAME, _('Please wait...'))

                    cmd = "fswebcam -r " + cam_options[
                        'resolution'] + flip_img_h + flip_img_v + " --info OpenSprinkler -S 3 --save " + get_image_location()
                    proc = subprocess.Popen(
                        cmd,
                        stderr=subprocess.STDOUT, # merge stdout and stderr
                        stdout=subprocess.PIPE,
                        shell=True)
                    output = proc.communicate()[0]
                    text = re.sub('\x1b[^m]*m', '', output) # remove color character from communication in text
                    log.info(NAME, text)
                    log.info(NAME, _('Ready...'))
            else:
                log.clear(NAME)
                log.info(NAME, _('Cannot find USB camera (/dev/video0).'))
                cam_options['installed_fswebcam'] = False

        else:
            log.clear(NAME)
            log.info(NAME, _('Plugin is disabled...'))
            cam_options['installed_fswebcam'] = False

    except Exception:
        log.error(NAME, _('Webcam plug-in') + ':\n' + traceback.format_exc())
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
        cam_options.web_update(web.input())
        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(cam_options)


class download_page(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'image/jpeg')
        try:
            with open(get_image_location()) as f:
                return f.read()
        except:
            log.info(NAME, _('No image file from downloading. Retry'))
            raise web.seeother(plugin_url(settings_page), True)

