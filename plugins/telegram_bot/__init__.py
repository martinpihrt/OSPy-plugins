# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'

import asyncio
import html
import json
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from threading import Thread, Event

import web

from blinker import signal

from ospy.log import log
from plugins import PluginOptions, plugin_url
from ospy.webpages import ProtectedPage
from ospy.helpers import verify_csrf
from ospy.options import options
from ospy.stations import stations
from ospy.runonce import run_once
from ospy.programs import programs
from ospy.webpages import showInFooter


NAME = 'Telegram Bot'
MENU =  _(u'Package: Telegram Bot')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {'use_plugin': False,
     'botToken': '',
     'botID': '',
     'botUsername': '',
     'botFirstName': '',
     'zoneChange': False,
     'help_cmd': _('help'),
     'info_cmd': _('info'),
     'enable_cmd': _('enable'),
     'disable_cmd': _('disable'),
     'runOnce_cmd': _('runOnce'),
     'stop_cmd': _('stop'),
     'currentChats': [],
     'lastChatDate': [],
     'lastUpdateID': 0,
     'use_footer': True
     }
)


class TelegramApi(object):
    """Small async wrapper around Telegram Bot API.

    OSPy does not need the full python-telegram-bot dependency here.  The direct
    Bot API keeps this plug-in stable across python-telegram-bot breaking changes.
    """

    API_ROOT = 'https://api.telegram.org/bot{}'

    def __init__(self, token):
        self.token = token.strip()

    async def get_me(self):
        return await self._request('getMe')

    async def get_updates(self, offset=None, timeout=10):
        params = {'timeout': int(timeout), 'allowed_updates': json.dumps(['message'])}
        if offset:
            params['offset'] = int(offset)
        return await self._request('getUpdates', params)

    async def send_message(self, chat_id, text, parse_mode=None):
        if text is None:
            text = ''
        params = {'chat_id': chat_id, 'text': str(text)[:4096]}
        if parse_mode:
            params['parse_mode'] = parse_mode
        return await self._request('sendMessage', params)

    async def _request(self, method, params=None):
        return await asyncio.to_thread(self._request_sync, method, params or {})

    def _request_sync(self, method, params):
        url = '{}/{}'.format(self.API_ROOT.format(self.token), method)
        data = urllib.parse.urlencode(params).encode('utf-8')
        request = urllib.request.Request(url, data=data, method='POST')
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode('utf-8'))

        if not payload.get('ok'):
            description = payload.get('description', _('Unknown Telegram error'))
            raise RuntimeError(description)
        return payload.get('result')


################################################################################
# Main function loop:                                                          #
################################################################################


class Sender(Thread):

    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()
        self._currentChats = []
        self._sleep_time = 0
        self._api = None
        self._token = ''
        self._footer = None
        self._zone_connected = False
        self._loop = None
        self._last_station_states = self._station_states()
        self.start()

    def stop(self):
        self._stop_event.set()
        self.update()

    def update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    async def _async_sleep(self, secs):
        end_time = time.time() + secs
        while time.time() < end_time and not self._stop_event.is_set():
            await asyncio.sleep(0.5)

    def _footer_text(self, text):
        if plugin_options['use_footer']:
            if self._footer is None:
                self._footer = showInFooter()
                self._footer.button = "telegram_bot/settings"
                self._footer.label = _(u'Telegram Bot')
            self._footer.val = text.encode('utf8').decode('utf8')

    def _authorized(self, chat_id):
        return str(chat_id) in [str(chat) for chat in plugin_options['currentChats']]

    def _command_name(self, value):
        value = str(value or '').strip().lstrip('/')
        return value.split('@', 1)[0].lower()

    def _command_matches(self, command, configured):
        return self._command_name(command) == self._command_name(configured)

    async def _send(self, chat_id, text, parse_mode=None):
        if self._api is not None:
            await self._api.send_message(chat_id, text, parse_mode=parse_mode)

    async def _announce(self, text, parse_mode=None):
        if self._api is None:
            return

        for chat_id in list(plugin_options['currentChats']):
            try:
                await self._api.send_message(chat_id, text, parse_mode=parse_mode)
            except Exception:
                log.error(NAME, _(u'Cannot send Telegram message to chat {}.').format(chat_id))

    def _station_states(self):
        return {station.index: bool(station.active) for station in stations.get()}

    def _station_state_text(self, station):
        if station.active:
            if station.remaining_seconds == -1:
                return _(u'ON') + u' (' + _(u'Forever') + u')'
            return _(u'ON') + u' (' + u'{}'.format(str(int(station.remaining_seconds))) + u')'
        return _(u'OFF')

    def _format_station_line(self, station, changed=False):
        name = html.escape(station.name)
        state = html.escape(self._station_state_text(station))
        if changed:
            return u'>> <b>{}</b>: <b>{}</b>'.format(name, state)
        if station.active:
            return u'ON  <b>{}</b>: {}'.format(name, state)
        return u'OFF {}: {}'.format(name, state)

    def zone_change_message(self):
        previous_states = self._last_station_states
        current_states = self._station_states()
        self._last_station_states = current_states

        station_list = list(stations.get())
        changed_stations = [
            station for station in station_list
            if station.index in previous_states and previous_states[station.index] != current_states.get(station.index)
        ]

        txt = u'<b>{}</b>\n'.format(html.escape(_('There has been a Station Change.')))
        if changed_stations:
            txt += u'\n<b>{}</b>\n'.format(html.escape(_('Changed')))
            for station in changed_stations:
                txt += self._format_station_line(station, changed=True) + u'\n'

        txt += u'\n<b>{}</b>\n'.format(html.escape(_('All stations')))
        changed_indexes = set([station.index for station in changed_stations])
        for station in station_list:
            txt += self._format_station_line(station, changed=station.index in changed_indexes) + u'\n'
        return txt

    async def _bot_cmd_start(self, chat_id):
        await self._send(chat_id, _(u'Hi! I am a Bot to interface with {}.\nSend /{} for commands. To subscribe, send /subscribe {}.').format(
            options.name,
            plugin_options['help_cmd'],
            plugin_options['botID']
        ))

    async def _bot_cmd_subscribe(self, chat_id, access_key):
        expected_key = str(plugin_options['botID'])
        if expected_key and str(access_key).strip() == expected_key:
            chats = list(plugin_options['currentChats'])
            if str(chat_id) not in [str(chat) for chat in chats]:
                chats.append(chat_id)
                plugin_options['currentChats'] = chats
                txt = _(u'Hi! you are now added to the {} announcement.').format(options.name)
            else:
                txt = _(u'You are already subscribed to {} announcements.').format(options.name)
            log.info(NAME, txt)
        else:
            txt = _(u'Sorry, please enter the correct AccessKey!')
            log.info(NAME, txt)
        await self._send(chat_id, txt)

    async def _bot_cmd_help(self, chat_id):
        txt = _(u'Help: /{}\nInfo Command: /{}\nEnable Command: /{}\nDisable Command: /{}\nStop Command: /{}\nRun Once Command: /{} 1\nSubscribe: /subscribe {}').format(
            plugin_options['help_cmd'],
            plugin_options['info_cmd'],
            plugin_options['enable_cmd'],
            plugin_options['disable_cmd'],
            plugin_options['stop_cmd'],
            plugin_options['runOnce_cmd'],
            plugin_options['botID']
        )
        if not self._authorized(chat_id):
            txt += '\n' + _(u'Control commands work after subscription.')
        await self._send(chat_id, txt)

    async def _bot_cmd_info(self, chat_id):
        if self._authorized(chat_id):
            txt = _(u'Info from {}\n').format(options.name)
            for station in stations.get():
                txt += _(u'Station: {} State: ').format(station.name)
                if station.active:
                    txt += _(u'ON') + u' ('
                    if station.remaining_seconds == -1:
                        txt += _(u'Forever') + u')'
                    else:
                        txt += _(u'{}').format(str(int(station.remaining_seconds))) + u')'
                else:
                    txt += _(u'OFF')
                txt += '\n'
            txt += _(u'Scheduler is {}.\n').format(_(u'enabled') if options.scheduler_enabled else _(u'disabled'))
        else:
            txt = _(u'Sorry I can not do that.')
        await self._send(chat_id, txt)

    async def _bot_cmd_enable(self, chat_id):
        if self._authorized(chat_id):
            txt = _(u'{} System - scheduler ON.').format(options.name)
            options.scheduler_enabled = True
        else:
            txt = _(u'Sorry I can not do that.')
        await self._send(chat_id, txt)

    async def _bot_cmd_disable(self, chat_id):
        if self._authorized(chat_id):
            txt = _(u'{} System - scheduler OFF.').format(options.name)
            options.scheduler_enabled = False
        else:
            txt = _(u'Sorry I can not do that.')
        await self._send(chat_id, txt)

    async def _bot_cmd_stop(self, chat_id):
        if self._authorized(chat_id):
            txt = _(u'{} System - scheduler OFF. All stations OFF.').format(options.name)
            programs.run_now_program = None
            run_once.clear()
            log.finish_run(None)
            stations.clear()
        else:
            txt = _(u'Sorry I can not do that.')
        await self._send(chat_id, txt)

    async def _bot_cmd_run_once(self, chat_id, argument):
        if not self._authorized(chat_id):
            await self._send(chat_id, _(u'Sorry I can not do that.'))
            return

        try:
            program_number = int(argument)
        except (TypeError, ValueError):
            await self._send(chat_id, _(u'Please enter a program number, for example /{} 1.').format(plugin_options['runOnce_cmd']))
            return

        for program in programs.get():
            if program.index == program_number - 1:
                options.manual_mode = False
                log.finish_run(None)
                stations.clear()
                programs.run_now(program.index)
                await self._send(chat_id, _(u'{} RunOnce: program {}.').format(options.name, program_number))
                return

        await self._send(chat_id, _(u'Program {} was not found.').format(program_number))

    async def _handle_message(self, update):
        message = update.get('message') or {}
        chat = message.get('chat') or {}
        chat_id = chat.get('id')
        text = str(message.get('text') or '').strip()
        if not chat_id or not text:
            return

        msg_id = message.get('message_id')
        first_name = chat.get('first_name') or ''
        last_name = chat.get('last_name') or ''
        msg_from = '{} {}'.format(first_name, last_name).strip()

        log.clear(NAME)
        log.info(NAME, _(u'New message: {} ID: {}.').format(text, msg_id))
        log.info(NAME, _(u'From: {} ID: {}.').format(msg_from, chat_id))

        parts = text.split()
        command = parts[0]
        command_name = self._command_name(command)
        argument = parts[1] if len(parts) > 1 else ''
        run_once_command = self._command_name(plugin_options['runOnce_cmd'])
        if run_once_command and not argument and command_name.startswith(run_once_command) and command_name != run_once_command:
            argument = command_name[len(run_once_command):]

        if command_name == 'start':
            await self._bot_cmd_start(chat_id)
            temp_text = _('Last msg: /start')
        elif command_name == 'subscribe':
            await self._bot_cmd_subscribe(chat_id, argument)
            temp_text = _('Last msg: /subscribe')
        elif command_name == self._command_name(plugin_options['botID']):
            await self._bot_cmd_subscribe(chat_id, plugin_options['botID'])
            temp_text = _('Last msg: /subscribe')
        elif self._command_matches(command, plugin_options['help_cmd']):
            await self._bot_cmd_help(chat_id)
            temp_text = _('Last msg: /{}').format(plugin_options['help_cmd'])
        elif self._command_matches(command, plugin_options['info_cmd']):
            await self._bot_cmd_info(chat_id)
            temp_text = _('Last msg: /{}').format(plugin_options['info_cmd'])
        elif self._command_matches(command, plugin_options['enable_cmd']):
            await self._bot_cmd_enable(chat_id)
            temp_text = _('Last msg: /{}').format(plugin_options['enable_cmd'])
        elif self._command_matches(command, plugin_options['disable_cmd']):
            await self._bot_cmd_disable(chat_id)
            temp_text = _('Last msg: /{}').format(plugin_options['disable_cmd'])
        elif self._command_matches(command, plugin_options['stop_cmd']):
            await self._bot_cmd_stop(chat_id)
            temp_text = _('Last msg: /{}').format(plugin_options['stop_cmd'])
        elif self._command_matches(command, plugin_options['runOnce_cmd']) or (run_once_command and command_name.startswith(run_once_command)):
            await self._bot_cmd_run_once(chat_id, argument)
            temp_text = _('Last msg: /{} arg: {}').format(plugin_options['runOnce_cmd'], argument)
        else:
            txt = _('Sorry command "{}" is not supported! Send /{} for help.').format(text, plugin_options['help_cmd'])
            await self._send(chat_id, txt)
            temp_text = txt

        log.info(NAME, temp_text)
        self._footer_text(temp_text)

    async def _connect(self):
        self._api = TelegramApi(plugin_options['botToken'])
        getbot = await self._api.get_me()
        plugin_options['botID'] = getbot.get('id', '')
        plugin_options['botUsername'] = getbot.get('username', '')
        plugin_options['botFirstName'] = getbot.get('first_name', '')
        self._currentChats = list(plugin_options['currentChats'])

        log.clear(NAME)
        log.info(NAME, _(u'Hi connect is OK my ID: {}, User Name: {}, First Name: {}.').format(
            plugin_options['botID'],
            plugin_options['botUsername'],
            plugin_options['botFirstName']
        ))
        self._footer_text(_(u'Hi connect is OK my Name: {}.').format(plugin_options['botUsername']))
        await self._announce(_(u'Bot on {} has just started!').format(options.name))

    async def _poll(self):
        last_update_id = int(plugin_options.get('lastUpdateID', 0) or 0)
        updates = await self._api.get_updates(offset=last_update_id + 1 if last_update_id else None)
        for update in updates:
            update_id = int(update.get('update_id', 0) or 0)
            if update_id:
                plugin_options['lastUpdateID'] = update_id
            await self._handle_message(update)

    async def _main(self):
        if not self._zone_connected:
            signal('zone_change').connect(notify_zone_change)
            self._zone_connected = True

        while not self._stop_event.is_set():
            if not plugin_options['use_plugin']:
                self._api = None
                self._footer_text(_(u'Telegram Bot is disabled.'))
                await self._async_sleep(5)
                continue

            if not str(plugin_options['botToken']).strip():
                self._api = None
                self._footer_text(_(u'Telegram Bot is waiting for token.'))
                await self._async_sleep(5)
                continue

            try:
                token = str(plugin_options['botToken']).strip()
                if self._api is None or token != self._token:
                    self._token = token
                    await self._connect()

                await self._poll()
            except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                txt = _(u'Telegram Bot has connection error: {}').format(exc)
                log.error(NAME, txt)
                self._footer_text(_(u'Telegram Bot has error, check in plugin status!'))
                self._api = None
                await self._async_sleep(30)
            except Exception:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                err_string = u"".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
                log.error(NAME, _(u'Telegram Bot plug-in') + ':\n' + err_string)
                self._footer_text(_(u'Telegram Bot has error, check in plugin status!'))
                self._api = None
                await self._async_sleep(30)

    def run(self):
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main())
        finally:
            self._loop = None
            loop.close()


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
       sender.join(15)
       sender = None


def notify_zone_change(name, **kw):
    if plugin_options['zoneChange'] and sender is not None:
        if sender._api is not None and sender._loop is not None:
            txt = sender.zone_change_message()
            asyncio.run_coroutine_threadsafe(sender._announce(txt, parse_mode='HTML'), sender._loop)


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments and deleting logs"""

    def GET(self):
        return self.plugin_render.telegram_bot(plugin_options, log.events(NAME))

    def POST(self):
        global sender
        qdict = web.input()
        verify_csrf(qdict)
        plugin_options.web_update(qdict)

        if sender is not None:
            sender.update()
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.telegram_bot_help()


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data = dict(plugin_options)
        data['botToken'] = ''
        data['events'] = log.events(NAME)
        return json.dumps(data)
