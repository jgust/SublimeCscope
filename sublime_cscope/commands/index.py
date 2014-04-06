import sublime
import sublime_plugin

from .. import indexer

class ScRefreshAllCommand(sublime_plugin.WindowCommand):
    def run(self):
        indexer.refresh()
