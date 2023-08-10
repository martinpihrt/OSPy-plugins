# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'


import datetime
import time
import sys
import os
import mimetypes

from threading import Thread, Event
import traceback
import json
import subprocess

import web
from ospy.log import log
from ospy.options import options
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string
from plugins import PluginOptions, plugin_url, plugin_data_dir


NAME = 'Label Maker'
MENU =  _('Package: Label Maker')
LINK = 'settings_page'

colors_name = ['BLACK', 'RED', 'GREEN','BLUE','ORANGE','BROWN']

plugin_options = PluginOptions(
    NAME,
    {
        'code_type': '0',            # 0=BAR EAN13, 1=QR black and white, 2=QR color, 3=QR with logo
        'msg': '',                   # last inserted message
        'color': '0',                # Color for fill in QR ('BLACK', 'RED', 'GREEN','BLUE','ORANGE','BROWN')
        'qr_back_color': 'white',    # QR back color
    })


################################################################################
# Main function loop:                                                          #
################################################################################
class Plugin_Checker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()
        self.start()

    def stop(self):
        self._stop_event.set()

    def run(self):
        log.info(NAME, datetime_string() + ' ' + _('Ready. Select code type and message.'))
        pass

    def update(self):
        try:
            log.clear(NAME)
            image_path = os.path.join(plugin_data_dir(), 'yourcode.png')
            instaled = None
            if plugin_options['code_type'] == "0": # EAN13 code
                try:
                    from barcode import EAN13
                    from barcode.writer import ImageWriter
                    instaled = True
                except:
                    log.info(NAME, datetime_string() + ' ' + _('Barcode not instaled, installing from pip (pip install python-barcode).'))
                    cmd = 'pip install python-barcode'
                    install(cmd)
                    log.info(NAME, datetime_string() + ' ' + _('Now restart this plugin!'))
                    pass
                if instaled is not None:
                    if plugin_options['msg'].isdigit():
                        if len(plugin_options['msg']) == 12:
                            with open(image_path, "wb") as f:
                                EAN13(plugin_options['msg'], writer=ImageWriter()).write(f)
                            log.info(NAME, datetime_string() + ' ' + _('Generated EAN13 code...'))
                        else:
                            log.error(NAME, datetime_string() + ' ' + _('EAN code must have 12 digits!'))
                    else:
                        log.error(NAME, datetime_string() + ' ' + _('EAN code can only contain numbers!'))

            if plugin_options['code_type'] == "1": # QR BW code
                try:
                    import qrcode
                    instaled = True
                except:
                    log.info(NAME, datetime_string() + ' ' + _('QRcode not instaled, installing from pip (pip install qrcode).'))
                    cmd = 'pip install qrcode'
                    install(cmd)
                    log.info(NAME, datetime_string() + ' ' + _('Now restart this plugin!'))
                    pass
                if instaled is not None:
                    if plugin_options['msg']:
                        img = qrcode.make(plugin_options['msg'])
                        img.save(image_path)
                        log.info(NAME, datetime_string() + ' ' + _('Generated QR BW code...'))
                    else:
                        log.error(NAME, datetime_string() + ' ' + _('You have to type some text before pressing the generate button!'))

            if plugin_options['code_type'] == "2": # QR color code
                try:
                    import qrcode
                    instaled = True
                except:
                    log.info(NAME, datetime_string() + ' ' + _('QRcode not instaled, installing from pip (pip install qrcode).'))
                    cmd = 'pip install qrcode'
                    install(cmd)
                    log.info(NAME, datetime_string() + ' ' + _('Now restart this plugin!'))
                    pass
                if instaled is not None:
                    if plugin_options['msg']:
                        qr = qrcode.QRCode(version = 1, box_size = 10, border = 5)
                        qr.add_data(plugin_options['msg'])
                        qr.make(fit = True)
                        img = qr.make_image(fill_color = colors_name[int(plugin_options['color'])], back_color = plugin_options['qr_back_color'])
                        img.save(image_path)
                        log.info(NAME, datetime_string() + ' ' + _('Generated QR color code...'))
                    else:
                        log.error(NAME, datetime_string() + ' ' + _('You have to type some text before pressing the generate button!'))

            if plugin_options['code_type'] == "3": # QR inserted logo
                try:
                    import qrcode
                    from PIL import Image
                    instaled = True
                except:
                    log.info(NAME, datetime_string() + ' ' + _('QRcode or Pillow not instaled, installing from pip (pip install qrcode, pip install Pillow).'))
                    cmd = 'pip install qrcode'
                    install(cmd)
                    cmd = 'pip install Pillow'
                    install(cmd)
                    log.info(NAME, datetime_string() + ' ' + _('Now restart this plugin!'))
                    pass
                if instaled is not None:
                    if plugin_options['msg']:
                        Logo_link = os.path.join('plugins','labelmaker','static','images','logo.png')
                        logo = Image.open(Logo_link)
                        basewidth = 100
                        wpercent = (basewidth/float(logo.size[0]))
                        hsize = int((float(logo.size[1])*float(wpercent)))
                        logo = logo.resize((basewidth, hsize), Image.ANTIALIAS)
                        QRcode = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H)
                        QRcode.add_data(plugin_options['msg'])
                        QRcode.make()
                        QRimg = QRcode.make_image(fill_color = colors_name[int(plugin_options['color'])], back_color = plugin_options['qr_back_color']).convert('RGB')
                        pos = ((QRimg.size[0] - logo.size[0]) // 2, (QRimg.size[1] - logo.size[1]) // 2)
                        QRimg.paste(logo, pos)
                        QRimg.save(image_path)
                        log.info(NAME, datetime_string() + ' ' + _('Generated QR code with logo...'))
                    else:
                        log.error(NAME, datetime_string() + ' ' + _('You have to type some text before pressing the generate button!'))

        except Exception:
            log.error(NAME, datetime_string() + ' ' + _('Label Maker plug-in') + ':\n' + traceback.format_exc())


checker = None


################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global checker
    if checker is None:
        checker = Plugin_Checker()


def stop():
    global checker
    if checker is not None:
        checker.stop()
        checker.join()
        checker = None


def install(cmd):
    proc = subprocess.Popen(cmd,stderr=subprocess.STDOUT,stdout=subprocess.PIPE,shell=True)
    output = proc.communicate()[0].decode('utf8')
    log.info(NAME, '{}'.format(output))


################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering adjustments"""

    def GET(self):
        return self.plugin_render.labelmaker(plugin_options, log.events(NAME))

    def POST(self):
        plugin_options.web_update(web.input())
        if checker is not None:
            checker.update()
        raise web.seeother(plugin_url(settings_page), True)


class download_page(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        try:
            download_name = plugin_data_dir() + '/' + 'yourcode.png'          
            if os.path.isfile(download_name):     # exists image? 
                content = mimetypes.guess_type(download_name)[0]
                web.header('Content-type', content)
                web.header('Content-Length', os.path.getsize(download_name))
                web.header('Content-Disposition', 'attachment; filename=yourcode')
                img = open(download_name,'rb')
                return img.read()
            else:
                download_name = os.path.join('plugins', 'labelmaker', 'static', 'images', 'nonecode.png')  
                content = mimetypes.guess_type(download_name)[0]
                web.header('Content-type', content)
                web.header('Content-Length', os.path.getsize(download_name))
                web.header('Content-Disposition', 'attachment; filename=none_code')
                img = open(download_name,'rb')
                return img.read()
        except:
            pass
            log.error(NAME, _('Label Maker plug-in') + ':\n' + traceback.format_exc())
            return self.plugin_render.labelmaker(plugin_options, log.events(NAME))


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.labelmaker_help()


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)