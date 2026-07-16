Relay Test Readme
====
Tested in Python 3+

Example plugin to demonstrate OSPY on-board relay.  
The plug-in switches the relay on for 3 seconds and then switches it off.

The plug-in includes an OSPy `plugin.json` manifest, registers its test worker
with the shared plug-in runtime, and implements `health()`. Diagnostics reports
the worker state, physical relay command state, and test duration.


The hardware should be connected as follows:
<a href="/plugins/relay/static/images/schematics.png"><img src="/plugins/relay/static/images/schematics.png" width="100%"></a>


Example use relay test plugin:  
Control Your garage door from OSPy webpages.
