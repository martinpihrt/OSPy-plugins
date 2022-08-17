# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'

import json
import time
import datetime
import traceback
import os
from threading import Thread, Event

import web

from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import get_rpi_revision, datetime_string, get_input
from ospy import helpers
from ospy.options import options

import requests, shutil
from requests.auth import HTTPBasicAuth
import mimetypes

from PIL import Image
import glob


NAME = 'IP Cam'
MENU =  _(u'Package: IP Cam')
LINK = 'settings_page'


plugin_options = PluginOptions(
    NAME,
    {
        'jpg_ip': ['']*options.output_count,       # IP address for jpeg image
        'jpg_que': ['']*options.output_count,      # Query for jpeg image
        'mjpeg_que': ['']*options.output_count,    # Query for mjpeg image        
        'jpg_user': ['']*options.output_count,     # Username for access to jpeg image
        'jpg_pass': ['']*options.output_count,     # Password for access to jpeg image
        'use_jpg': True,                           # first download jpeg from IP address to plugin folder and next show these jpg on webpage
        'use_gif': True,                           # first download jpeg from IP address to plugin folder and next create gif and show these gif on webpage
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
        img_counter = 0
        while not self._stop_event.is_set():
            try:
                if plugin_options['use_jpg']:
                    img_down_state = []
                    for c in range(0, options.output_count):
                        if plugin_options['jpg_ip'][c] and plugin_options['jpg_que'][c] and plugin_options['jpg_user'][c] and plugin_options['jpg_pass'][c]:
                            url_ip_port = '{}'.format(plugin_options['jpg_ip'][c])
                            url_query = '{}'.format(plugin_options['jpg_que'][c])
                            url_user = '{}'.format(plugin_options['jpg_user'][c])
                            url_pass = '{}'.format(plugin_options['jpg_pass'][c])
                            img_path = os.path.join(plugin_data_dir(), '{}.jpg'.format(c+1))
                            try:
                                res = requests.get(url_ip_port + '/' + url_query, stream = True, verify=False, auth=HTTPBasicAuth(url_user, url_pass))
                                if res.status_code == 200:
                                    with open(img_path, 'wb') as f:
                                        shutil.copyfileobj(res.raw, f)
                                    img_down_state.append('{}.jpg'.format(c+1))
                            except:
                                log.error(NAME, _(u'IP Cam plug-in') + ':\n' + traceback.format_exc())
                                pass

                    log.clear(NAME)
                    log.info(NAME, _(u'Downloaded images') + ': ' + datetime_string())
                    log.info(NAME, str(img_down_state)[1:-1])
                
                self._sleep(2)

                if plugin_options['use_gif']:                
                    for c in range(0, options.output_count):
                        if plugin_options['jpg_ip'][c] and plugin_options['jpg_que'][c] and plugin_options['jpg_user'][c] and plugin_options['jpg_pass'][c]:
                            IMG_FILE = os.path.join(plugin_data_dir(), str(c+1), '{}.jpg'.format(img_counter))
                            SOURCE_FILE = os.path.join(plugin_data_dir(), '{}.jpg'.format(c+1))                            
                            if not os.path.isdir(os.path.dirname(IMG_FILE)):
                                helpers.mkdir_p(os.path.dirname(IMG_FILE))
                            if os.path.isfile(SOURCE_FILE):
                                shutil.copy(SOURCE_FILE, IMG_FILE)
                    
                    img_counter += 1
                    if img_counter >= 10:
                        img_counter = 0
                        for c in range(0, options.output_count):
                            if plugin_options['jpg_ip'][c] and plugin_options['jpg_que'][c] and plugin_options['jpg_user'][c] and plugin_options['jpg_pass'][c]:
                                frames = []
                                for i in range(0, 9):
                                    IMG_FILE = os.path.join(plugin_data_dir(), str(c+1), '{}.jpg'.format(i))
                                    if os.path.isfile(IMG_FILE):
                                        frames.append(Image.open(IMG_FILE))
                                if len(frames) > 0:
                                    frame_one = frames[0]
                                    frame_one.save('plugins/ip_cam/data/{}.gif'.format(c+1), format='GIF', append_images=frames, save_all=True, duration=100, loop=0)
                                    log.info(NAME, _(u'Creating {}.gif').format(c+1))      

                self._sleep(3)

            except Exception:
                log.error(NAME, _(u'IP Cam plug-in') + ':\n' + traceback.format_exc())
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


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Main html page"""

    def GET(self):
        global sender
        qdict = web.input()

        cam = get_input(qdict, 'cam', False, lambda x: True)
        cam_foto = get_input(qdict, 'cam_foto', False, lambda x: True)
        cam_gif = get_input(qdict, 'cam_gif', False, lambda x: True)

        if sender is not None and cam:
            cam_nr = int(qdict['cam'])
            return self.plugin_render.ip_cam_mjpeg(plugin_options, cam_nr)

        if sender is not None:
            if cam_foto:
                cam_nr = qdict['cam_foto']
                download_name = plugin_data_dir() + '/' + '{}.jpg'.format(cam_nr)
            elif cam_gif:
                cam_nr = qdict['cam_gif']
                download_name = plugin_data_dir() + '/' + '{}.gif'.format(cam_nr)
            else:
                return self.plugin_render.ip_cam(plugin_options, log.events(NAME))

            if os.path.isfile(download_name):     # exists image? 
                content = mimetypes.guess_type(download_name)[0]
                web.header('Content-type', content)
                web.header('Content-Length', os.path.getsize(download_name))
                web.header('Content-Disposition', 'attachment; filename=%s' % str(id))
                img = open(download_name,'rb')
                return img.read()
            else:
                return None

    def POST(self):
        return self.plugin_render.ip_cam(plugin_options, log.events(NAME))
                

class setup_page(ProtectedPage):
    """Load an html setup page."""

    def GET(self):
        qdict = web.input()
        msg = 'none'
  
        try:
            return self.plugin_render.ip_cam_setup(plugin_options, msg)   
        except:           
            plugin_options.__setitem__('jpg_ip', ['']*options.output_count)
            plugin_options.__setitem__('jpg_que', ['']*options.output_count)
            plugin_options.__setitem__('mjpeg_que', ['']*options.output_count)
            plugin_options.__setitem__('jpg_user', ['']*options.output_count)
            plugin_options.__setitem__('jpg_pass', ['']*options.output_count)

            return self.plugin_render.ip_cam_setup(plugin_options, msg)

    def POST(self):
        global sender
        try:
            qdict = web.input()
            commands = {'mjpeg_que': [], 'jpg_ip': [], 'jpg_que': [], 'jpg_user': [], 'jpg_pass': []}
            for i in range(0, options.output_count):
                if 'mjpeg_que'+str(i) in qdict:
                    commands['mjpeg_que'].append(qdict['mjpeg_que'+str(i)])
                else:
                    commands['mjpeg_que'].append('')

                if 'jpg_ip'+str(i) in qdict:
                    commands['jpg_ip'].append(qdict['jpg_ip'+str(i)])
                else:
                    commands['jpg_ip'].append('')

                if 'jpg_que'+str(i) in qdict:
                    commands['jpg_que'].append(qdict['jpg_que'+str(i)])
                else:
                    commands['jpg_que'].append('')

                if 'jpg_user'+str(i) in qdict:
                    commands['jpg_user'].append(qdict['jpg_user'+str(i)])
                else:
                    commands['jpg_user'].append('')

                if 'jpg_pass'+str(i) in qdict:
                    commands['jpg_pass'].append(qdict['jpg_pass'+str(i)])
                else:
                    commands['jpg_pass'].append('')                                                                                

            if 'use_jpg' in qdict:
                if qdict['use_jpg']=='on':
                     plugin_options.__setitem__('use_jpg', True)
                else:
                    plugin_options.__setitem__('use_jpg', False)

            if 'use_gif' in qdict:
                if qdict['use_gif']=='on':
                     plugin_options.__setitem__('use_gif', True)
                else:
                    plugin_options.__setitem__('use_gif', False)                    

            plugin_options.__setitem__('mjpeg_que', commands['mjpeg_que'])
            plugin_options.__setitem__('jpg_ip', commands['jpg_ip'])
            plugin_options.__setitem__('jpg_que', commands['jpg_que'])
            plugin_options.__setitem__('jpg_user', commands['jpg_user'])
            plugin_options.__setitem__('jpg_pass', commands['jpg_pass'])

            if sender is not None:
                sender.update()

        except Exception:
            log.debug(NAME, _('IP cam plug-in') + ':\n' + traceback.format_exc())
            pass

        msg = 'saved'
        return self.plugin_render.ip_cam_setup(plugin_options, msg)


class help_page(ProtectedPage):
    """Load an html page for help page."""

    def GET(self):
        return self.plugin_render.ip_cam_help()         


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)