
import sublime
import sublime_plugin

from ..SublimeCscope import DEBUG
from . import indexer

# These commands should trigger a state change event in the indexer
PROJECT_COMMANDS = ('prompt_add_folder',
                    'prompt_open_project_or_workspace',
                    'prompt_switch_project_or_workspace',
                    'prompt_select_workspace',
                    'open_recent_project_or_workspace')

class EventListener(sublime_plugin.EventListener):
    """Monitors events from the editor and tries to figure out
       when it is meaningful to notify the indexers"""

    def __init__(self):
        super().__init__()
        self._curr_active_window = 0
        self._project_command_in_progres = []
        self._last_saved_buffer = None
        self._last_closed_buffer = None


    def _check_active_window(self):
        curr_active_window = sublime.active_window().id()

        # don't notify any change the first time
        if self._curr_active_window == 0:
            self._curr_active_window = curr_active_window
            return False

        prev_active_window = self._curr_active_window
        self._curr_active_window = curr_active_window

        #A change in active window can mean that a new window was created,
        #a window was closed or the user switched between windows.
        if prev_active_window != curr_active_window:
            return True

        return False


    def _clear_last_saved_buffer(self):
        self._last_saved_buffer = None


    def _clear_last_closed_buffer(self):
        self._last_closed_buffer = None


    def _find_open_file(self, file_name):
        for win in sublime.windows():
            if win.find_open_file(file_name):
                return True
        return False


    def on_post_save(self, view):
        self._check_active_window()
        file_name = view.file_name()
        if not view.is_scratch() and file_name:
            # ignore multiple calls for the same buffer for 1 second.
            if file_name != self._last_saved_buffer:
                self._last_saved_buffer = file_name
                indexer.buffer_promoted(file_name)
                sublime.set_timeout_async(self._clear_last_saved_buffer, 1000)


    def on_close(self, view):
        self._check_active_window()
        file_name = view.file_name()
        if not view.is_scratch() and file_name:
            # only send buffer demoted if all views into the buffer have been
            # closed.
            if file_name != self._last_closed_buffer and not self._find_open_file(file_name):
                self._last_closed_buffer = file_name
                indexer.buffer_demoted(file_name)
                sublime.set_timeout_async(self._clear_last_closed_buffer, 1000)


    def on_activated(self, view):
        focus_changed = self._check_active_window()
        window_id = view.window().id() if view.window() else 0
        proj_command_complete = False

        if window_id in self._project_command_in_progres:
            proj_command_complete = True
            self._project_command_in_progres.remove(window_id)

        if window_id and (focus_changed or proj_command_complete):
            indexer.window_state_changed()


    def on_window_command(self, win, cmd_name, args):
        self._check_active_window()

        if not win.id():
            return

        # if DEBUG:
        #     print("Got window command: %s" % cmd_name)

        if cmd_name in PROJECT_COMMANDS:
            if win.id() not in self._project_command_in_progres:
                self._project_command_in_progres.append(win.id())
            else:
                print("Got command %s from win: %d while other already in progress")

        elif cmd_name == 'refresh_folder_list':
            indexer.refresh(win)

        elif cmd_name == 'remove_folder':
            indexer.window_state_changed()


