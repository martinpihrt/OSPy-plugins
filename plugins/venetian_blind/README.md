Venetian Blind Readme
====

Tested in Python 3+

Version 1.2.4 implements `ospy.provider.v1` and exposes every enabled blind as a cached resource with explicit open, stop, close and tilt 1–4 actions for Automation Rules. The actions reuse the same validated command path as Mobile API v1.

The plug-in includes a `plugin.json` manifest and reports its worker, configured and reachable blinds, latest status update, command and errors through the OSPy system health interface. Mobile API v1 exposes one native status card for every configured blind, including its current state, position, connection and Shelly profile. It also declares bounded open, stop, close and tilt actions for clients that support per-card manual controls.

This plugin can be used to control blinds and shutters through an API and a hardware module such as a Shelly relay. The blind motor is connected to a Shelly relay or a similar device with separate outputs for the up and down directions. The relay supports control through its local REST or RPC API and can also measure consumption.

Plugin setup
-----------

Blinds are managed individually through Add blind, Edit and confirmed Delete actions, with a saved card or list view.

The complete structured blind list is stored directly in OSPy `PluginOptions`; the plug-in does not create a separate configuration JSON file. The selected Gen1/Gen2/Custom profile, host, labels and all four tilt percentages, labels and custom URLs therefore remain persistent after a restart, update or live plug-in replacement. The only plug-in-owned JSON file is the optional operating log.

Boolean settings use the same accessible red and green sliding switches as other OSPy plug-ins without changing the saved option names or their compatibility with existing configurations.

Each blind can use Shelly Gen1, Shelly Gen2 and newer, or Custom REST URLs. Gen1 uses `/status`, `/roller/0?go=open|close|stop` and `to_pos`; Gen2+ uses `Cover.GetStatus`, `Cover.Open`, `Cover.Close`, `Cover.Stop` and `Cover.GoToPosition`. Four independently named tilt positions have configurable percentages and optional custom URLs. The reported Shelly position is classified as closed, tilt 1–4, open or an intermediate position.

Testing a saved command keeps the same blind editor open so several directions and tilt positions can be checked without reopening the blind after every command.

Temperature shading reads the selected OSPy sensor from its actual `last_read_value` channel, compares it directly with the configured limit and operates only inside the permitted time window. Lowering is allowed only after the configured number of consecutive, fresh and unique Wind Monitor measurements is below the safe limit. It is armed only by a transition in which every enabled blind is confirmed fully open.

Strong-wind protection is active all day and starts after the configured number of unique accepted Wind Monitor measurements reaches or exceeds the wind limit inside the configured minute interval, for example two exceedances during five minutes. It does not reuse the same cached measurement. If at least one enabled blind is closed, tilted, between positions or unreachable, the selected raising programs run; only a confirmed open state from every enabled blind suppresses the action. Pending lowering actions are cancelled first.

One automatic lowering action consumes the armed state. Manually tilting, closing or moving a blind to an intermediate position therefore does not cause another lowering action while the temperature condition remains true. Shading is rearmed only after every enabled blind is confirmed fully open again, whether the blinds were raised by strong-wind protection or manually. This both preserves a deliberate manual tilt and allows a later manual full opening to start a new shading cycle.

The plug-in observes active OSPy programs selected for raising and lowering. Programs started manually or through an ESP32 Multi Contact therefore suppress a duplicate automatic start while they are active, while the next valid Shelly position remains the authoritative state.

OSPy retains the last Run-Now program object after its final interval has ended. The plug-in checks the real final interval deadline, releases that completed object and continues its own queue. Temperature shading and strong-wind protection can consequently alternate repeatedly without restarting OSPy.

* Check Use Control: Enables or disables the plugin.

* Check Enable logging: Enables or disables logging.

* Show in footer: Shows plugin data in the footer on the home page.

* Label for blind: Names the blind for better identification.

* Command for open blind: Defines a custom command such as `http://192.168.88.213/roller/0?go=open`.

* Command for stop blind: Defines a custom command such as `http://192.168.88.213/roller/0?go=stop`.

* Command for close blind: Defines a custom command such as `http://192.168.88.213/roller/0?go=close`.

* Command for read status: Defines a custom status address such as `http://192.168.88.213/status`.

