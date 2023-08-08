Prototype Readme
====

Tested in Python 3+

The proto plugin is designed as a starting point for creating new plugin for OSPy. It does not perform any useful action but contains the basic components necessary for a functioning plugin. More detailed information can be found directly in the plugin on the help page.

The basic structure is as follows:

    plugins
    + plugin_name
      + data
      + docs
      + static
      + templates
      + __init__.py
      \ README.md

The static files will be made accessible automatically at the following location:
/plugins/plugin_name/static/...

All *.md files in the docs directory will be visible in the help page.
The README.md (if available) will be the first entry in the help page
and might be used in the future as a description for plug-in browsing.