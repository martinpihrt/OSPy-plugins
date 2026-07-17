System update from GitHub Readme
====

Tested in Python 3+

This plugin compares the local copy with the remote repository and can automatically update the local copy.  
The default **Stable** update channel follows the tested `master` branch. The optional **Test** channel follows `beta` and receives changes immediately, so it may contain defects. The selected channel is displayed in the plug-in status and Diagnostics and is used by both manual and automatic updates. Switching back to Stable explicitly returns OSPy to `master`.
The repository owner must create and maintain the remote `beta` branch. If it does not exist, the check fails visibly and no update or branch change is performed.
Before installing an update, the plug-in creates a verified OSPy system safety backup. If that backup cannot be created, the update is not started.
For check new version OSPy click on update status button.  
If new version is posible click on update OSPy button. Plugin downloading and installing new version OSPy. Next restarting OSPy service.  
This plugin allows update itself automatically the system, while allowing send an E-mail to the system administrator.

The plug-in includes a manifest declaring repository-network, Git subprocess, OSPy-file, restart and e-mail access, uses the shared OSPy lifecycle for its checker and manual refresh worker, and reports repository checks, update availability, updates and rollback state through the Diagnostics health interface.

Plugin setup
-----------

* Use update plugin:  
  If the box is checked, the plugin checks for available system updates every hour.

* Automatic update:  
  If the box is checked, the plugin will update the system itself 

* Send E-mail if update is available:  
  For this function required E-mail plugin.

* E-mail subject:  
  The subject of the E-mail being sent.

* Show in footer:  
  Show data from plugin in footer on home page.

* Status:  
  Status window from the plugin.
