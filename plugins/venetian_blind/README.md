Venetian Blind Readme
====

Tested in Python 3+

The plug-in includes a `plugin.json` manifest and reports its worker, configured and reachable blinds, latest status update, command and errors through the OSPy system health interface.

This plugin can be used to control blinds and shutters through an API and a hardware module such as a Shelly relay. The blind motor is connected to a Shelly relay or a similar device with separate outputs for the up and down directions. The relay supports control through its local REST or RPC API and can also measure consumption.

Plugin setup
-----------

Blinds are managed individually through Add blind, Edit and confirmed Delete actions, with a saved card or list view. Existing count-based settings migrate automatically to the Custom REST profile without changing labels, open, stop, close or status URLs, or the labels for positions 0 and 100 percent.

Each blind can use Shelly Gen1, Shelly Gen2 and newer, or Custom REST URLs. Gen1 uses `/status`, `/roller/0?go=open|close|stop` and `to_pos`; Gen2+ uses `Cover.GetStatus`, `Cover.Open`, `Cover.Close`, `Cover.Stop` and `Cover.GoToPosition`. Four independently named tilt positions have configurable percentages and optional custom URLs. The reported Shelly position is classified as closed, tilt 1–4, open or an intermediate position.

Temperature shading selects one OSPy temperature sensor, a threshold with hysteresis, a permitted time window and multiple programs that lower the blinds. Lowering is allowed only after the configured number of consecutive Wind Monitor readings is below the safe limit. Strong-wind protection is active all day, uses its own confirmation count and can run multiple raising programs. Selected programs run sequentially because OSPy has one Run-Now slot, and strong-wind protection cancels pending lowering actions before it raises the blinds. A state latch and the position read from Shelly prevent repeated commands while a condition remains active.

The plug-in observes active OSPy programs selected for raising and lowering. Programs started manually or through an ESP32 Multi Contact therefore update the temporary desired direction, while the next valid Shelly position remains the authoritative state.

* Check Use Control: Enables or disables the plugin.

* Check Enable logging: Enables or disables logging.

* Show in footer: Shows plugin data in the footer on the home page.

* Label for blind: Names the blind for better identification.

* Command for open blind: Defines a custom command such as `http://192.168.88.213/roller/0?go=open`.

* Command for stop blind: Defines a custom command such as `http://192.168.88.213/roller/0?go=stop`.

* Command for close blind: Defines a custom command such as `http://192.168.88.213/roller/0?go=close`.

* Command for read status: Defines a custom status address such as `http://192.168.88.213/status`.

