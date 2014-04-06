
import os
import sublime
import sublime_plugin
from unittest import defaultTestLoader, TextTestRunner

from ...SublimeCscope import reload_plugin, plugin_loaded, plugin_unloaded

import SublimeCscope.sublime_cscope.tests

def _load_plugin():
    try:
        plugin_loaded()
    except Exception as e:
        print (e)

def _unload_plugin():
    try:
        plugin_unloaded()
    except Exception as e:
        print (e)


class ScTestsCommand(sublime_plugin.WindowCommand):
    def run(self):
        _unload_plugin()
        reload_plugin()
        sublime.set_timeout_async(self.run_tests(), 500)

    def run_tests(self):
        suite = defaultTestLoader.loadTestsFromModule(SublimeCscope.sublime_cscope.tests)
        runner = TextTestRunner()
        runner.run(suite)
        _load_plugin()
