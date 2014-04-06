
import unittest
from unittest.mock import patch, MagicMock

from .. import event_listener

_indexer_to_mock = 'SublimeCscope.sublime_cscope.event_listener.indexer'
_sublime_to_mock = 'SublimeCscope.sublime_cscope.event_listener.sublime'

class EventListenerTests(unittest.TestCase):

    def setUp(self):
        self.test_obj = event_listener.EventListener()

    @patch(_indexer_to_mock, autospec=True)
    def test_buffer_promotion(self, mock_indexer):
        """ Modified buffers should be promoted to hot list
        Buffer should be promoted to the hot list if it
        has been modified (just getting a save event is good enough).
        """

        file_name = '/somedir/otherdir/test_file.c'
        win_id = 1

        mock_view = MagicMock()
        mock_view.window().id.return_value = win_id
        mock_view.file_name.return_value = file_name
        mock_view.is_scratch.return_value = False

        self.test_obj.on_post_save(mock_view)
        win_id += 1
        mock_view.window().id.return_value = win_id
        self.test_obj.on_post_save(mock_view)

        # A change in window id should not trigger a window state change on buffer save
        self.assertFalse(mock_indexer.window_state_changed.called)

        mock_indexer.buffer_promoted.assert_called_once_with(file_name)

        # Scratch buffers should be ignored
        mock_indexer.reset_mock()
        win_id += 1
        mock_view.is_scratch.return_value = True

        self.test_obj.on_post_save(mock_view)

        self.assertFalse(mock_indexer.window_state_changed.called)
        self.assertFalse(mock_indexer.buffer_promoted.called)

    @patch(_indexer_to_mock, autospec=True)
    def test_buffer_demotion(self, mock_indexer):
        """Buffer should be demoted from the hot list when it has been closed."""
        file_name = '/somedir/otherdir/test_file.c'
        win_id = 1

        mock_view = MagicMock()
        mock_view.window().id.return_value = win_id
        mock_view.file_name.return_value = file_name
        mock_view.is_scratch.return_value = False

        self.test_obj.on_close(mock_view)
        win_id += 1
        mock_view.window().id.return_value = win_id
        self.test_obj.on_close(mock_view)

        mock_indexer.buffer_demoted.assert_called_once_with(file_name)

        # Scratch buffers should be ignored
        mock_indexer.reset_mock()
        win_id += 1
        mock_view.is_scratch.return_value = True

        self.test_obj.on_post_save(mock_view)
        self.assertFalse(mock_indexer.window_state_changed.called)
        self.assertFalse(mock_indexer.buffer_promoted.called)

    @patch(_sublime_to_mock, autospec=True)
    @patch(_indexer_to_mock, autospec=True)
    def test_ongoing_project_commands(self, mock_indexer, mock_sublime):
        win_id = 1

        mock_win = MagicMock()
        mock_win.window.return_value = mock_win
        mock_win.id.return_value = win_id

        mock_sublime.active_window.return_value = mock_win

        self.test_obj.on_window_command(mock_win,
            event_listener.PROJECT_COMMANDS[0], None)

        self.test_obj.on_activated(mock_win)

        self.assertTrue(mock_indexer.window_state_changed.called)


    @patch(_sublime_to_mock, autospec=True)
    @patch(_indexer_to_mock, autospec=True)
    def test_window_state_changes(self, mock_indexer, mock_sublime):
        """  Test window state change scenarios
        We want to detect any window changes that suggest that the user has
        1) opened a new project, 2) closed a window (and thus any open project),
        3) changed the project folders (add/remove folders)
        """
        win_id = 1
        mock_win = MagicMock()
        mock_win.id.return_value = win_id

        mock_sublime.active_window.return_value = mock_win

        mock_win.window.return_value = mock_win


        self.test_obj.on_activated(mock_win)
        self.test_obj.on_activated(mock_win)

        self.assertFalse(mock_indexer.window_state_changed.called)

        win_id += 1
        mock_win.id.return_value = win_id

        self.test_obj.on_activated(mock_win)

        self.assertTrue(mock_indexer.window_state_changed.called)



















