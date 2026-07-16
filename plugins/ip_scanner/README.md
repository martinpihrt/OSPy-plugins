IP Scanner Readme
====

Tested in Python 3+

This plugin prints all available network devices on same range as OSPy.

The scanner shows the OSPy IP address, network interface, local network range,
gateway and a table of discovered devices. Each device can include IP address,
MAC address, hostname, vendor hint, ARP state and notes such as Gateway,
This OSPy or Sensor candidate.

The optional Check common web ports setting checks ports 80, 443, 8080 and 8081
for discovered devices.

The plug-in includes an OSPy `plugin.json` manifest, registers its scanning
worker with the shared plug-in runtime, uses the common stop signal, and
implements `health()`. A stop request is propagated into queued host checks so
only the currently running, timeout-bounded commands need to finish.
Diagnostics reports worker and scan state, network interface and range, last
completed scan, device count, optional port checking, and the latest error.
