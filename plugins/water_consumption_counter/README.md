Water Consumption Counter Readme
====

Tested in Python 3+

This plugin read Water consumption on master station or second master station.  
Total sum is the calculated as run of the main (or second) station per second. This is not an actual flow meter (physical flow sensor).
Used for an overview of water consumption.

The plug-in includes a manifest for compatibility and permission checks, keeps its master-station signal subscriptions in the shared OSPy lifecycle, disconnects them during shutdown, and reports counters, events and e-mail state through the Diagnostics health interface.

Version 1.1.0 adds a responsive status dashboard and live Home timeline values. An active main or second main station shows the total estimated consumption since the last counter reset, including the current run. Every active ordinary station configured to use that master shows only the estimated consumption of its current run and the applicable configured flow. A station without an assigned master does not display an estimated value. Home updates the values automatically; **Options > System > Show plug-ins on home** must be enabled.

Plugin setup
-----------

* Liter/sec master:  
  The amount of water per second for the main station.

* Liter/sec second master:  
  The amount of water per second for the second main station.

* Last counter reset:  
  The measured value for the main and sub main stations is measured from that time.

* Check Send email:
  If checked send email notification plugin sends e-mail water consumption.  
  For this function required e-mail notification plugin with all setup in plugin.      

* Button for counter reset:
  The button deletes the total measured consumption values.

The calculation remains an estimate based on configured liters per second and running time. It does not read or verify a physical water meter.
