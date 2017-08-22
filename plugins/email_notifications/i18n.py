#!/usr/bin/python
# encoding: utf-8
__author__ = 'Martin Pihrt'

import os
import locale
import gettext
import shelve

OPTIONS_FILE = './ospy/data/options.db'

try:
    db = shelve.open(OPTIONS_FILE)
    sd_lang = db['lang'] # example return sd_lang = 'cs_CZ'
    db.close()    
except:
    sd_lang = 'default'

### here add next languages ###
languages = ({
    "en_US": "English",
    "cs_CZ": "Czech",
})
###############################

def get_system_lang():
    """Return default system locale language"""
    lc, encoding = locale.getdefaultlocale()
    if lc:
        return lc
    else:
        return None

# File location directory.
curdir = os.path.abspath(os.path.dirname(__file__))

# i18n directory.
localedir = curdir + '/i18n' 

gettext.install('ospy_messages', localedir, unicode=True)

sys_lang = get_system_lang()

if sd_lang == 'default':
    if sys_lang in languages:
        ui_lang = sys_lang
    else:
        ui_lang = 'en_US'
else:
    ui_lang = sd_lang

try:
    gettext.translation('ospy_messages', localedir, languages=[ui_lang]).install(True)
except IOError:
    pass
