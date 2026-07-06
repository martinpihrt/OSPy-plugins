# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'


import datetime
import time
import sys
import os
import mimetypes

from threading import Thread, Event, Lock
import traceback
import json
import re
import importlib.util
import shutil
import subprocess

import web
from ospy.log import log
from ospy.options import options
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string, verify_csrf
from plugins import PluginOptions, plugin_url, plugin_data_dir


NAME = 'Label Maker'
MENU =  _('Package: Label Maker')
LINK = 'settings_page'

colors_name = ['BLACK', 'RED', 'GREEN','BLUE','ORANGE','BROWN']
qr_error_levels = ['L', 'M', 'Q', 'H']
dependency_install_lock = Lock()
dependency_install_running = False

plugin_options = PluginOptions(
    NAME,
    {
        'code_type': '0',            # 0=BAR EAN13, 1=QR black and white, 2=QR color, 3=QR with logo
        'msg': '',                   # last inserted message
        'color': '0',                # Color for fill in QR ('BLACK', 'RED', 'GREEN','BLUE','ORANGE','BROWN')
        'qr_back_color': '#ffffff',  # QR back color
        'qr_box_size': 10,           # QR module size
        'qr_border': 5,              # QR quiet zone
        'qr_error_correction': 'M',  # QR error correction L/M/Q/H
        'filename': 'yourcode',      # Download filename
    })


def _safe_int(value, default, min_value, max_value):
    try:
        value = int(value)
    except Exception:
        value = default
    return max(min_value, min(max_value, value))


def _safe_color_index(value):
    return _safe_int(value, 0, 0, len(colors_name) - 1)


def _safe_filename(value):
    value = (value or 'yourcode').strip()
    value = re.sub(r'[^A-Za-z0-9._-]+', '_', value)
    value = value.strip('._-')
    return value or 'yourcode'


def _generated_image_path():
    return os.path.join(plugin_data_dir(), 'yourcode.png')


def _qr_error_correction(qrcode):
    level = str(plugin_options['qr_error_correction']).upper()
    if level not in qr_error_levels:
        level = 'M'
    return {
        'L': qrcode.constants.ERROR_CORRECT_L,
        'M': qrcode.constants.ERROR_CORRECT_M,
        'Q': qrcode.constants.ERROR_CORRECT_Q,
        'H': qrcode.constants.ERROR_CORRECT_H,
    }[level]


def _validate_message(code_type, message):
    if code_type == "0":
        if not message:
            return _('EAN code must have 12 digits!')
        if not message.isdigit():
            return _('EAN code can only contain numbers!')
        if len(message) != 12:
            return _('EAN code must have 12 digits!')
    else:
        if not message:
            return _('You have to type some text before pressing the generate button!')
        if len(message) > 500:
            return _('QR message must not be longer than 500 characters!')
    return ''


def _log_generated(kind, image_path, message):
    log.info(NAME, datetime_string() + ' ' + kind)
    log.info(NAME, datetime_string() + ' ' + _('Message length') + ': {}'.format(len(message)))
    if os.path.isfile(image_path):
        log.info(NAME, datetime_string() + ' ' + _('Output file') + ': {}'.format(os.path.basename(image_path)))


def _missing_dependency(package_name, apt_package):
    log.error(NAME, datetime_string() + ' ' + _('Missing Python package') + ': {}'.format(package_name))
    log.info(NAME, datetime_string() + ' ' + _('Install it from the system package manager and restart this plug-in.'))
    log.info(NAME, datetime_string() + ' sudo apt install {}'.format(apt_package))


def labelmaker_dependency_specs(code_type=None):
    code_type = str(code_type if code_type is not None else plugin_options['code_type'])
    if code_type == "0":
        return [('barcode', 'python-barcode', 'python3-barcode')]
    if code_type in ("1", "2"):
        return [('qrcode', 'qrcode', 'python3-qrcode')]
    if code_type == "3":
        return [('qrcode', 'qrcode', 'python3-qrcode'), ('PIL', 'Pillow', 'python3-pil')]
    return []


def labelmaker_missing_dependencies(code_type=None):
    missing = []
    for module_name, package_name, apt_package in labelmaker_dependency_specs(code_type):
        if importlib.util.find_spec(module_name) is None:
            missing.append({
                'module': module_name,
                'package': package_name,
                'apt': apt_package,
            })
    return missing


def labelmaker_dependencies_installing():
    with dependency_install_lock:
        return dependency_install_running


def start_labelmaker_dependency_install():
    global dependency_install_running
    with dependency_install_lock:
        if dependency_install_running:
            log.info(NAME, datetime_string() + ' ' + _('Dependency installation is already running.'))
            return
        dependency_install_running = True

    install_thread = Thread(target=install_labelmaker_dependencies)
    install_thread.daemon = True
    install_thread.start()


def install_labelmaker_dependencies():
    global dependency_install_running
    try:
        missing = labelmaker_missing_dependencies()
        if not missing:
            log.info(NAME, datetime_string() + ' ' + _('Dependencies are already installed.'))
            return

        apt_packages = sorted(set(item['apt'] for item in missing))
        log.info(NAME, datetime_string() + ' ' + _('Installing dependencies. This operation can take several minutes.'))

        if os.name != 'posix' or not shutil.which('apt-get'):
            log.error(NAME, datetime_string() + ' ' + _('Automatic dependency installation is available only on systems with apt-get.'))
            log.info(NAME, datetime_string() + ' sudo apt install {}'.format(' '.join(apt_packages)))
            return

        cmd = ['apt-get', 'install', '-y'] + apt_packages
        if hasattr(os, 'geteuid') and os.geteuid() != 0:
            if shutil.which('sudo'):
                cmd.insert(0, 'sudo')
            else:
                log.error(NAME, datetime_string() + ' ' + _('Root privileges are required for installing dependencies.'))
                log.info(NAME, datetime_string() + ' sudo apt install {}'.format(' '.join(apt_packages)))
                return

        log.info(NAME, datetime_string() + ' ' + _('Running command') + ': ' + ' '.join(cmd))
        proc = subprocess.run(cmd, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, timeout=900)
        output = proc.stdout.decode('utf-8', 'replace').strip()
        if output:
            log.info(NAME, output[-4000:])

        missing = labelmaker_missing_dependencies()
        if proc.returncode == 0 and not missing:
            log.info(NAME, datetime_string() + ' ' + _('Dependencies were installed successfully.'))
        else:
            log.error(NAME, datetime_string() + ' ' + _('Dependency installation failed. Missing modules') + ': ' + ', '.join(item['package'] for item in missing))
    except:
        log.error(NAME, datetime_string() + ' ' + _('Label Maker plug-in') + ':\n' + traceback.format_exc())
    finally:
        with dependency_install_lock:
            dependency_install_running = False


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
            image_path = _generated_image_path()
            code_type = str(plugin_options['code_type'])
            message = (plugin_options['msg'] or '').strip()
            validation_error = _validate_message(code_type, message)
            if validation_error:
                log.error(NAME, datetime_string() + ' ' + validation_error)
                return

            instaled = None
            if code_type == "0": # EAN13 code
                try:
                    from barcode import EAN13
                    from barcode.writer import ImageWriter
                    instaled = True
                except:
                    _missing_dependency('python-barcode', 'python3-barcode')
                if instaled is not None:
                    with open(image_path, "wb") as f:
                        EAN13(message, writer=ImageWriter()).write(f)
                    _log_generated(_('Generated EAN13 code...'), image_path, message)

            if code_type in ("1", "2", "3"): # QR codes
                try:
                    import qrcode
                    instaled = True
                except:
                    _missing_dependency('qrcode', 'python3-qrcode')
                if instaled is not None:
                    qr = qrcode.QRCode(
                        version=None,
                        error_correction=_qr_error_correction(qrcode),
                        box_size=_safe_int(plugin_options['qr_box_size'], 10, 2, 20),
                        border=_safe_int(plugin_options['qr_border'], 5, 1, 10)
                    )
                    qr.add_data(message)
                    qr.make(fit=True)

                    fill_color = 'BLACK' if code_type == "1" else colors_name[_safe_color_index(plugin_options['color'])]
                    back_color = '#ffffff' if code_type == "1" else plugin_options['qr_back_color']
                    img = qr.make_image(fill_color=fill_color, back_color=back_color)

                    if code_type == "3":
                        try:
                            from PIL import Image
                        except:
                            _missing_dependency('Pillow', 'python3-pil')
                            return

                        logo_link = os.path.join('plugins', 'labelmaker', 'static', 'images', 'logo.png')
                        if not os.path.isfile(logo_link):
                            log.error(NAME, datetime_string() + ' ' + _('Logo file was not found!'))
                            return

                        logo = Image.open(logo_link)
                        resampling = getattr(getattr(Image, 'Resampling', Image), 'LANCZOS', Image.BICUBIC)
                        qr_img = img.convert('RGB')
                        basewidth = max(40, min(120, qr_img.size[0] // 4))
                        wpercent = basewidth / float(logo.size[0])
                        hsize = int(float(logo.size[1]) * float(wpercent))
                        logo = logo.resize((basewidth, hsize), resampling)
                        pos = ((qr_img.size[0] - logo.size[0]) // 2, (qr_img.size[1] - logo.size[1]) // 2)
                        if logo.mode in ('RGBA', 'LA'):
                            qr_img.paste(logo, pos, logo)
                        else:
                            qr_img.paste(logo, pos)
                        img = qr_img

                    img.save(image_path)
                    if code_type == "1":
                        _log_generated(_('Generated QR BW code...'), image_path, message)
                    elif code_type == "2":
                        _log_generated(_('Generated QR color code...'), image_path, message)
                    else:
                        _log_generated(_('Generated QR code with logo...'), image_path, message)

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
        checker.join(15)
        checker = None


################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering adjustments"""

    def GET(self):
        try:
            qdict = web.input()
            install_deps = qdict.get('install_deps') is not None
            if install_deps:
                verify_csrf(qdict)
                start_labelmaker_dependency_install()
                raise web.seeother(plugin_url(settings_page), True)

            missing = labelmaker_missing_dependencies()
            return self.plugin_render.labelmaker(
                plugin_options,
                log.events(NAME),
                missing,
                labelmaker_dependencies_installing(),
                ', '.join(item['apt'] for item in missing),
            )
        except web.HTTPError:
            raise
        except:
            log.error(NAME, _('Label Maker plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('labelmaker -> settings_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            qdict = web.input()
            verify_csrf(qdict)
            plugin_options.web_update(qdict)
            if checker is not None:
                checker.update()
            raise web.seeother(plugin_url(settings_page), True)
        except web.HTTPError:
            raise
        except Exception:
            log.error(NAME, _('Label Maker plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('labelmaker -> settings_page POST')
            return self.core_render.notice('/', msg)

class download_page(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        try:
            download_name = _generated_image_path()
            if os.path.isfile(download_name):     # exists image? 
                content = mimetypes.guess_type(download_name)[0] or 'image/png'
                filename = _safe_filename(plugin_options['filename']) + '.png'
                web.header('Content-type', content)
                web.header('Content-Length', os.path.getsize(download_name))
                web.header('Content-Disposition', 'attachment; filename="{}"'.format(filename))
                img = open(download_name,'rb')
                return img.read()
            else:
                download_name = os.path.join('plugins', 'labelmaker', 'static', 'images', 'nonecode.png')  
                content = mimetypes.guess_type(download_name)[0] or 'image/png'
                web.header('Content-type', content)
                web.header('Content-Length', os.path.getsize(download_name))
                web.header('Content-Disposition', 'attachment; filename="none_code.png"')
                img = open(download_name,'rb')
                return img.read()
        except:
            log.error(NAME, _('Label Maker plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('labelmaker -> download_page GET')
            return self.core_render.notice('/', msg)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            return self.plugin_render.labelmaker_help()
        except:
            log.error(NAME, _('Label Maker plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('labelmaker -> help_page GET')
            return self.core_render.notice('/', msg)

class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(plugin_options)
        except:
            return {}


class status_json(ProtectedPage):
    """Returns the current plugin status log in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            missing = labelmaker_missing_dependencies()
            return json.dumps({
                'events': log.events(NAME),
                'missing': [item['apt'] for item in missing],
                'installing': labelmaker_dependencies_installing(),
            })
        except:
            return {}
