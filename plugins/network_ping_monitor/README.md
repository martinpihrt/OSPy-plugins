Network Ping Monitor Readme
====

This extension allows you to ping addresses. All pings are recorded in a file.
If logging is enabled, a graph with measured data will be displayed at the bottom of the screen.  

The plug-in includes an OSPy `plugin.json` manifest, registers its ICMP polling
worker with the shared plug-in runtime, uses the common stop signal, and
implements `health()`. Stop requests are checked between targets so only the
currently running timeout-bounded ping needs to finish. Diagnostics reports
worker and per-target state, latest completed cycle, partial or total
reachability loss, and internal errors. Optional local and SQL logging remain
independent of diagnostic ping status.

Plugin setup
-----------
* Use ping monitoring:    
  Activate this extension use for ping testing.  

* Ping address 1, 2, 3:  
  1-3 address for testing.     

* Status:  
  Status window from the plugin.
