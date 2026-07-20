# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

from threading import Thread, Event, Lock
import time
import subprocess
import traceback
import json
import os
import re
import secrets
import shlex
import shutil
import socket
import sys
import zipfile
import web
from ospy.webpages import ProtectedPage, clear_plugin_runtime_data
from ospy.log import log, logEM, logEV
from plugins import PluginOptions, plugin_url, get_runtime
from ospy import version
from ospy.helpers import datetime_string, restart, verify_csrf
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
        'update_channel': 'stable',
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
WATCHDOG_DIR = os.path.join(PLUGIN_DIR, 'data')
WATCHDOG_STATE_FILE = os.path.join(WATCHDOG_DIR, 'update_watchdog.json')
WATCHDOG_ACK_FILE = os.path.join(WATCHDOG_DIR, 'update_watchdog.ack.json')
WATCHDOG_RESULT_FILE = os.path.join(WATCHDOG_DIR, 'update_watchdog_result.json')
WATCHDOG_READY_FILE = os.path.join(WATCHDOG_DIR, 'update_watchdog.ready.json')
WATCHDOG_SCRIPT = os.path.join(PLUGIN_DIR, 'update_watchdog.py')
WATCHDOG_SUPERVISOR = os.path.join(PLUGIN_DIR, 'update_watchdog_supervisor.sh')
WATCHDOG_TIMEOUT = 120
WATCHDOG_CONFIRM_DELAY = 20
WATCHDOG_START_TIMEOUT = 10
COMMIT_RE = re.compile(r'^[0-9a-fA-F]{40}$')
STABLE_TAG_RE = re.compile(r'^v\d+\.\d+\.\d+$')
runtime = get_runtime()
health_lock = Lock()
health_state = {
    'last_check': 0,
    'last_update': 0,
    'last_rollback': 0,
    'last_email': 0,
    'last_error': 0,
    'last_error_message': '',
    'watchdog_mode': '',
}

UPDATE_CHANNELS = {
    'stable': 'master',
    'beta': 'beta',
}


def selected_channel():
    channel = str(plugin_options.get('update_channel', 'stable')).lower()
    return channel if channel in UPDATE_CHANNELS else 'stable'


def selected_branch():
    return UPDATE_CHANNELS[selected_channel()]


def selected_remote_branch():
    return 'origin/{}'.format(selected_branch())


def current_commit():
    try:
        return git_output(['git', 'rev-parse', 'HEAD'])
    except Exception:
        return ''


def stable_release_info():
    """Return the newest verified stable release reachable from origin/master."""
    try:
        tags = git_output([
            'git', 'for-each-ref', 'refs/tags', '--sort=-version:refname',
            '--format=%(refname:short)'
        ]).splitlines()
    except Exception:
        return {}

    for tag in tags:
        tag = tag.strip()
        if not STABLE_TAG_RE.fullmatch(tag):
            continue
        try:
            if git_output(['git', 'cat-file', '-t', tag]) != 'tag':
                continue
            run_required_command([
                'git', 'merge-base', '--is-ancestor', '{}^{{commit}}'.format(tag),
                'origin/master'
            ])
            commit_hash = git_output(['git', 'rev-list', '-n', '1', tag])
            if not _valid_commit(commit_hash):
                continue
            release_date = git_output([
                'git', 'for-each-ref', 'refs/tags/{}'.format(tag),
                '--format=%(creatordate:short)'
            ])
            notes = git_output([
                'git', 'for-each-ref', 'refs/tags/{}'.format(tag),
                '--format=%(contents)'
            ])[:4000]
            return {
                'tag': tag,
                'commit': commit_hash,
                'date': release_date,
                'notes': notes,
            }
        except Exception:
            continue
    return {}


class StatusChecker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self.started = Event()
        self._stop_event = runtime.stop_event
        self._refresh_lock = Lock()
        self._refresh_thread = None

        self.status = {
            'ver_str': version.ver_str,
            'ver_date': version.ver_date,
            'remote': _('None!'),
            'channel': selected_channel(),
            'remote_branch': selected_remote_branch(),
            'can_update': False,
            'can_error': False,
            'can_ownership_error': False,
            'error_message': '',
            'checking': False,
            'commits': [],
            'local_hash': current_commit(),
            'target_hash': '',
            'stable_release': {},
        }
        self._sleep_time = 0
        self.start()
        runtime.register_thread(self)

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def stop(self):
        self._stop_event.set()

    def refresh_async(self):
        with self._refresh_lock:
            if self.status.get('checking'):
                return False

            if self._refresh_thread is not None and self._refresh_thread.is_alive():
                return False

            log.clear(NAME)
            self._refresh_thread = Thread(target=self._manual_refresh, daemon=True)
            self._refresh_thread.start()
            runtime.register_thread(self._refresh_thread)
            return True

    def _manual_refresh(self):
        try:
            self._update_rev_data()
        except Exception:
            with health_lock:
                health_state['last_error'] = time.time()
                health_state['last_error_message'] = traceback.format_exc().splitlines()[-1]
            log.error(NAME, _('System update plug-in') + ':\n' + traceback.format_exc())

    def _update_rev_data(self):
        global stats

        new_date = 0
        new_revision = 0
        changes = '' 
        self.status['checking'] = True

        try:
            run_required_command(['git', 'fetch', '--prune', '--tags', 'origin'], timeout=45)
            remote = git_output(['git', 'config', '--get', 'remote.origin.url'])
            if remote:
                self.status['remote'] = remote

            channel = selected_channel()
            remote_branch = selected_remote_branch()
            self.status['channel'] = channel
            self.status['remote_branch'] = remote_branch
            try:
                git_output(['git', 'rev-parse', '--verify', remote_branch])
            except Exception:
                raise RuntimeError(
                    _('The selected update channel branch was not found') + ': ' + remote_branch
                )

            remote_rev = int(git_output(['git', 'rev-list', remote_branch, '--count']))
            local_hash = git_output(['git', 'rev-parse', 'HEAD'])
            remote_hash = git_output(['git', 'rev-parse', remote_branch])
            self.status['can_update'] = remote_hash != local_hash

            # AktuĂˇlnĂ­ commit hash
            self.status['local_hash'] = local_hash
            self.status['target_hash'] = remote_hash
            self.status['stable_release'] = stable_release_info()

            command = 'git log -1 %s --format=%%cd --date=short' % remote_branch
            new_date = git_output(command.split())

            command = 'git rev-list %s --count --first-parent' % remote_branch
            new_revision = int(git_output(command.split()))

            command = 'git log HEAD..%s --oneline' % remote_branch
            changes = '  ' + '\n  '.join(git_output(command.split()).split('\n'))

            stats['ver_changes'] = ''

            # PoslednĂ­ch 10 commitĹŻ (hash|datum|message)
            commit_log = git_output(
                ['git', 'log', '-n', '10', '--pretty=format:%H|%cd|%s', '--date=short']
            ).splitlines()

            commits = []
            for line in commit_log:
                parts = line.split('|', 2)
                if len(parts) == 3:
                    commits.append({
                        'hash': parts[0],
                        'short_hash': parts[0][:8],
                        'date': parts[1],
                        'message': parts[2]
                    })
            self.status['commits'] = commits
            self.status['can_error'] = False
            self.status['can_ownership_error'] = False
            self.status['error_message'] = ''
            with health_lock:
                health_state['last_check'] = time.time()

        except Exception:
            error_message = traceback.format_exc().splitlines()[-1]
            with health_lock:
                health_state['last_error'] = time.time()
                health_state['last_error_message'] = error_message
            log.error(NAME, _('Error while updating revision data:\n') + traceback.format_exc())
            self.status['can_update'] = False
            stats['can_update'] = False
            self.status['can_error'] = True
            self.status['can_ownership_error'] = 'dubious ownership' in error_message.lower()
            self.status['error_message'] = error_message
            self.status['checking'] = False
            self.started.set()
            return

        if not self.status['can_update']:
            log.info(NAME, _('Up-to-date.'))
            stats['can_update'] = False
        else:
            log.info(NAME, _('New version is available!'))
            log.info(NAME, _('Update channel') + ': {} ({})'.format(selected_channel(), selected_branch()))
            log.info(NAME, _('Currently running revision') + ': %d.%d.%d (%s)' % (version.major_ver, version.minor_ver, (version.revision - version.old_count), version.ver_date))
            log.info(NAME, _('Available revision') + ': %d.%d.%d (%s)' % (version.major_ver, version.minor_ver, new_revision - version.old_count, new_date))
            log.info(NAME, _('Changes') +':\n' + changes)
            stats['ver_changes'] = changes
            msg = '<b>' + _('System update plug-in') + '</b> ' + '<br><p style="color:red;">' 
            msg += _('New OSPy version is available!') + '<br>' 
            msg += _('Update channel') + ': {} ({})'.format(selected_channel(), selected_branch()) + '<br>'
            msg += _('Currently running revision') + ': %d.%d.%d (%s)' % (version.major_ver, version.minor_ver, (version.revision - version.old_count), version.ver_date) + '<br>'
            msg += _('Available revision') + ': %d.%d.%d (%s)' % (version.major_ver, version.minor_ver, new_revision - version.old_count, new_date) + '.' + '</p>'
            msglog =   _('System update plug-in') + ': '
            msglog +=  _('New OSPy version is available!') + '-> ' + _('Currently running revision') + ': %d.%d.%d (%s)' % (version.major_ver, version.minor_ver, (version.revision - version.old_count), version.ver_date) + ', '
            msglog += _('Update channel') + ': {} ({}), '.format(selected_channel(), selected_branch())
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
                        with health_lock:
                            health_state['last_email'] = time.time()
                except Exception:
                    log.error(NAME, _('System update plug-in') + ':\n' + traceback.format_exc()) 

            stats['ver_new'] =  '%d.%d.%d (%s)' % (version.major_ver, version.minor_ver, new_revision - version.old_count, new_date) 
            stats['ver_new_date'] = '%s' % new_date   
            stats['ver_act'] =  '%d.%d.%d (%s)' % (version.major_ver, version.minor_ver, (version.revision - version.old_count), version.ver_date)
            stats['can_update'] = True

        self.status['checking'] = False
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
                        msg = _('New OSPy version is available!') + ' [{} / {}]'.format(selected_channel(), selected_branch())
                        stats['can_update'] = True 
                        report_ospyupdate()
                    else:
                        msg = _('Up-to-date') + ' [{} / {}]'.format(selected_channel(), selected_branch())
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
                with health_lock:
                    health_state['last_error'] = time.time()
                    health_state['last_error_message'] = traceback.format_exc().splitlines()[-1]
                log.error(NAME, _('System update plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)


checker = None

################################################################################
# Helper functions:                                                            #
################################################################################
def git_output(args, timeout=30):
    return subprocess.check_output(args, stderr=subprocess.STDOUT, timeout=timeout).decode('utf-8').strip()


def run_command(cmd, timeout=60):
    try:
        args = shlex.split(cmd) if isinstance(cmd, str) else cmd
        proc = subprocess.run(args, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, timeout=timeout)
        output = proc.stdout.decode('utf-8')
        log.info(NAME, output)
        return output.strip()
    except Exception:
        log.error(NAME, _('System update plug-in') + ':\n' + traceback.format_exc())
        return ''


def run_required_command(cmd, timeout=60):
    args = shlex.split(cmd) if isinstance(cmd, str) else cmd
    output = subprocess.check_output(args, stderr=subprocess.STDOUT, timeout=timeout).decode('utf-8')
    if output.strip():
        log.info(NAME, output.strip())
    return output.strip()


def _read_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as source:
            value = json.load(source)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as target:
        json.dump(value, target, indent=2, sort_keys=True)
        target.flush()
        os.fsync(target.fileno())
    os.replace(temporary, path)


def _valid_commit(commit_hash):
    return COMMIT_RE.fullmatch(str(commit_hash or '')) is not None


def _watchdog_state(previous_commit, target_commit):
    if not _valid_commit(previous_commit) or not _valid_commit(target_commit):
        raise RuntimeError(_('The update watchdog received an invalid commit identifier.'))
    repository = git_output(['git', 'rev-parse', '--show-toplevel'])
    previous_branch = git_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    token = secrets.token_hex(32)
    unit = 'ospy-update-watchdog-{}'.format(int(time.time()))
    state = {
        'schema_version': 1,
        'token': token,
        'repository': os.path.abspath(repository),
        'python': sys.executable,
        'previous_commit': previous_commit,
        'previous_branch': previous_branch if previous_branch != 'HEAD' else '',
        'target_commit': target_commit,
        'created': time.time(),
        'deadline': time.time() + WATCHDOG_TIMEOUT,
        'acknowledgement': WATCHDOG_ACK_FILE,
        'result': WATCHDOG_RESULT_FILE,
        'ready': WATCHDOG_READY_FILE,
        'unit': unit,
    }
    for path in (WATCHDOG_ACK_FILE, WATCHDOG_READY_FILE, WATCHDOG_STATE_FILE):
        try:
            os.remove(path)
        except OSError:
            pass
    _write_json(WATCHDOG_STATE_FILE, state)
    return state


def arm_update_watchdog(previous_commit, target_commit):
    """Start a monitor outside ospy.service before changing tracked files."""
    state = _watchdog_state(previous_commit, target_commit)
    systemd_run = shutil.which('systemd-run')
    systemctl = shutil.which('systemctl')
    shell = shutil.which('sh')
    helper_command = [sys.executable, WATCHDOG_SCRIPT]
    if shell and os.path.isfile(WATCHDOG_SUPERVISOR):
        # The legacy SysV OSPy stop script used to kill every process whose
        # executable was /usr/bin/python3.  Keep a non-Python supervisor as
        # the transient unit's main process so it can relaunch the helper if
        # that broad cleanup is still installed on an existing controller.
        helper_command = [
            shell, WATCHDOG_SUPERVISOR, sys.executable, WATCHDOG_SCRIPT,
        ]
    helper_command.extend([
        '--state', WATCHDOG_STATE_FILE,
        '--token', state['token'],
    ])
    process = None
    mode = ''
    try:
        if systemd_run and systemctl and os.path.isdir('/run/systemd/system'):
            command = [
                systemd_run,
                '--quiet',
                '--collect',
                '--unit={}'.format(state['unit']),
                '--property=Type=exec',
            ] + helper_command
            try:
                run_required_command(command, timeout=15)
                mode = 'systemd'
            except Exception:
                # Older systemd versions may not support --collect or Type=exec.
                command = [
                    systemd_run,
                    '--quiet',
                    '--unit={}'.format(state['unit']),
                ] + helper_command
                run_required_command(command, timeout=15)
                mode = 'systemd'
        else:
            process = subprocess.Popen(
                helper_command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
            time.sleep(0.2)
            if process.poll() is not None:
                raise RuntimeError(_('The external update watchdog could not be started.'))
            mode = 'process'

        ready_deadline = time.time() + WATCHDOG_START_TIMEOUT
        while time.time() < ready_deadline:
            ready = _read_json(WATCHDOG_READY_FILE)
            if ready.get('token') == state['token']:
                break
            if process is not None and process.poll() is not None:
                raise RuntimeError(_('The external update watchdog could not be started.'))
            time.sleep(0.1)
        else:
            raise RuntimeError(_('The external update watchdog could not be started.'))
    except Exception:
        if mode == 'systemd' and systemctl:
            try:
                run_command([systemctl, 'stop', state['unit']], timeout=5)
            except Exception:
                pass
        elif process is not None:
            try:
                process.terminate()
            except Exception:
                pass
        for path in (WATCHDOG_READY_FILE, WATCHDOG_STATE_FILE):
            try:
                os.remove(path)
            except OSError:
                pass
        raise
    state['mode'] = mode
    _write_json(WATCHDOG_STATE_FILE, state)
    with health_lock:
        health_state['watchdog_mode'] = mode
    log.info(NAME, _('External update watchdog armed.') + ' ({})'.format(mode))
    return state


def acknowledge_update_watchdog():
    """Confirm a pending update only after the new process is healthy."""
    state = _read_json(WATCHDOG_STATE_FILE)
    if not state:
        return False
    target = state.get('target_commit', '')
    token = state.get('token', '')
    if not _valid_commit(target) or not token:
        return False
    if git_output(['git', 'rev-parse', 'HEAD']) != target:
        return False
    from ospy import health as core_health
    scheduler_health = core_health.component('scheduler')
    if scheduler_health.get('last_success', 0) <= state.get('created', 0):
        return False
    bind_address = str(options.HTTP_web_ip or '0.0.0.0')
    if bind_address == '0.0.0.0':
        bind_address = '127.0.0.1'
    elif bind_address == '::':
        bind_address = '::1'
    try:
        connection = socket.create_connection((bind_address, int(options.web_port)), timeout=2)
        connection.close()
    except OSError:
        return False
    _write_json(WATCHDOG_ACK_FILE, {
        'token': token,
        'status': 'confirmed',
        'time': time.time(),
        'commit': target,
    })
    _write_json(WATCHDOG_RESULT_FILE, {
        'status': 'confirmed',
        'time': time.time(),
        'previous_commit': state.get('previous_commit', ''),
        'target_commit': target,
    })
    # The external helper already loaded the state before OSPy was restarted.
    # Removing the pending marker here prevents a stale warning if the helper's
    # final file cleanup is delayed or interrupted.  Its acknowledgement stays
    # available so the helper can still observe it and exit without rollback.
    for path in (WATCHDOG_READY_FILE, WATCHDOG_STATE_FILE):
        try:
            os.remove(path)
        except OSError:
            pass
    log.info(NAME, _('Updated OSPy start confirmed; automatic rollback cancelled.'))
    return True


def _confirm_pending_update():
    # The old process exits immediately because no state existed at its start.
    if not _read_json(WATCHDOG_STATE_FILE):
        return
    if runtime.stop_event.wait(WATCHDOG_CONFIRM_DELAY):
        return
    while not runtime.stop_event.is_set():
        state = _read_json(WATCHDOG_STATE_FILE)
        if not state or time.time() >= float(state.get('deadline', 0)) - 10:
            return
        try:
            if acknowledge_update_watchdog():
                return
        except Exception:
            with health_lock:
                health_state['last_error'] = time.time()
                health_state['last_error_message'] = traceback.format_exc().splitlines()[-1]
            log.error(NAME, _('Update watchdog confirmation error:\n') + traceback.format_exc())
            return
        if runtime.stop_event.wait(2):
            return


def cancel_update_watchdog(state, status='cancelled'):
    if not state:
        return
    _write_json(WATCHDOG_ACK_FILE, {
        'token': state.get('token', ''),
        'status': status,
        'time': time.time(),
    })


def create_update_safety_backup(reason='before system update'):
    """Use the new verified backup engine, with a legacy bridge for older OSPy."""
    try:
        from ospy.backup import create_system_backup
    except ImportError:
        data_dir = os.path.abspath(os.path.join('ospy', 'data'))
        backup_dir = os.path.abspath(os.path.join('ospy', 'backup'))
        os.makedirs(backup_dir, exist_ok=True)
        destination = os.path.join(
            backup_dir,
            'ospy_pre_update_{}.zip'.format(time.strftime('%Y-%m-%d_%H-%M-%S'))
        )
        temporary = destination + '.tmp'
        try:
            with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                for current, dirs, files in os.walk(data_dir):
                    dirs[:] = [name for name in dirs if name != '__pycache__']
                    for name in files:
                        path = os.path.join(current, name)
                        if os.path.islink(path) or not os.path.isfile(path):
                            continue
                        archive.write(path, os.path.relpath(path, data_dir))
            with zipfile.ZipFile(temporary, 'r') as archive:
                if not archive.namelist() or archive.testzip() is not None:
                    raise RuntimeError(_('The safety backup could not be verified.'))
            os.replace(temporary, destination)
            return destination
        except Exception:
            if os.path.exists(temporary):
                os.remove(temporary)
            raise
    return create_system_backup(reason=reason)

def perform_update():
    watchdog = None
    previous_commit = ''
    try:
        channel = selected_channel()
        branch = selected_branch()
        remote_branch = selected_remote_branch()
        run_required_command(['git', 'config', 'core.filemode', 'false'])
        run_required_command(['git', 'fetch', '--prune', 'origin'], timeout=120)
        target_commit = git_output(['git', 'rev-parse', '--verify', remote_branch])
        previous_commit = git_output(['git', 'rev-parse', 'HEAD'])
        from ospy.options import options as current_options
        current_options.save_now()
        safety_backup = create_update_safety_backup()
        log.info(NAME, _('Safety backup created before update') + ': ' + os.path.basename(safety_backup))

        # UloĹľĂ­me aktuĂˇlnĂ­ commit pro pĹ™Ă­pad rollbacku
        with open(ROLLBACK_FILE, 'w') as f:
            f.write(previous_commit)
        watchdog = arm_update_watchdog(previous_commit, target_commit)

        run_required_command(['git', 'reset', '--hard'], timeout=120)
        run_required_command(['git', 'checkout', '-B', branch, remote_branch], timeout=120)
        run_required_command(['git', 'reset', '--hard', remote_branch], timeout=120)
        with health_lock:
            health_state['last_update'] = time.time()

        msg = _('OSPy updated successfully. Please wait while restarting...') + ' ' + \
              _('Update channel') + ': {} ({}).'.format(channel, branch)
        log.info(NAME, msg)

        if options.run_logEV:
            logEV.save_events_log(
                _('System OSPy'),
                _('Updated to version') + ': {}. '.format(str(stats['ver_new'])) +
                _('Update channel') + ': {} ({})'.format(channel, branch),
                id='SystemUpdate', level='success', category='system'
            )

        # SpustĂ­me restart v pozadĂ­, aby se hlĂˇĹˇka stihla zobrazit
        def delayed_restart():
            time.sleep(4)  # ÄŤas na zobrazenĂ­ hlĂˇĹˇky
            restart(wait=0)  # okamĹľitĂ˝ restart po zpoĹľdÄ›nĂ­

        Thread(target=delayed_restart, daemon=True).start()

        return msg  # pokud volĂˇĹˇ z webu, mĹŻĹľeĹˇ tuto hlĂˇĹˇku zobrazit

    except Exception:
        if previous_commit and _valid_commit(previous_commit):
            try:
                run_required_command(['git', 'reset', '--hard', previous_commit], timeout=120)
                previous_branch = (watchdog or {}).get('previous_branch', '')
                if previous_branch:
                    run_required_command(
                        ['git', 'checkout', '-B', previous_branch, previous_commit],
                        timeout=120
                    )
            except Exception:
                log.error(NAME, _('Immediate update recovery failed:\n') + traceback.format_exc())
        cancel_update_watchdog(watchdog, status='update_failed')
        log.error(NAME, _('Update error:\n') + traceback.format_exc())
        return _('Update failed!')


def perform_rollback_selected(commit_hash, target_branch=None, target_label=''):
    watchdog = None
    previous_commit = ''
    try:
        if not _valid_commit(commit_hash):
            log.error(NAME, _('No commit hash provided for rollback.'))
            return False
        run_required_command(['git', 'cat-file', '-e', '{}^{{commit}}'.format(commit_hash)])
        previous_commit = git_output(['git', 'rev-parse', 'HEAD'])
        from ospy.options import options as current_options
        current_options.save_now()
        safety_backup = create_update_safety_backup(reason='before system rollback')
        log.info(NAME, _('Safety backup created before rollback') + ': ' + os.path.basename(safety_backup))
        with open(ROLLBACK_FILE, 'w') as rollback_file:
            rollback_file.write(previous_commit)
        watchdog = arm_update_watchdog(previous_commit, commit_hash)
        run_required_command(['git', 'reset', '--hard', commit_hash], timeout=120)
        if target_branch:
            run_required_command(
                ['git', 'checkout', '-B', target_branch, commit_hash], timeout=120
            )
            run_required_command(['git', 'reset', '--hard', commit_hash], timeout=120)
        with health_lock:
            health_state['last_rollback'] = time.time()
        destination = '{} ({})'.format(target_label, commit_hash) if target_label else commit_hash
        log.info(NAME, _('Rolled back to commit: ') + destination)
        return True
    except Exception:
        if previous_commit and _valid_commit(previous_commit):
            try:
                run_required_command(['git', 'reset', '--hard', previous_commit], timeout=120)
                previous_branch = (watchdog or {}).get('previous_branch', '')
                if previous_branch:
                    run_required_command(
                        ['git', 'checkout', '-B', previous_branch, previous_commit],
                        timeout=120
                    )
            except Exception:
                log.error(NAME, _('Immediate rollback recovery failed:\n') + traceback.format_exc())
        cancel_update_watchdog(watchdog, status='rollback_failed')
        log.error(NAME, _('Rollback error:\n') + traceback.format_exc())
        return False


def start():
    global checker
    if checker is None:
        checker = StatusChecker()
        confirmation = Thread(target=_confirm_pending_update, daemon=True)
        confirmation.start()
        runtime.register_thread(confirmation)


def stop():
    global checker
    if checker is not None:
        checker.stop()
        runtime.request_stop()
        checker.join(15)
        refresh_thread = checker._refresh_thread
        if refresh_thread is not None and refresh_thread.is_alive():
            refresh_thread.join(15)
        if not checker.is_alive() and (refresh_thread is None or not refresh_thread.is_alive()):
            checker = None
    clear_plugin_runtime_data('system_update')

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
        qdict = web.input()
        if 'refresh' in qdict:
            verify_csrf(qdict)
            checker.refresh_async()
        else:
            checker.started.wait(1)
        return self.plugin_render.system_update(plugin_options, log.events(NAME), checker.status)

    def POST(self):
        qdict = web.input()
        verify_csrf(qdict)
        requested_channel = str(qdict.get('update_channel', 'stable')).lower()
        qdict['update_channel'] = requested_channel if requested_channel in UPDATE_CHANNELS else 'stable'
        plugin_options.web_update(qdict)
        checker.status['channel'] = selected_channel()
        checker.status['remote_branch'] = selected_remote_branch()
        checker.status['can_update'] = False
        checker.refresh_async()
        raise web.seeother(plugin_url(status_page), True)


class status_json(ProtectedPage):
    """Returns live System Update status in JSON format."""

    def GET(self):
        qdict = web.input()
        if 'refresh' in qdict:
            verify_csrf(qdict)
            checker.refresh_async()

        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps({
                'status': checker.status,
                'events': log.events(NAME)
            })
        except Exception:
            log.error(NAME, _('System update plug-in') + ':\n' + traceback.format_exc())
            return json.dumps({
                'status': {},
                'events': []
            })


class update_page(ProtectedPage):
    def GET(self):
        verify_csrf()
        # SpustĂ­me aktualizaci a zĂ­skĂˇme hlĂˇĹˇku
        msg = perform_update()  # vracĂ­ text hlĂˇĹˇky

        # ZobrazĂ­me strĂˇnku s hlĂˇĹˇkou, restart probÄ›hne pozdÄ›ji v pozadĂ­
        return self.core_render.notice('/', msg)


class rollback_select_page(ProtectedPage):
    def POST(self):
        data = web.input(commit_hash=None)
        verify_csrf(data)
        commit_hash = data.get('commit_hash')

        # Nejprve ovÄ›Ĺ™, Ĺľe je co vracet
        if not commit_hash:
            log.error(NAME, _('No commit hash provided for rollback.'))
            msg = _('No commit selected for rollback.')
            return self.core_render.notice('/', msg)

        # ZobrazĂ­me hlĂˇĹˇku ihned, restart zpozdĂ­me v pozadĂ­
        msg = _('OSPy rollback to selected version completed. Please wait...')
        log.info(NAME, msg)

        # SpustĂ­me rollback a restart s krĂˇtkĂ˝m zpoĹľdÄ›nĂ­m
        def do_rollback_and_restart():
            try:
                if not perform_rollback_selected(commit_hash):
                    return
                time.sleep(3)  # 3 sekundy na zobrazenĂ­ hlĂˇĹˇky
                restart(wait=0)  # okamĹľitĂ˝ restart po zpoĹľdÄ›nĂ­
            except Exception:
                log.error(NAME, _('Rollback thread error:\n') + traceback.format_exc())

        Thread(target=do_rollback_and_restart, daemon=True).start()

        # VrĂˇtĂ­me HTML strĂˇnku s hlĂˇĹˇkou
        return self.core_render.notice('/', msg)


class rollback_stable_page(ProtectedPage):
    def POST(self):
        data = web.input()
        verify_csrf(data)
        try:
            run_required_command(['git', 'fetch', '--prune', '--tags', 'origin'], timeout=45)
            release = stable_release_info()
        except Exception:
            release = {}
        if not release:
            log.error(NAME, _('No verified stable release is available.'))
            return self.core_render.notice('/', _('No verified stable release is available.'))

        msg = _('OSPy rollback to the last stable release has started. Please wait...')
        log.info(NAME, msg)

        def do_stable_rollback_and_restart():
            try:
                if perform_rollback_selected(
                        release['commit'], target_branch='master', target_label=release['tag']):
                    time.sleep(3)
                    restart(wait=0)
            except Exception:
                log.error(NAME, _('Rollback thread error:\n') + traceback.format_exc())

        Thread(target=do_stable_rollback_and_restart, daemon=True).start()
        return self.core_render.notice('/', msg)


class help_page(ProtectedPage):
    def GET(self):
        return self.plugin_render.system_update_help()


class restart_page(ProtectedPage):
    def GET(self):
        verify_csrf()
        msg = _('OSPy is now restarted. Please wait...')
        report_restarted()
        
        # SpustĂ­me restart v pozadĂ­, aby se hlĂˇĹˇka stihla zobrazit
        def delayed_restart():
            import time
            from ospy.helpers import restart
            time.sleep(3)  # ÄŤas na pĹ™eÄŤtenĂ­ hlĂˇĹˇky
            restart(wait=0)  # okamĹľitĂ˝ restart po zpoĹľdÄ›nĂ­

        from threading import Thread
        Thread(target=delayed_restart, daemon=True).start()

        # ZobrazĂ­me strĂˇnku s hlĂˇĹˇkou
        return self.core_render.notice('/', msg)


class error_page(ProtectedPage):
    """Error page."""    
    def GET(self):
        verify_csrf()
        msg = _('OSPy is now restarted (invoked by the user). Please wait...')
        report_restarted()
        
        command = "git config --system --add safe.directory '*'"
        run_command(command)

        # SpustĂ­me restart v pozadĂ­, aby se hlĂˇĹˇka stihla zobrazit
        def delayed_restart():
            import time
            from ospy.helpers import restart
            time.sleep(4)  # ÄŤas na pĹ™eÄŤtenĂ­ hlĂˇĹˇky
            restart(wait=0)  # okamĹľitĂ˝ restart po zpoĹľdÄ›nĂ­

        from threading import Thread
        Thread(target=delayed_restart, daemon=True).start()

        # ZobrazĂ­me strĂˇnku s hlĂˇĹˇkou
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


def health():
    """Return a compact status for the OSPy diagnostics page."""
    worker_alive = checker is not None and checker.is_alive()
    checker_status = checker.status if checker is not None else {}
    with health_lock:
        state = dict(health_state)
    watchdog_pending = _read_json(WATCHDOG_STATE_FILE)
    watchdog_ack = _read_json(WATCHDOG_ACK_FILE)
    watchdog_result = _read_json(WATCHDOG_RESULT_FILE)
    watchdog_confirmed = bool(
        watchdog_pending
        and watchdog_ack.get('token') == watchdog_pending.get('token')
        and watchdog_ack.get('status') == 'confirmed'
    )
    watchdog_waiting = bool(watchdog_pending) and not watchdog_confirmed
    watchdog_result_status = watchdog_result.get('status', '')
    watchdog_result_label = (
        _('Success') if watchdog_confirmed or watchdog_result_status == 'confirmed'
        else watchdog_result_status or _('None')
    )
    channel_label = _('Stable') if selected_channel() == 'stable' else _('Test')
    details = {
        'worker': _('Running') if worker_alive else _('Stopped'),
        'enabled': bool(plugin_options.get('use_update', False)),
        'automatic_update': bool(plugin_options.get('auto_update', False)),
        'checking': bool(checker_status.get('checking', False)),
        'update_available': bool(checker_status.get('can_update', False)),
        'current_version': version.ver_str,
        'current_commit': checker_status.get('local_hash', '') or current_commit(),
        'target_commit': checker_status.get('target_hash', ''),
        'stable_release': checker_status.get('stable_release', {}).get('tag', ''),
        'upstream_branch': checker_status.get('remote_branch', ''),
        _('Update channel'): '{} ({})'.format(channel_label, selected_branch()),
        'last_check': state['last_check'],
        'last_update': state['last_update'],
        'last_rollback': state['last_rollback'],
        'last_email': state['last_email'],
        'last_error': state['last_error'],
        _('Update watchdog'): (
            _('Success') if watchdog_confirmed else
            _('Waiting for healthy start') if watchdog_waiting else
            state.get('watchdog_mode') or _('Inactive')
        ),
        _('Last watchdog result'): watchdog_result_label,
    }
    if state['last_error_message']:
        details['error'] = state['last_error_message']
    if watchdog_result.get('status') == 'rollback_failed':
        status = 'error'
        summary = _('Automatic rollback after a failed update did not complete.')
        if watchdog_result.get('error'):
            details['error'] = watchdog_result['error']
    elif watchdog_waiting:
        status = 'warning'
        summary = _('The update watchdog is waiting for a healthy OSPy start.')
    elif not worker_alive:
        status = 'error'
        summary = _('System Update worker is not running.')
    elif not plugin_options.get('use_update', False):
        status = 'unknown'
        summary = _('System Update checks are disabled.')
    elif checker_status.get('can_error', False):
        status = 'error'
        summary = _('System Update could not check the repository.')
    elif checker_status.get('checking', False):
        status = 'unknown'
        summary = _('System Update is checking the repository.')
    elif checker_status.get('can_update', False):
        status = 'warning'
        summary = _('A different OSPy revision is available in the selected update channel.')
    else:
        status = 'ok'
        summary = _('OSPy is up to date.') + ' {} ({})'.format(channel_label, selected_branch())
    return {'status': status, 'summary': summary, 'details': details}
