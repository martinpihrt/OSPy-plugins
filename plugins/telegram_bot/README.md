Telegram Bot Readme
====

This plugin lets OSPy send Telegram notifications and lets subscribed Telegram
chats run a small set of OSPy control commands.

The plugin uses the official Telegram Bot API directly. It does not install or
upgrade `python-telegram-bot`, because current versions of that library use a
new asynchronous API and older plugin code is not compatible with it.

It includes a `plugin.json` manifest and reports its worker, token presence,
connection, bot username, subscribed chat count, polling, received messages and
errors through the OSPy system health interface. Tokens and chat identifiers are
not included in diagnostics.

Setup
-----------

1. In Telegram, open `@BotFather` and send `/start`.
2. Create a bot with `/newbot`.
3. Copy the token from BotFather.
4. Paste the token into the OSPy Telegram Bot plugin.
5. Enable the plugin and submit the form.
6. Wait until the plugin shows the bot ID and username.
7. Open your bot chat and send `/subscribe BOT_ID`, where `BOT_ID` is the ID
   shown on the plugin page.

OSPy restart is not required after changing the token or enabling the plugin.

Plugin setup
-----------

* Enable Telegram Bot:
  Enables or disables the Telegram polling worker.

* Bot Token:
  Token from `@BotFather`.

* Your Bot ID:
  Telegram ID detected from the token. Use this ID as the subscribe access key.

* Bot username:
  Telegram username detected from the token.

* Subscribed chats:
  Telegram chats that can control OSPy and receive notifications.

* Zone Change:
  Send a message when station state changes.

* Help Command:
  Command for showing available commands.

* Info Command:
  Command for showing current station and scheduler state.

* Enable Command:
  Command for enabling the scheduler.

* Disable Command:
  Command for disabling the scheduler.

* RunOnce Command:
  Command for running a program by number, for example `/runOnce 1`.

* Stop Command:
  Command for stopping all stations and disabling the scheduler.

* Show in footer:
  Show Telegram Bot status in the OSPy footer.

Commands
-----------

* `/start`:
  Show the first setup message.

* `/subscribe BOT_ID`:
  Subscribe the current Telegram chat to OSPy.

* `/help`:
  Show available commands.

* `/info`:
  Show station and scheduler state.

* `/enable`:
  Enable the scheduler.

* `/disable`:
  Disable the scheduler.

* `/runOnce 1`:
  Run program number 1.

* `/stop`:
  Stop all stations and disable the scheduler.

## Example
[![](https://github.com/martinpihrt/OSPy-plugins/blob/master/plugins/telegram_bot/static/images/phone1.png?raw=true)](https://github.com/martinpihrt/OSPy-plugins/blob/master/plugins/telegram_bot/static/images/phone1.png)
[![](https://github.com/martinpihrt/OSPy-plugins/blob/master/plugins/telegram_bot/static/images/phone2.png?raw=true)](https://github.com/martinpihrt/OSPy-plugins/blob/master/plugins/telegram_bot/static/images/phone2.png)
