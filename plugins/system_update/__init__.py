# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

from threading import Thread, Event, Condition
import time
import subprocess
import traceback
import json
import os
import web
from ospy.webpages import ProtectedPage
from ospy.log import log, logEM, logEV
from plugins import PluginOptions, plugin_url
from ospy import version
from ospy.helpers import datetime_string, restart
from ospy.webpages import showInFooter
from ospy.options import options
from blinker import signal

NAME = 'System Update'
MENU = _('Package: System Update')
LINK = 'status_page'

plugin_options = PluginOptions(
    NAME,
    {
        'auto_update': False,
        'use_update': False,
        'use_eml': False,
        'eml_subject': _('Report from OSPy SYSTEM UPDATE plugin'),
        'use_footer': False,
        'eplug': 0, # email plugin type (email notifications or email notifications SSL)
    }
)

stats = {
    'ver_act': '0.0.0',
    'ver_new': '0.0.0',
    'can_update': False,
    'ver_new_date': '',
    'ver_changes': ''
}

PLUGIN_DIR = os.path.dirname(__file__)
ROLLBACK_FILE = os.path.join(PLUGIN_DIR, 'rollback_commit.txt')


class StatusChecker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self.started = Event()
        self._stop_event = Event()

        self.status = {
            'ver_str': version.ver_str,
            'ver_date': version.ver_date,
            'remote': _('None!'),
            'remote_branch': 'origin/master',
            'can_update': False,
            'can_error': False,
            'commits': [],
            'local_hash': ''
        }
        self._sleep_time = 0
        self.start()

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def stop(self):
        self._stop_event.set()

    def _update_rev_data(self):
        global stats

        new_date = 0
        new_revision = 0
        changes = '' 

        try:
            run_command('git remote update')
            remote = subprocess.check_output(['git', 'config', '--get', 'remote.origin.url']).decode().strip()
            if remote:
                self.status['remote'] = remote

            remote_branch = subprocess.check_output(
                ['git', 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}']
            ).decode().strip()
            if remote_branch:
                self.status['remote_branch'] = remote_branch

            local_rev = int(subprocess.check_output(['git', 'rev-list', 'HEAD', '--count']).decode())
            remote_rev = int(subprocess.check_output(['git', 'rev-list', remote_branch, '--count']).decode())
            self.status['can_update'] = remote_rev > local_rev

            # Aktuální commit hash
            self.status['local_hash'] = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()

            command = 'git log -1 %s --format=%%cd --date=short' % remote_branch
            new_date = subprocess.check_output(command.split()).decode('utf-8').strip()

            command = 'git rev-list %s --count --first-parent' % remote_branch
            new_revision = int(subprocess.check_output(command.split()).decode('utf8'))

            command = 'git log HEAD..%s --oneline' % remote_branch
            changes = '  ' + '\n  '.join(subprocess.check_output(command.split()).decode('utf8').split('\n'))

            stats['ver_changes'] = ''

            # Posledních 10 commitů (hash|datum|message)
            commit_log = subprocess.check_output(
                ['git', 'log', '-n', '10', '--pretty=format:%h|%cd|%s', '--date=short']
            ).decode('utf-8').splitlines()

            commits = []
            for line in commit_log:
                parts = line.split('|', 2)
                if len(parts) == 3:
                    commits.append({
                        'hash': parts[0],
                        'date': parts[1],
                        'message': parts[2]
                    })
            self.status['commits'] = commits
            self.status['can_error'] = False

        except Exception:
            log.error(NAME, _('Error while updating revision data:\n') + traceback.format_exc())
            self.status['can_error'] = True

        if new_revision == version.revision and new_date == version.ver_date:
            log.info(NAME, _('Up-to-date.'))
        elif new_revision > version.revision:
            log.info(NAME, _('New version is available!'))
            log.info(NAME, _('Currently running revision') + ': %d.%d.%d (%s)' % (version.major_ver, version.minor_ver, (version.revision - version.old_count), version.ver_date))
            log.info(NAME, _('Available revision') + ': %d.%d.%d (%s)' % (version.major_ver, version.minor_ver, new_revision - version.old_count, new_date))
            log.info(NAME, _('Changes') +':\n' + changes)
            stats['ver_changes'] = changes
            msg = '<b>' + _('System update plug-in') + '</b> ' + '<br><p style="color:red;">' 
            msg += _('New OSPy version is available!') + '<br>' 
            msg += _('Currently running revision') + ': %d.%d.%d (%s)' % (version.major_ver, version.minor_ver, (version.revision - version.old_count), version.ver_date) + '<br>'
            msg += _('Available revision') + ': %d.%d.%d (%s)' % (version.major_ver, version.minor_ver, new_revision - version.old_count, new_date) + '.' + '</p>'
            msglog =   _('System update plug-in') + ': '
            msglog +=  _('New OSPy version is available!') + '-> ' + _('Currently running revision') + ': %d.%d.%d (%s)' % (version.major_ver, version.minor_ver, (version.revision - version.old_count), version.ver_date) + ', '
            msglog +=  _('Available revision') + ': %d.%d.%d (%s)' % (version.major_ver, version.minor_ver, new_revision - version.old_count, new_date) + '.'
               
            if plugin_options['use_eml']:
                try:
                    try_mail = None
                    if plugin_options['eplug']==0: # email_notifications
                        from plugins.email_notifications import try_mail
                    if plugin_options['eplug']==1: # email_notifications SSL
                        from plugins.email_notifications_ssl import try_mail
                    if try_mail is not None:
                        try_mail(msg, msglog, attachment=None, subject=plugin_options['eml_subject']) # try_mail(text, logtext, attachment=None, subject=None)
                except Exception:
                    log.error(NAME, _('System update plug-in') + ':\n' + traceback.format_exc()) 

            stats['ver_new'] =  '%d.%d.%d (%s)' % (version.major_ver, version.minor_ver, new_revision - version.old_count, new_date) 
            stats['ver_new_date'] = '%s' % new_date   
            stats['ver_act'] =  '%d.%d.%d (%s)' % (version.major_ver, version.minor_ver, (version.revision - version.old_count), version.ver_date)

        else:
            log.info(NAME, _('Running unknown version!'))
            log.info(NAME, _('Currently running revision') + ': %d (%s)' % (version.revision, version.ver_date))
            log.info(NAME, _('Available revision') + ': %d (%s)' % (new_revision, new_date))

        self.started.set()

    def run(self):
        global stats
        temp_upd = None

        if plugin_options['use_footer']:
            temp_upd = showInFooter()                                  #  instantiate class to enable data in footer
            temp_upd.button = "system_update/status"                   # button redirect on footer
            temp_upd.label =  _('System Update')                       # label on footer
            msg = _('Waiting to state')
            temp_upd.val = msg.encode('utf8').decode('utf8')           # value on footer

        while not self._stop_event.is_set():
            try:
                if plugin_options['use_update']:
                    log.clear(NAME)
                    self._update_rev_data()
                        
                    if self.status['can_update']:
                        msg =_('New OSPy version is available!')
                        stats['can_update'] = True 
                        report_ospyupdate()
                    else:
                        msg =_('Up-to-date')
                        stats['can_update'] = False    

                    if self.status['can_update'] and plugin_options['auto_update']:
                        perform_update()
                else:
                    msg =_('Plugin is not enabled')

                if plugin_options['use_footer']:
                    if temp_upd is not None:
                        temp_upd.val = msg.encode('utf8').decode('utf8')  # value on footer  
                    else:
                        log.error(NAME, _('Error: restart this plugin! Show in homepage footer have enabled.'))

                self._sleep(3600)

            except Exception:
                self.started.set()
                log.error(NAME, _('System update plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)


checker = None

################################################################################
# Helper functions:                                                            #
################################################################################
def run_command(cmd):
    try:
        proc = subprocess.Popen(cmd, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, shell=True)
        output = proc.communicate()[0].decode('utf-8')
        log.info(NAME, output)
        return output.strip()
    except Exception:
        log.error(NAME, _('System update plug-in') + ':\n' + traceback.format_exc())
        return ''

def perform_update():
    try:
        # Uložíme aktuální commit pro případ rollbacku
        commit_hash = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
        with open(ROLLBACK_FILE, 'w') as f:
            f.write(commit_hash)

        run_command("git config core.filemode false")
        run_command("git reset --hard")
        run_command("git pull")

        msg = _('OSPy updated successfully. Please wait while restarting...')
        log.info(NAME, msg)

        if options.run_logEV:
            logEV.save_events_log( _('System OSPy'), _('Updated to version') + ': {}'.format(str(stats['ver_new'])))        

        # Spustíme restart v pozadí, aby se hláška stihla zobrazit
        def delayed_restart():
            time.sleep(4)  # čas na zobrazení hlášky
            restart(wait=0)  # okamžitý restart po zpoždění

        Thread(target=delayed_restart, daemon=True).start()

        return msg  # pokud voláš z webu, můžeš tuto hlášku zobrazit

    except Exception:
        log.error(NAME, _('Update error:\n') + traceback.format_exc())
        return _('Update failed!')


def perform_rollback_selected(commit_hash):
    try:
        if not commit_hash:
            log.error(NAME, _('No commit hash provided for rollback.'))
            return
        run_command(f'git reset --hard {commit_hash}')
        log.info(NAME, _('Rolled back to commit: ') + commit_hash)
        restart(wait=4)
    except Exception:
        log.error(NAME, _('Rollback error:\n') + traceback.format_exc())


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

def get_all_values():
    global stats
    plg_state = 0 # 0= Plugin is not enabled, 1= Up-to-date, 2= New OSPy version is available  
    try:
        if stats['can_update'] and plugin_options['use_update']: 
            plg_state = 2
        elif not stats['can_update'] and plugin_options['use_update']:
            plg_state = 1
        else:
            plg_state = 0
        return plg_state, stats['ver_new'], stats['ver_act'], stats['ver_changes'] # state, new version, actual version, 'ver changes
    except:
        log.error(NAME, _('Get all values error:\n') + traceback.format_exc())
        return plg_state, 0, 0, "error"                                            # state, new version, actual version, 'ver changes


restarted = signal('restarted')
def report_restarted():
    restarted.send()

ospyupdate = signal('ospyupdate')
def report_ospyupdate():
    ospyupdate.send() 


################################################################################
# Web pages:                                                                   #
################################################################################
class status_page(ProtectedPage):
    def GET(self):
        checker.started.wait(10)
        return self.plugin_render.system_update(plugin_options, log.events(NAME), checker.status)

    def POST(self):
        plugin_options.web_update(web.input())
        raise web.seeother(plugin_url(status_page), True)


class update_page(ProtectedPage):
    def GET(self):
        # Spustíme aktualizaci a získáme hlášku
        msg = perform_update()  # vrací text hlášky

        # Zobrazíme stránku s hláškou, restart proběhne později v pozadí
        return self.core_render.notice('/', msg)


class rollback_select_page(ProtectedPage):
    def POST(self):
        data = web.input(commit_hash=None)
        commit_hash = data.get('commit_hash')

        # Nejprve ověř, že je co vracet
        if not commit_hash:
            log.error(NAME, _('No commit hash provided for rollback.'))
            msg = _('No commit selected for rollback.')
            return self.core_render.notice('/', msg)

        # Zobrazíme hlášku ihned, restart zpozdíme v pozadí
        msg = _('OSPy rollback to selected version completed. Please wait...')
        log.info(NAME, msg)

        # Spustíme rollback a restart s krátkým zpožděním
        def do_rollback_and_restart():
            try:
                perform_rollback_selected(commit_hash)
                time.sleep(3)  # 3 sekundy na zobrazení hlášky
                restart(wait=0)  # okamžitý restart po zpoždění
            except Exception:
                log.error(NAME, _('Rollback thread error:\n') + traceback.format_exc())

        Thread(target=do_rollback_and_restart, daemon=True).start()

        # Vrátíme HTML stránku s hláškou
        return self.core_render.notice('/', msg)


class help_page(ProtectedPage):
    def GET(self):
        return self.plugin_render.system_update_help()


class restart_page(ProtectedPage):
    def GET(self):
        msg = _('OSPy is now restarted. Please wait...')
        report_restarted()
        
        # Spustíme restart v pozadí, aby se hláška stihla zobrazit
        def delayed_restart():
            import time
            from ospy.helpers import restart
            time.sleep(3)  # čas na přečtení hlášky
            restart(wait=0)  # okamžitý restart po zpoždění

        from threading import Thread
        Thread(target=delayed_restart, daemon=True).start()

        # Zobrazíme stránku s hláškou
        return self.core_render.notice('/', msg)


class error_page(ProtectedPage):
    """Error page."""    
    def GET(self):
        msg = _('OSPy is now restarted (invoked by the user). Please wait...')
        report_restarted()
        
        command = "git config --system --add safe.directory '*'"
        run_command(command)

        # Spustíme restart v pozadí, aby se hláška stihla zobrazit
        def delayed_restart():
            import time
            from ospy.helpers import restart
            time.sleep(4)  # čas na přečtení hlášky
            restart(wait=0)  # okamžitý restart po zpoždění

        from threading import Thread
        Thread(target=delayed_restart, daemon=True).start()

        # Zobrazíme stránku s hláškou
        return self.core_render.notice('/', msg)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(plugin_options)
        except:
            return {}


class test_page(ProtectedPage):
    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data = get_all_values()
        try:
            return json.dumps(data)
        except:
            return {}