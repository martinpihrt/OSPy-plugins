# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# this plugins check sha on github and update ospy file from github

from threading import Thread, Event, Condition
import time
import subprocess
import sys
import traceback

import web
from ospy.webpages import ProtectedPage
from ospy.helpers import restart
from ospy.log import log, logEM
from plugins import PluginOptions, plugin_url
from ospy import version
from ospy.options import options
from ospy.helpers import datetime_string

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer
#from ospy.webpages import showOnTimeline # Enable plugin to display station data on timeline


NAME = 'System Update'
MENU =  _(u'Package: System Update')
LINK = 'status_page'

plugin_options = PluginOptions(
    NAME, 
    {
        'auto_update': False,
        'use_update': False,
        'use_eml': False,
        'eml_subject': _(u'Report from OSPy SYSTEM UPDATE plugin')
    }
)


class StatusChecker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self.started = Event()
        self._done = Condition()
        self._stop = Event()

        self.status = {
            'ver_str': version.ver_str,
            'ver_date': version.ver_date,
            'remote': _(u'None!'),
            'remote_branch': 'origin/master',
            'can_update': False}

        self._sleep_time = 0
        self.start()

    def stop(self):
        self._stop.set()

    def update_wait(self):
        self._done.acquire()
        self._sleep_time = 0
        self._done.wait(10)
        self._done.release()

    def update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def _update_rev_data(self):
        """Returns the update revision data."""

        command = 'git remote update'
        subprocess.check_output(command.split())

        command = 'git config --get remote.origin.url'
        remote = subprocess.check_output(command.split()).strip()
        if remote:
            self.status['remote'] = remote

        command = 'git rev-parse --abbrev-ref --symbolic-full-name @{u}'
        remote_branch = subprocess.check_output(command.split()).strip()
        if remote_branch:
            self.status['remote_branch'] = remote_branch

        command = 'git log -1 %s --format=%%cd --date=short' % remote_branch
        new_date = subprocess.check_output(command.split()).strip()

        command = 'git rev-list %s --count --first-parent' % remote_branch
        new_revision = int(subprocess.check_output(command.split()))

        command = 'git log HEAD..%s --oneline' % remote_branch
        changes = '  ' + '\n  '.join(subprocess.check_output(command.split()).split('\n'))
        changes = changes.decode('utf-8')

        if new_revision == version.revision and new_date == version.ver_date:
            log.info(NAME, _(u'Up-to-date.'))
            self.status['can_update'] = False
        elif new_revision > version.revision:
            log.info(NAME, _(u'New version is available!'))
            log.info(NAME, _(u'Currently running revision') + ': %d (%s)' % (version.revision, version.ver_date))
            log.info(NAME, _(u'Available revision') + ': %d (%s)' % (new_revision, new_date))
            log.info(NAME, _(u'Changes') +':\n' + changes)
            self.status['can_update'] = True
            msg = '<b>' + _(u'System update plug-in') + '</b> ' + '<br><p style="color:red;">' 
            msg += _(u'New OSPy version is available!') + '<br>' 
            msg += _(u'Currently running revision') + ': %d (%s)' % (version.revision, version.ver_date) + '<br>'
            msg += _(u'Available revision') + ': %d (%s)' % (new_revision, new_date) + '.' + '</p>'
            msglog =   _(u'System update plug-in') + ': '
            msglog +=  _(u'New OSPy version is available!') + '-> ' + _(u'Currently running revision') + ': %d (%s)' % (version.revision, version.ver_date) + ', '
            msglog +=  _(u'Available revision') + ': %d (%s)' % (new_revision, new_date) + '.'

            if plugin_options['use_eml']:
                try:
                    from plugins.email_notifications import try_mail                                    
                    try_mail(msg, msglog, attachment=None, subject=plugin_options['eml_subject']) # try_mail(text, logtext, attachment=None, subject=None)

                except Exception:     
                    log.error(NAME, _(u'System update plug-in') + ':\n' + traceback.format_exc()) 



        else:
            log.info(NAME, _(u'Running unknown version!'))
            log.info(NAME, _(u'Currently running revision') + ': %d (%s)' % (version.revision, version.ver_date))
            log.info(NAME, _(u'Available revision') + ': %d (%s)' % (new_revision, new_date))
            self.status['can_update'] = False

        self._done.acquire()
        self._done.notify_all()
        self._done.release()

    def run(self):
        temp_upd = showInFooter() #  instantiate class to enable data in footer
        temp_upd.button = "system_update/status"    # button redirect on footer
        temp_upd.label =  _(u'System Update')       # label on footer
        msg ='Waiting to state'
        temp_upd.val = msg.encode('utf8')           # value on footer 

        while not self._stop.is_set():
            try:
                if plugin_options['use_update']:
                    log.clear(NAME)
                    self._update_rev_data()
                        
                    if self.status['can_update']:
                        msg =_(u'New OSPy version is available!') 
                    else:
                        msg =_(u'Up-to-date')    

                    if self.status['can_update'] and plugin_options['auto_update']:
                        perform_update()
                      
                    self.started.set()
                else:
                    msg =_(u'Plugin is not enabled')

                temp_upd.val = msg.encode('utf8')  # value on footer  

                self._sleep(3600)

            except Exception:
                self.started.set()
                log.error(NAME, _(u'System update plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)


checker = None


################################################################################
# Helper functions:                                                            #
################################################################################
def perform_update():
    try:
       # ignore local chmod permission
       command = "git config core.filemode false"  # http://superuser.com/questions/204757/git-chmod-problem-checkout-screws-exec-bit
       subprocess.check_output(command.split())

       command = "git reset --hard"
       subprocess.check_output(command.split())

       command = "git pull"
       output = subprocess.check_output(command.split())
    
       # Go back to master (refactor is old):
       if checker is not None:
          if checker.status['remote_branch'] == 'origin/refactor':
             command = 'git checkout master'
             subprocess.check_output(command.split())

       log.debug(NAME, _(u'Update result') + ': ' + output)
       restart(3)

    except Exception:
       log.error(NAME, _(u'System update plug-in') + ':\n' + traceback.format_exc())


def start():
    global checker
    if checker is None:
        checker = StatusChecker()


def stop():
    global checker
    if checker is not None:
        checker.stop()
        checker.join()
        checker = None


################################################################################
# Web pages:                                                                   #
################################################################################
class status_page(ProtectedPage):
    """Load an html page rev data."""

    def GET(self):
        checker.started.wait(10)    # Make sure we are initialized
        return self.plugin_render.system_update(plugin_options, log.events(NAME), checker.status)

    def POST(self):
        plugin_options.web_update(web.input())
        if checker is not None:
            checker.update()

        raise web.seeother(plugin_url(status_page), True)


class refresh_page(ProtectedPage):
    """Refresh status and show it."""

    def GET(self):
        checker.update_wait()
        raise web.seeother(plugin_url(status_page), True)


class update_page(ProtectedPage):
    """Update OSPy from github and return text message from comm line."""

    def GET(self):
        perform_update()
        msg = _(u'OSPy is now updated from Github and restarted. Please wait...')
        return self.core_render.notice(home_page, msg)


class restart_page(ProtectedPage):
    """Restart system."""

    def GET(self):
        restart(3)
        msg = _(u'OSPy is now restarted (invoked by the user). Please wait...')
        return self.core_render.notice(plugin_url(status_page), msg)
