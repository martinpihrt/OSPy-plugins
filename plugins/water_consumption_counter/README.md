Water Consumption Counter Readme
====

Tested in Python 3+

This plugin read Water consumption on master station or second master station.  
Total sum is the calculated as run of the main (or second) station per second. This is not an actual flow meter (physical flow sensor).
Used for an overview of water consumption.

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