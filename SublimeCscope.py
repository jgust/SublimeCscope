import sublime
import sys
import os
from imp import reload

PACKAGE_NAME = 'SublimeCscope'
DEBUG = False

ST_VERSION_SUPPORTED = 3059

def reload_plugin():
    reloader_name = PACKAGE_NAME + '.sublime_cscope.reloader'
    if reloader_name in sys.modules:
        reload(sys.modules[reloader_name])

def plugin_loaded():
    if DEBUG: print("SublimeCscope loaded")
    load_settings().add_on_change(PACKAGE_NAME, indexer.settings_changed)
    indexer.refresh()

def plugin_unloaded():
    if DEBUG: print("SublimeCscope unloaded")
    indexer.quit()
    load_settings().clear_on_change(PACKAGE_NAME)

if int(sublime.version()) < ST_VERSION_SUPPORTED:
    del plugin_loaded
    del plugin_unloaded

    print('%s: Please upgrade to Sublime Text 3 Build %d or higher.'
                                         % (PACKAGE_NAME, ST_VERSION_SUPPORTED))
# Finish setting up the package (borrowed from Package Control)
else:
    # Make sure all dependencies are reloaded on upgrade
    reload_plugin()

    from .sublime_cscope import reloader
    from .sublime_cscope import indexer
    from .sublime_cscope.settings import load_settings
    from .sublime_cscope.event_listener import EventListener
    from .sublime_cscope.commands import *

    if DEBUG:
        from .sublime_cscope.debug_commands import *


