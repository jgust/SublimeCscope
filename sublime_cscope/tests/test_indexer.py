
import os
import threading
import unittest
import itertools
from unittest.mock import call, patch, MagicMock


from .. import indexer

_indexer_package_path = 'SublimeCscope.sublime_cscope.indexer'
_indexer_to_mock = _indexer_package_path + '.Indexer'
_indexer_config_to_mock = _indexer_package_path + '.IndexerConfig'
_sublime_to_mock = _indexer_package_path + '.sublime'
_os_to_mock = _indexer_package_path + '.os'

DUMMY_FILE_ST_MODE = 33188
DUMMY_FOLDER_ST_MODE = 16877
DUMMY_SYMLINK_ST_MODE = 41471


class TestActor(indexer.ActorBase):

    def __init__(self):
        super().__init__()
        self.request = []
        self.recv_response = []
        self.sent_response = []
        self.recv_response_event = threading.Event()

    @indexer.send_msg
    def _test_request(self, requester_id):
        req = {}
        req['requester_id'] = requester_id
        req['receiver_id'] = threading.get_ident()
        self.request.append(req)
        self.sent_response.append(req)
        return req

    @indexer.send_msg
    def test_request(self, requester_id):
        return self._test_request(requester_id)

    @indexer.send_msg
    def trigger_request_async(self):
        return self._test_request(threading.get_ident(), send_always=True, result_callback=self.test_response)

    @indexer.send_msg
    def test_response(self, result):
        resp = {}
        resp['result'] = result
        resp['receiver_id'] = threading.get_ident()
        self.recv_response.append(resp)
        self.recv_response_event.set()



class ActorTests(unittest.TestCase):

    def setUp(self):
        self.testActor1 = TestActor()
        self.testActor2 = TestActor()

        self.assertFalse(self.testActor1._is_started())
        self.assertFalse(self.testActor2._is_started())

        self.testActor1.start()
        self.testActor2.start()

        self.assertTrue(self.testActor1._is_started())
        self.assertTrue(self.testActor2._is_started())

        self.own_thread_id = threading.get_ident()
        self.actor1_id = self.testActor1._thread_id
        self.actor2_id = self.testActor2._thread_id

    def tearDown(self):
        self.testActor1.quit()
        self.testActor2.quit()

        self.assertFalse(self.testActor1._is_started())
        self.assertFalse(self.testActor2._is_started())

    def test_async_request_response(self):

        # Send the request to actor1 and send the response to actor2
        self.testActor1.test_request(self.own_thread_id, result_callback=self.testActor2.test_response)

        self.assertTrue(self.testActor2.recv_response_event.wait(5))

        self.assertEqual(self.testActor1.recv_count, 1)
        self.assertEqual(self.testActor2.recv_count, 1)

        self.assertTrue(len(self.testActor1.request) == 1)
        self.assertTrue(len(self.testActor1.sent_response) == 1)
        self.assertTrue(len(self.testActor1.recv_response) == 0)

        self.assertTrue(len(self.testActor2.request) == 0)
        self.assertTrue(len(self.testActor2.sent_response) == 0)
        self.assertTrue(len(self.testActor2.recv_response) == 1)

        req = self.testActor1.request[0]
        sent_resp = self.testActor1.sent_response[0]
        recv_resp = self.testActor2.recv_response[0]

        self.assertIs(sent_resp, recv_resp['result'], "Sent and received responses don't match")
        self.assertEqual(recv_resp['receiver_id'], self.actor2_id, "Response was not received by correct actor")
        self.assertEqual(req['requester_id'], self.own_thread_id, "Requester ID did not come through")
        self.assertEqual(req['receiver_id'], self.actor1_id, "Request was not recieved by correct actor")

    def test_sync_request_response(self):
        resp1 = self.testActor1.test_request(self.own_thread_id, wait_for_result=True)
        resp2 = self.testActor2.test_request(self.own_thread_id, wait_for_result=True)

        self.assertEqual(self.testActor1.recv_count, 1)
        self.assertEqual(self.testActor2.recv_count, 1)

        self.assertIsNotNone(resp1)
        self.assertIsNotNone(resp2)

        self.assertTrue(len(self.testActor1.sent_response) == 1)
        self.assertTrue(len(self.testActor1.recv_response) == 0)

        self.assertTrue(len(self.testActor2.sent_response) == 1)
        self.assertTrue(len(self.testActor2.recv_response) == 0)

        self.assertEqual(resp1['requester_id'], self.own_thread_id)
        self.assertEqual(resp2['requester_id'], self.own_thread_id)
        self.assertEqual(resp1['receiver_id'], self.actor1_id)
        self.assertEqual(resp2['receiver_id'], self.actor2_id)

    def test_internal_async_request(self):
        self.testActor1.trigger_request_async()

        self.assertTrue(self.testActor1.recv_response_event.wait(5))

        # Should have triggered an extra intra-actor message
        self.assertEqual(self.testActor1.recv_count, 2)

        self.assertTrue(len(self.testActor1.request) == 1)
        self.assertTrue(len(self.testActor1.sent_response) == 1)
        self.assertTrue(len(self.testActor1.recv_response) == 1)

        req = self.testActor1.request[0]
        sent_resp = self.testActor1.sent_response[0]
        recv_resp = self.testActor1.recv_response[0]

        self.assertIs(sent_resp, recv_resp['result'], "Sent and received responses don't match")
        self.assertEqual(recv_resp['receiver_id'], self.actor1_id, "Response was not received by correct actor")
        self.assertEqual(req['requester_id'], self.actor1_id, "Requester ID did not come through")
        self.assertEqual(req['receiver_id'], self.actor1_id, "Request was not recieved by correct actor")



class IndexerTests(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass



@patch(_os_to_mock + '.stat')
@patch(_os_to_mock + '.walk')
class CrawlerTests(unittest.TestCase):

    def setUp(self):
        self.mconfig = MagicMock(indexer.IndexerConfig)
        self.bps = ['testfolder/sources', 'testfolder/headers']
        self.mconfig.base_paths.return_value = [(self.bps[0], True), (self.bps[1], True)]
        self.mconfig.find_base_path.return_value = (self.bps[0], True)
        self.mconfig.file_matches.side_effect = self.mock_matches
        self.mconfig.folder_matches.side_effect = self.mock_matches

        self.test_obj = indexer.Crawler()
        self.test_obj.start()

    def tearDown(self):
        self.test_obj.quit()


    def mock_matches(self, dirpath, element, st_mode=0, base_path=None):
        self.assertIsNotNone(self.selector_data)

        p = os.path.join(dirpath, element)
        return self.selector_data[p]

    def mock_stat(self, file, follow_symlinks=True):
        folder, base = os.path.split(file)
        name, ext = os.path.splitext(base)
        mode = DUMMY_FOLDER_ST_MODE

        ino = 0
        size = 0
        mtime = 0

        self.assertIsNotNone(self.mock_data)
        mock_data = self.mock_data
        for k in self.mock_data.keys():
            if file == k:
                ino = mock_data[k]['ino']
            else:
                if folder.startswith(k):
                    mock_data = mock_data[k]
                    folder = folder[len(k+os.path.sep):]
                    if folder:
                        for s in folder.split(os.path.sep):
                            mock_data = mock_data[s]

                    if not ext:
                        ino = mock_data[name]['ino']
                    else:
                        for i, f in enumerate(mock_data['fdata']['files']):
                            if f == base:
                                ino = mock_data['fdata']['inos'][i]
                                size = mock_data['fdata']['sizes'][i]
                                mtime = mock_data['fdata']['mtimes'][i]

        self.assertNotEqual(ino, 0, "File/Folder: %s not found" % file)

        if name.endswith("_ln") and not follow_symlinks:
            mode = DUMMY_SYMLINK_ST_MODE
        elif ext:
            mode = DUMMY_FILE_ST_MODE

        mock = MagicMock()
        mock.st_mode = mode
        mock.st_ino = ino
        mock.st_size = size
        mock.st_mtime = mtime

        return mock


    def mock_walk(self, path, followlinks=False):
        self.assertIsNotNone(self.mock_data)

        sub_data = None
        if path in self.mock_data:
            sub_data = self.mock_data[path]
        else:
            for k in self.mock_data.keys():
                if path.startswith(k):
                    sub_data = self.mock_data[k]
                    sub_path = path[len(k+os.path.sep):]
                    for p in sub_path.split(os.path.sep):
                        sub_data = sub_data[p]

        files = sub_data.get('fdata', {}).get('files', [])
        folders = list(set(sub_data.keys()) - set(('fdata', 'ino')))

        yield path, folders, files
        for f in folders:
            if followlinks or not f.endswith('_ln'):
                yield from self.mock_walk(os.path.join(path, f), followlinks)


    def gen_test_data(self, base_paths, levels=1,
                      files_per_level=5, ln_per_level=2,
                      subdirs_per_level=2, subdir_ln_per_level=1):
        seeder = itertools.count(123, 53)
        test_data = {}

        if levels < 1:
            levels = 1

        for bp in base_paths:
            test_data[bp] = {}
            self.gen_subdir_data(test_data[bp], levels,
                                 subdirs_per_level, subdir_ln_per_level,
                                 files_per_level, ln_per_level, seeder)

        return test_data

    def gen_subdir_data(self, curr_level_dict, descend_levels,
                        num_subdirs, num_subdir_links,
                        num_files, num_links, seeder):
        curr_level_dict['ino'] = next(seeder)
        curr_level_dict['fdata'] = self.gen_file_data(num_files,
                                                      num_links,
                                                      next(seeder),
                                                      next(seeder))
        if descend_levels > 0:
            for sub in range(num_subdirs):
                next_level_dict = {}
                curr_level_dict['sub%d' % sub] = next_level_dict
                self.gen_subdir_data(next_level_dict, descend_levels-1,
                                     num_subdirs, num_subdir_links,
                                     num_files, num_links, seeder)

            for sub in range(num_subdir_links):
                next_level_dict = {}
                curr_level_dict['sub%d_ln' % sub] = next_level_dict
                self.gen_subdir_data(next_level_dict, descend_levels-1,
                                     num_subdirs, num_subdir_links,
                                     num_files, num_links, seeder)


    def gen_file_data(self, num_files, num_links, start_ino, seed):
        files = ['testfile%d.dummy' % i for i in range(num_files)]
        links = ['testfile%d_ln.dummy' % i for i in range(num_links)]
        files.extend(links)

        inos = [i for i in range(start_ino, start_ino+num_files+num_links)]
        sizes = [(hash(f) + seed) >> 15 for f in files]
        mtimes = [(hash(f) * seed) >> 15 for f in files]
        data = {}
        data['files'] = files
        data['inos'] = inos
        data['sizes'] = sizes
        data['mtimes'] = mtimes

        return data

    def gen_selector_data(self, test_data, cycle_list):
        sel = itertools.cycle(cycle_list)
        selector_data = {}

        for bp, bp_data in test_data.items():
            self.gen_selector_subdir_data(selector_data, bp, bp_data, sel)

        return selector_data

    def gen_selector_subdir_data(self, selector_data,
                                 prepend_path, test_data, sel):

        for k, v in test_data.items():
            if k == 'ino':
                next
            elif k == 'fdata':
                for f in v['files']:
                    full_path = os.path.join(prepend_path, f)
                    selector_data[full_path] = next(sel)
            else:
                is_selected = next(sel)
                if not is_selected:
                    # if a subdir is not selected, none if its children
                    # should be selected either
                    sel = itertools.cycle([False])

                full_path = os.path.join(prepend_path, k)
                selector_data[full_path] = is_selected
                self.gen_selector_subdir_data(selector_data, full_path, v, sel)

    def gen_expected_result(self, test_data, selector_data):
        exp_result = {}

        for bp, bp_data in test_data.items():
            self.gen_expected_result_subdir(bp, bp_data, selector_data, exp_result)

        return exp_result

    def gen_expected_result_subdir(self, curr_path, subdir_data,
                                   selector_data, exp_result):
        result = {}
        exp_result[subdir_data['ino']] = result
        result['path'] = curr_path
        result['files'] = []
        result['magic'] = 0

        if 'fdata' in subdir_data:
            for i, f in enumerate(subdir_data['fdata']['files']):
                p = os.path.join(curr_path, f)
                if selector_data[p]:
                    result['files'].append(f)
                    result['magic'] += subdir_data['fdata']['sizes'][i] + \
                                        subdir_data['fdata']['mtimes'][i]

        for sd in set(subdir_data.keys()) - set(('ino', 'fdata')):
            p = os.path.join(curr_path, sd)
            if selector_data[p]:
                self.gen_expected_result_subdir(p, subdir_data[sd],
                                                selector_data, exp_result)

    def test_full_crawl(self, mock_os_walk, mock_os_stat):
        # setup the mocks
        mock_os_walk.side_effect = self.mock_walk
        mock_os_stat.side_effect = self.mock_stat

        #generate a fake file tree two levels deep
        self.mock_data = self.gen_test_data(self.bps, levels=2)

        #generate selector data so that every other file is selected
        self.selector_data = self.gen_selector_data(self.mock_data, [True, False])

        # print("mock data: %s" % self.mock_data)
        # print("selector data: %s" % self.selector_data)

        # generate the expected results from the data above
        exp_result = self.gen_expected_result(self.mock_data, self.selector_data)

        # print("Exp result: %s" % exp_result)
        res, ud = self.test_obj.crawl(self.mconfig, 'test', wait_for_result=True)

        self.assertEqual(ud, 'test')
        self.assertEqual(res, exp_result)

    @unittest.skip("Unimplemented")
    def test_no_follow_links(self, mock_os_walk, mock_os_stat):
        pass

    @unittest.skip("Unimplemented")
    def test_link_loop(self, mock_os_walk, mock_os_stat):
        pass

    @unittest.skip("Unimplemented")
    def test_only_files(self, mock_os_walk, mock_os_stat):
        pass

    @unittest.skip("Unimplemented")
    def test_only_folders(self, mock_os_walk, mock_os_stat):
        pass



class IndexerConfigTests(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    @staticmethod
    def gen_mock_window(idx):

        mock_win = MagicMock()
        mock_view = MagicMock()
        mock_settings = MagicMock()

        proj_file = "/somedir/someotherdir/mock_proj%d.sublime-project" % idx

        proj_folders = []
        proj_data = {}

        proj_data['folders'] = proj_folders

        mock_win.id.return_value = idx

        # This is actually a View attribute, but its added
        # to the mock in order to pass through all functions
        # that take view_or_window.
        mock_win.window.return_value = mock_win

        mock_win.active_view.return_value = mock_view
        mock_win.project_file_name.return_value = proj_file
        mock_win.folders.return_value = proj_folders
        mock_win.project_data.return_value = proj_data

        mock_view.settings.return_value = mock_settings

        mock_settings._dict = {}
        mock_settings.get.side_effect = lambda k, d: mock_settings._dict.get(k, d)

        return mock_win

    @staticmethod
    def add_folder_to_window(win,
                             path,
                             follow_links=True,
                             file_includes=[],
                             file_excludes=[],
                             folder_includes=[],
                             folder_excludes=[],
                             index_excludes=[]):
        folder_config = {}
        folder_config['path'] = path
        folder_config['follow_symlinks'] = follow_links
        folder_config['file_include_patterns'] = file_includes
        folder_config['file_exclude_patterns'] = file_excludes
        folder_config['folder_include_patterns'] = folder_includes
        folder_config['folder_exclude_patterns'] = folder_excludes

        win.project_data()['folders'].append(folder_config)

        win.active_view().settings()._dict['index_exclude_patterns'] = index_excludes

    def test_two_configs_same_window(self):

        win = self.gen_mock_window(1)
        self.add_folder_to_window(win, '/thisdir/thatdir/mockdir',
                                  file_includes=['test*', 'mock*'],
                                  file_excludes=['*.o', '*.log'],
                                  folder_includes=['testdir*', 'mockdir*'],
                                  folder_excludes=['out', 'logs'],
                                  index_excludes=['*.p', '*BACKUP*'])

        self.add_folder_to_window(win, '/thisdir/thatdir2/mockdir2',
                                  file_includes=['test*', 'mock*'],
                                  file_excludes=['*.o', '*.log'],
                                  folder_includes=['testdir*', 'mockdir*'],
                                  folder_excludes=['out', 'logs'],
                                  index_excludes=['*.p', '*BACKUP*'])

        with patch(_os_to_mock + '.path.exists', return_value=True) as mock_os:
            config1 = indexer.IndexerConfig(win)
            config2 = indexer.IndexerConfig(win)

        self.assertEqual(config1, config1)
        self.assertEqual(config1, config2)

    def test_two_configs_different_windows(self):
        win1 = self.gen_mock_window(1)
        win2 = self.gen_mock_window(2)
        win3 = self.gen_mock_window(3)

        win2.project_file_name.return_value = win1.project_file_name()

        self.add_folder_to_window(win1, '/thisdir/thatdir/mockdir',
                                  file_includes=['test*', 'mock*'],
                                  file_excludes=['*.o', '*.log'],
                                  folder_includes=['testdir*', 'mockdir*'],
                                  folder_excludes=['out', 'logs'],
                                  index_excludes=['*.p', '*BACKUP*'])

        self.add_folder_to_window(win2, '/thisdir/thatdir/mockdir',
                                  file_includes=['test*', 'mock*'],
                                  file_excludes=['*.o', '*.log'],
                                  folder_includes=['testdir*', 'mockdir*'],
                                  folder_excludes=['out', 'logs'],
                                  index_excludes=['*.p', '*BACKUP*'])

        self.add_folder_to_window(win3, '/thisdir/thatdir2/mockdir2',
                                  file_includes=['test*', 'mock*'],
                                  file_excludes=['*.o', '*.log'],
                                  folder_includes=['testdir*', 'mockdir*'],
                                  folder_excludes=['out', 'logs'],
                                  index_excludes=['*.p', '*BACKUP*'])

        with patch(_os_to_mock + '.path.exists', return_value=True) as mock_os:
            config1 = indexer.IndexerConfig(win1)
            config2 = indexer.IndexerConfig(win2)
            config3 = indexer.IndexerConfig(win3)

        self.assertEqual(config1, config2)
        self.assertNotEqual(config2, config3)

    def test_empty_whitelist_blacklist(self):
        win = self.gen_mock_window(1)
        base_path = '/thisdir/thatdir/mockdir'
        self.add_folder_to_window(win, base_path,
                                  file_includes=[],
                                  file_excludes=[],
                                  folder_includes=[],
                                  folder_excludes=[],
                                  index_excludes=[])

        with patch(_os_to_mock + '.path.exists', return_value=True) as mock_os:
            config = indexer.IndexerConfig(win)

        sub_folder = os.path.join(base_path, 'test')

        self.assertTrue(config.file_matches(sub_folder,
                                            'test.c',
                                            DUMMY_FILE_ST_MODE,
                                            base_path))

        self.assertTrue(config.folder_matches(sub_folder,
                                              'test',
                                              DUMMY_FOLDER_ST_MODE,
                                              base_path))



    def test_blacklist(self):
        win = self.gen_mock_window(1)
        base_path = '/thisdir/thatdir/mockdir'
        self.add_folder_to_window(win, base_path,
                                  file_includes=[],
                                  file_excludes=['*test*'],
                                  folder_includes=[],
                                  folder_excludes=['test'],
                                  index_excludes=[])

        with patch(_os_to_mock + '.path.exists', return_value=True) as mock_os:
            config = indexer.IndexerConfig(win)

        sub_folder = os.path.join(base_path, 'sub')

        self.assertFalse(config.file_matches(sub_folder,
                                             'test.c',
                                             DUMMY_FILE_ST_MODE,
                                             base_path))

        self.assertTrue(config.file_matches(sub_folder,
                                            'source.c',
                                             DUMMY_FILE_ST_MODE,
                                             base_path))

        self.assertFalse(config.folder_matches(sub_folder,
                                              'test',
                                               DUMMY_FOLDER_ST_MODE,
                                               base_path))

        self.assertTrue(config.folder_matches(sub_folder,
                                              'source',
                                               DUMMY_FOLDER_ST_MODE,
                                               base_path))

    def test_whitelist(self):
        win = self.gen_mock_window(1)
        base_path = '/thisdir/thatdir/mockdir'
        self.add_folder_to_window(win, base_path,
                                  file_includes=['prefix*.*'],
                                  file_excludes=[],
                                  folder_includes=['sources'],
                                  folder_excludes=[],
                                  index_excludes=[])

        with patch(_os_to_mock + '.path.exists', return_value=True) as mock_os:
            config = indexer.IndexerConfig(win)


        self.assertFalse(config.file_matches(base_path,
                                             'test.c',
                                             DUMMY_FILE_ST_MODE,
                                             base_path))

        self.assertTrue(config.file_matches(base_path,
                                            'prefixsource.c',
                                             DUMMY_FILE_ST_MODE,
                                             base_path))

        self.assertFalse(config.folder_matches(base_path,
                                              'test',
                                               DUMMY_FOLDER_ST_MODE,
                                               base_path))

        self.assertTrue(config.folder_matches(base_path,
                                              'sources',
                                               DUMMY_FOLDER_ST_MODE,
                                               base_path))


# For some reason, this doesn't work.  The dict doesn't get unpatch
# after each test.
# @patch.dict(indexer._indexers_by_win, clear=True)
# @patch.dict(indexer._indexers, clear=True)
@patch(_sublime_to_mock, autospec=True)
@patch(_indexer_to_mock, autospec=True)
@patch(_indexer_config_to_mock, autospec=True)
class IndexerApiTests(unittest.TestCase):

    def setUp(self):
        self._gen_win_id = 0
        self._mock_windows = [self.gen_mock_window() for n in range(3)]
        self._mock_indexer_instances = []
        self._mock_config_instances = []

        indexer._indexers.clear()
        indexer._indexers_by_win.clear()

    def tearDown(self):
        indexer.quit()

        self.assertEqual(0, len(indexer._indexers))
        self.assertEqual(0, len(indexer._indexers_by_win))

    def gen_mock_window(self):

        self._gen_win_id += 1

        mock_win = MagicMock()

        proj_file = "/somedir/someotherdir/mock_proj%d.sublime-project" % self._gen_win_id

        proj_folders = ["/thisdir/thatdir/mockdir%d" % n for n in range(2)]

        mock_win.id.return_value = self._gen_win_id
        mock_win.window.return_value = mock_win
        mock_win.project_file_name.return_value = proj_file
        mock_win.folders.return_value = proj_folders

        return mock_win

    def test_start_stop(self, mock_config, mock_indexer, mock_sublime):
        """ Simulates starting and closing of the editor
        When started, all windows containing open folders should get an
        Indexer. All active indexers should be closed gracefully when the
        editor is closed
        """
        mock_sublime.windows.return_value = self._mock_windows
        mock_sublime.active_window.return_value = self._mock_windows[0]

        # Start sending a refresh all
        indexer.refresh()

        self.assertEqual(len(self._mock_windows), len(indexer._indexers))
        self.assertEqual(len(self._mock_windows), len(indexer._indexers_by_win))

        # Proper closing is tested at teardown

    def test_new_project_window(self, mock_config, mock_indexer, mock_sublime):
        mock_sublime.windows.return_value = self._mock_windows[:1]
        mock_sublime.active_window.return_value = self._mock_windows[0]

        # Create an initial state
        indexer.refresh()

        self.assertEqual(1, len(indexer._indexers))
        self.assertEqual(1, len(indexer._indexers_by_win))

        # open a new window
        mock_sublime.windows.return_value = self._mock_windows[:2]
        mock_sublime.active_window.return_value = self._mock_windows[1]

        indexer.window_state_changed()

        self.assertEqual(2, len(indexer._indexers))
        self.assertEqual(2, len(indexer._indexers_by_win))

    def test_close_project_window(self, mock_config, mock_indexer, mock_sublime):
        mock_sublime.windows.return_value = self._mock_windows[:2]
        mock_sublime.active_window.return_value = self._mock_windows[1]

        indexer.refresh()

        self.assertEqual(2, len(indexer._indexers))
        self.assertEqual(2, len(indexer._indexers_by_win))

        #close one window
        mock_sublime.windows.return_value = self._mock_windows[:1]
        mock_sublime.active_window.return_value = self._mock_windows[0]

        indexer.window_state_changed()

        self.assertEqual(1, len(indexer._indexers))
        self.assertEqual(1, len(indexer._indexers_by_win))

    def test_switch_project_in_window(self, mock_config,
                                      mock_indexer, mock_sublime):
        mock_sublime.windows.return_value = self._mock_windows[:2]
        mock_sublime.active_window.return_value = self._mock_windows[1]

        indexer.refresh()

        self.assertEqual(2, len(indexer._indexers))
        self.assertEqual(2, len(indexer._indexers_by_win))

        # change the project in the first window
        new_win = self.gen_mock_window()
        new_win.id.return_value = self._mock_windows[0].id()
        self._mock_windows[0] = new_win

        mock_sublime.windows.return_value = self._mock_windows[:2]
        mock_sublime.active_window.return_value = self._mock_windows[0]

        indexer.window_state_changed()

        # The indexer belonging to the previous project should be closed
        self.assertEqual(2, len(indexer._indexers))
        self.assertEqual(2, len(indexer._indexers_by_win))

        projects = [win.project_file_name() for win in self._mock_windows[:2]]
        for key in indexer._indexers.keys():
            self.assertTrue(key in projects)

    def test_same_project_in_multiple_windows(self, mock_config,
                                              mock_indexer, mock_sublime):
        mock_sublime.windows.return_value = self._mock_windows
        mock_sublime.active_window.return_value = self._mock_windows[0]

        indexer.refresh()

        #make window 2 point to window 1´s project
        self._mock_windows[1].project_file_name.return_value \
                                        = self._mock_windows[0].project_file_name()
        self._mock_windows[1].folders.return_value \
                                        = self._mock_windows[0].folders()

        indexer.window_state_changed()

        # We should have two indexers and three windows
        self.assertEqual(2, len(indexer._indexers))
        self.assertEqual(len(self._mock_windows), len(indexer._indexers_by_win))

        projects = [win.project_file_name() for win in self._mock_windows]
        for key in indexer._indexers.keys():
            self.assertTrue(key in projects)

    def test_focus_change(self, mock_config, mock_indexer, mock_sublime):
        mock_sublime.windows.return_value = self._mock_windows
        mock_sublime.active_window.return_value = self._mock_windows[0]

        indexer.refresh()

        mock_sublime.active_window.return_value = self._mock_windows[1]

        # all calls to Indexer() will now return a new Mock object
        new_ind_mock = MagicMock(indexer.Indexer)
        old_ind_mock = mock_indexer.return_value
        mock_indexer.return_value = new_ind_mock
        old_ind_mock.reset_mock()

        indexer.window_state_changed()

        # Since there is no change, no new indexers should be created.
        indexer_instances = [n['indexer'] for n in indexer._indexers.values()]
        for ind_mock in indexer_instances:
            self.assertIs(ind_mock, old_ind_mock)

        # only calls to Indexer#start are allowed (since it is a no-op when started)
        calls = {name for name, _, _ in old_ind_mock.mock_calls}
        calls = calls - set(('start',))
        self.assertEqual(0, len(calls))

    def test_plugin_settings_change(self, mock_config,
                                    mock_indexer, mock_sublime):
        mock_sublime.windows.return_value = self._mock_windows
        mock_sublime.active_window.return_value = self._mock_windows[0]

        indexer.refresh()

        # Simulate that a project settings change causes a change in the indexer
        # config
        new_config_mock = MagicMock(indexer.IndexerConfig)
        mock_config.return_value = new_config_mock
        new_config_mock.__eq__.return_value = False
        new_config_mock.__ne__.return_value = True
        mock_indexer.return_value.reset_mock()

        indexer.settings_changed()
        # Should result in a new call to set_config
        calls = [(name, arg) for name, arg, _ in mock_indexer.return_value.method_calls
                                                        if name == 'set_config']
        self.assertEqual(len(self._mock_windows), len(calls))
        for _, arg in calls:
            self.assertIs(arg[0], new_config_mock)

        # Call again, this time there is no change in config
        new_config_mock.__eq__.return_value = True
        new_config_mock.__ne__.return_value = False
        mock_indexer.return_value.reset_mock()

        indexer.settings_changed()
        calls = {name for name, _, _ in mock_indexer.return_value.mock_calls}
        calls = calls - set(('start',))
        self.assertEqual(0, len(calls))


    def test_project_settings_change(self, mock_config,
                                     mock_indexer, mock_sublime):
        mock_sublime.windows.return_value = self._mock_windows
        mock_sublime.active_window.return_value = self._mock_windows[0]
        mock_sublime.set_timeout_async.side_effect = lambda c, t: c()

        mock_indexers = [MagicMock(indexer.Indexer) for n in range(len(self._mock_windows))]
        # Return a unique mock instance for each call to indexer.Indexer()
        mock_indexer.side_effect = mock_indexers

        indexer.refresh()

        # sanity check
        for i, win in enumerate(self._mock_windows):
            ind = indexer._indexers[win.project_file_name()]['indexer']
            self.assertIs(ind, mock_indexers[i])

        new_config_mock = MagicMock(indexer.IndexerConfig)
        mock_config.return_value = new_config_mock
        new_config_mock.__eq__.return_value = False
        new_config_mock.__ne__.return_value = True

        for mock_ind in mock_indexers:
            mock_ind.reset_mock()

        # Fake an event that a project file was modified
        indexer.buffer_promoted(self._mock_windows[1].project_file_name())

        for i, mock_ind in enumerate(mock_indexers):
            calls = {(name, args) for name, args, _ in mock_ind.mock_calls}
            calls = calls - set( (('start', ()),) )

            # Only indexer corresponding to the modified project should
            # get a new config
            if i == 1:
                self.assertTrue(('set_config', (new_config_mock,)) in calls)
            else:
                self.assertEqual(0, len(calls))

