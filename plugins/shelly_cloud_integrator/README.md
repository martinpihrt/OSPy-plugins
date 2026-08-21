Shelly Cloud Integration Readme
====

Tested in Python 3+

The plug-in includes a `plugin.json` manifest and reports its worker, Shelly server, configured, loaded and online devices, retry state, latest request and errors through the OSPy system health interface. The cloud authorization key is not included in diagnostics or the settings JSON endpoint.

How to get the latest device status via Shelly Cloud API and curl. Path: https://server_uri/device/status.
Supported methods: GET and POST.
Parameters are supplied via query or request body
Required data to send the request:
Target device ID: key = "id"
account authentication key: key = "auth_key"
The result is a JSON object with the device status.
The server URL where all the devices and client accounts are located. This can be obtained from Shelly > User Settings > Cloud Authorization Key.

Plugin setup
-----------

The settings page manages devices individually instead of asking for a sensor count. Add new Shelly opens a new-device editor, Edit changes only the selected configuration and Delete removes only that configuration after confirmation without deleting the physical Shelly device or its cloud account. Existing parallel-list settings remain the persisted compatibility format, and migration adds stable internal identifiers while preserving device order, enabled state, labels, Shelly IDs, types, generation, reading source, local addresses and add-on labels.

The device overview can be displayed as a compact list or responsive cards. The selected view is saved in the plug-in settings and does not alter measurements, cached data or integrations that identify devices by Shelly ID.

The internal Shelly device service exposes snapshots of both cached readings and configured device identities. Dependent plug-ins can therefore distinguish a missing or disabled device from an enabled device that is still waiting for its first reading. Reading the service before the worker starts safely returns an empty cache.

Shelly 2.5 reports its shared voltage consistently in roller and switch modes over both cloud and local connections. Status output uses that value directly and no longer references a channel-specific variable that is not provided by Shelly 2.5. Local switch mode reads its IP address and RSSI from the standard `wifi` object. Shelly 2PM Add-on and Shelly 1PM Add-on status lines display both the actual RSSI and update timestamp in their correct fields.

The add and edit form, compact list and responsive cards show a local preview image for every supported device type. Selecting a different device type or generation updates the editor preview immediately, and selecting an image opens the matching official Shelly Knowledge Base page in a new tab. Preview files are stored locally with the plug-in, so the settings page does not depend on loading images from an external server.

* Server uri:  
  The server URL where all the devices and client accounts are located. This can be obtained from Shelly > User Settings > Cloud Authorization Key.

* Auth key: 
  This can be obtained from Shelly > User Settings > Cloud Authorization Key.

* Request interval:
  Shelly cloud data download recovery interval.

* Use sensor: 
  If you do not want to use the sensor but do not want to delete it in the list, uncheck the box.

* Label for Shelly sensor:  
  Your Shelly designation (Shelly will be available in the OSPy system under this designation).

* Shelly sensor ID:  
  Unique ID number to identify Shelly devices. It can be found in the Shelly device settings or on the Shelly manufacturer's cloud site: https://control.shelly.cloud after logging in, click on the desired device and the "device information" section.

* Shelly sensor type:
  Shelly Plus HT, Shelly Plus Plug S, Shelly Pro 2PM, Shelly Pro 3EM and Shelly 3EM-63T Gen3. The three-phase meters expose power, reverse power, voltage, current, power factor and accumulated energy for every phase, including total power and total energy for use by other OSPy plug-ins.

* Status:  
  Status window from the plugin.

Shelly API:
* https://shelly-api-docs.shelly.cloud/gen1/
* https://shelly-api-docs.shelly.cloud/gen2/


