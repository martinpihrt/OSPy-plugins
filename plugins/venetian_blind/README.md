Venetian Blind Readme
====

Tested in Python 3+

The plug-in includes a `plugin.json` manifest and reports its worker, configured and reachable blinds, latest status update, command and errors through the OSPy system health interface.

This plugin can be used to control blinds and shutters through an API and a hardware module such as a Shelly relay. The blind motor is connected to a Shelly relay or a similar device with separate outputs for the up and down directions. The relay supports control through its local REST or RPC API and can also measure consumption.

Plugin setup
-----------

Blinds are managed individually through Add blind, Edit and confirmed Delete actions, with a saved card or list view. Existing count-based settings migrate automatically to the Custom REST profile without changing labels, open, stop, close or status URLs, or the labels for positions 0 and 100 percent.

Boolean settings use the same accessible red and green sliding switches as other OSPy plug-ins without changing the saved option names or their compatibility with existing configurations.

Each blind can use Shelly Gen1, Shelly Gen2 and newer, or Custom REST URLs. Gen1 uses `/status`, `/roller/0?go=open|close|stop` and `to_pos`; Gen2+ uses `Cover.GetStatus`, `Cover.Open`, `Cover.Close`, `Cover.Stop` and `Cover.GoToPosition`. Four independently named tilt positions have configurable percentages and optional custom URLs. The reported Shelly position is classified as closed, tilt 1–4, open or an intermediate position.

Temperature shading reads the selected OSPy sensor from its actual `last_read_value` channel, compares it directly with the configured limit and operates only inside the permitted time window. Lowering is allowed only after the configured number of consecutive, fresh and unique Wind Monitor measurements is below the safe limit. No temperature hysteresis is required because the reported blind positions and one-action-per-condition guard prevent repeated relay commands.

Strong-wind protection is active all day and starts after the configured number of unique accepted Wind Monitor measurements reaches or exceeds the wind limit inside the configured minute interval, for example two exceedances during five minutes. It does not reuse the same cached measurement. If at least one enabled blind is closed, tilted, between positions or unreachable, the selected raising programs run; only a confirmed open state from every enabled blind suppresses the action. Pending lowering actions are cancelled first.

For temperature shading, only a confirmed closed state from every enabled blind suppresses the selected lowering programs. A mixed state such as eight closed blinds and one open blind therefore starts lowering when the temperature, wind and time conditions are met. An unreachable blind also makes the aggregate state unconfirmed. Each continuous condition produces at most one action while movement is incomplete, but after every blind reaches the requested state a later position change can trigger the appropriate action again.

The plug-in observes active OSPy programs selected for raising and lowering. Programs started manually or through an ESP32 Multi Contact therefore suppress a duplicate automatic start while they are active, while the next valid Shelly position remains the authoritative state.

* Check Use Control: Enables or disables the plugin.

* Check Enable logging: Enables or disables logging.

* Show in footer: Shows plugin data in the footer on the home page.

* Label for blind: Names the blind for better identification.

* Command for open blind: Defines a custom command such as `http://192.168.88.213/roller/0?go=open`.

* Command for stop blind: Defines a custom command such as `http://192.168.88.213/roller/0?go=stop`.

* Command for close blind: Defines a custom command such as `http://192.168.88.213/roller/0?go=close`.

* Command for read status: Defines a custom status address such as `http://192.168.88.213/status`.

