
import os
import sys
import stat
import fnmatch
import threading
import traceback
from queue import Queue
from threading import Thread, Event
from collections import defaultdict
from functools import wraps, partial, reduce
from itertools import filterfalse, chain

import sublime

# The primary DB is indexed on the fly by cscope
# and can therefore only contain a limited amount of files
# before the indexing time becomes noticable. For projects of
# size up to TWO_TIER_THRESHOLD we keep all the files in the primary SB
PRIMARY_DB = 'primary'
# For projects larger than TWO_TIER_THRESHOLD, we use a two tier solution
# instead. The primary DB is still indexed on the fly but now only contains
# files that are open in the editor and have been modified since the last
# indexing run of the secondary DB.  The secondary DB will then contain all
# the files in the project, but will be indexed less frequently so it will
# most likely be out of date, for the files being modified. That is ok since
# the primary DB will hold up to date information for those files.
SECONDARY_DB = 'secondary'

from ..SublimeCscope import DEBUG, PACKAGE_NAME
from . import settings
from . import cscope_runner

DEBUG_DECORATORS = False
DEBUG_INDEXERCONFIG = False

DB_FOLDER_POSTFIX = '-' + PACKAGE_NAME.lower()

TWO_TIER_THRESHOLD = 50

# The global dict of indexers
# There should be one per project or workspace
_indexers = {}
_indexers_by_win = {}

class ActorQuit(Exception):
    pass

class UnhandledMessageException(Exception):
    pass

class ActorCommandMsg():
    def __init__(self, action, wait_for_result=False, result_callback=None):
        self._action = action
        self._result = Queue() if wait_for_result else None
        self._result_callback = result_callback

    def _set_result(self, result):
        if self._result:
            self._result.put(result)
        elif isinstance(result, Exception):
            raise result
        elif self._result_callback:
            self._result_callback(result)

    def result(self):
        if self._result:
            res = self._result.get()
            if isinstance(res, Exception):
                raise res
            return res
        else:
            return None

    def run(self):
        try:
            res = self._action()
        except Exception as e:
            res = e
        finally:
            self._set_result(res)

# Decorator that hides the details of sending messages to Actors
def send_msg(func):
    @wraps(func)
    def wrapper(self, *args, **kwds):
        result_cb = None
        is_sync = False
        send_always = False

        #make sure the Actor is started
        self.start()
        if not self._is_started():
            raise AssertionError("Actor %s is not running" % self.__class__)

        is_external = bool(self._thread_id and self._thread_id != threading.get_ident())

        #strip away any arguments aimed for the decorator
        if kwds:
            result_cb = kwds.pop('result_callback', None)
            is_sync = kwds.pop('wait_for_result', False)
            send_always = kwds.pop('send_always', False)

        #deadly combo, that will cause a deadlock in the actor
        if send_always and is_sync and not is_external:
            raise AssertionError("You can't send a message to yourself and wait for the result!")

        if send_always or is_external:
            action = lambda: func(self, *args, **kwds)
            msg = ActorCommandMsg(action, wait_for_result=is_sync, result_callback=result_cb)
            if DEBUG_DECORATORS:
                print("Sending %s msg: %s" % ('sync' if is_sync else 'async', func.__name__))
            self.send(msg)
            return msg.result()

        if DEBUG_DECORATORS: print("Calling %s directly" % func.__name__)
        return func(self, *args, **kwds)
    return wrapper

class ActorBase:
    def __init__(self):
        self._mailbox = Queue()
        self._started = Event()
        self._terminated = Event()
        self._thread_id = 0
        self.recv_count = 0

    def send(self, msg):
        self._mailbox.put(msg)

    def recv(self):
        msg = self._mailbox.get()
        self.recv_count += 1
        if msg is ActorQuit:
            raise ActorQuit()
        return msg

    def _close(self):
        self.send(ActorQuit)

    def _join(self):
        self._terminated.wait()

    def _bootstrap(self):
        try:
            self._thread_id = threading.get_ident()
            self._started.set()
            self._run()
        except ActorQuit:
            pass
        finally:
            self._thread_id = 0
            self._started.clear()
            self._terminated.set()


    def _run(self):
        while True:
            msg = self.recv()
            if isinstance(msg, ActorCommandMsg):
                msg.run()
            else:
                self.handle_message(msg)

    def _is_started(self):
        return self._started.is_set() and not self._terminated.is_set()

    def handle_message(self, msg):
        raise UnhandledMessageException(msg)

    def quit(self):
        self._close()
        self._join()

    def start(self):
        if self._is_started():
            return

        self._terminated.clear()
        t = Thread(target=self._bootstrap)
        t.daemon = True
        t.start()


class Indexer(ActorBase):
    """ The indexers maintains the cscope indexes
    The Indexer is responsible for maintaining an up-to-date
    cscope index of the project it is associated with.
    """

    def __init__(self):
        super().__init__()
        self._crawler = Crawler()
        self._crawl_in_progress = False
        self._partial_crawl_queue = []
        self._index_timestamp = None
        self._two_tier_mode = False
        self._file_index = {}
        self._promotion_set = set()
        self._demotion_set = set()
        self._config = None

    def start(self):
        super().start()
        self._crawler.start()

    def quit(self):
        self._crawler.quit()
        super().quit()

    def _reset_results(self):
        self._two_tier_mode = False
        self._partial_crawl_queue.clear()
        self._file_index.clear()
        self._promotion_set.clear()
        self._demotion_set.clear()

    def _count_files(self, file_index):
        return reduce(lambda tot, i: tot + len(i['files']), file_index.values(), 0)

    def _write_file_list(self, files, file_name):
        # Only try to create our own folder
        if not os.path.exists(os.path.dirname(file_name)):
            os.mkdir(os.path.dirname(file_name))

        with open(file_name, mode='wt', encoding='utf-8') as file_list:
            flist = ['"' + f + '"' if ' ' in f else f for f in files]
            flist.append('\n')
            file_list.write('\n'.join(flist))

    def _gen_index(self, full_update=True):
        success = False

        try:
            primary_list = os.path.join(self._config.db_location, PRIMARY_DB + '.files')
            secondary_list = os.path.join(self._config.db_location, SECONDARY_DB + '.files')

            #generate the file list
            files = []
            for v in self._file_index.values():
                if v['files']:
                    files.extend(map(lambda f: os.path.join(v['path'], f), v['files']))

            if self._two_tier_mode:
                if self._promotion_set:
                    self._write_file_list(self._promotion_set, primary_list)
                elif os.path.exists(primary_list):
                    os.remove(primary_list)

                if full_update:
                    self._write_file_list(files, secondary_list)
                    cscope_runner.generate_index(self._config.db_location,
                                                 _find_window_from_indexer(self))
            else:
                self._write_file_list(files, primary_list)
                if os.path.exists(secondary_list):
                    os.remove(secondary_list)

            success = True
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
            print("%s: Generating index for project: %s caused an exception")
            print(''.join('!! ' + line for line in lines))

        return success

    @send_msg
    def _perform_crawl(self, partial_crawl=False):
        start_path = None

        if not self._config or not self._config.is_complete:
            return

        if self._crawl_in_progress:
            print("Project: '%s' refresh is already in progress" % self._config.db_location)
            return
        elif partial_crawl:
            #try to find a starting point that includes all paths in
            #self._partial_crawl_queue
            start_path = os.path.commonprefix(self._partial_crawl_queue)
            if start_path.endswith(os.path.sep):
                start_path = start_path[:-1]

            if start_path and not os.path.exists(start_path):
                start_path = os.path.dirname(start_path)

            base_path, _ = self._config.find_base_path(start_path)
            if start_path and not base_path:
                start_path = None

        if DEBUG:
            if start_path:
                print("Performing partial refresh starting from %s for project: %s" %
                            (start_path, self._config.db_location))
            else:
                print("Performing full refresh for project: %s" % self._config.db_location)

        self._partial_crawl_queue.clear()
        self._crawl_in_progress = True
        self._crawler.crawl(self._config,
                            user_data=start_path,
                            start_path=start_path,
                            result_callback=self._crawl_result_ready)


    @send_msg
    def _crawl_result_ready(self, result):
        self._crawl_in_progress = False
        crawl_res, partial_update = result

        if DEBUG:
            print("Crawl results received. Found %d files" % self._count_files(crawl_res))

        if self._count_files(crawl_res) > TWO_TIER_THRESHOLD:
            if not self._two_tier_mode:
                if partial_update:
                    print("%s: A partial update of project: %s resulted in threshold exceeded. "
                          "Performing full update." %
                          (PACKAGE_NAME, os.path.dirname(self._config.db_location)))
                    self._perform_crawl()
                    return
                else:
                    if DEBUG: print("Threshold exceeded, switching to two tier mode")
                    self._reset_results()
                    self._two_tier_mode = True

        elif not partial_update and self._two_tier_mode:
                if DEBUG: print("%s: Project: %s. Project size is below threshold. "
                                "Reverting back to one tier mode" %
                               (PACKAGE_NAME, os.path.dirname(self._config.db_location)))
                self._reset_results()

        file_index = {}

        if partial_update:
            # Extract the relevant subset to compare
            for k, v in list(self._file_index.values()):
                if k['path'].startswith(partial_update):
                    file_index[k] = v
                    del self._file_index[k]
        else:
            file_index = self._file_index
            self._file_index = {}
            self._partial_crawl_queue.clear()
            partial_update = ''

        if (file_index != crawl_res):
            if DEBUG:
                print("Crawl of project: %s contained changes." %
                                    os.path.dirname(self._config.db_location))

            self._file_index.update(crawl_res)

            if self._gen_index():
                #remove files from the demotion list
                tmp = {f for f in self._demotion_set if f.startswith(partial_update)}
                self._demotion_set -= tmp
                self._promotion_set -= tmp

        # Perfrom any pending partial crawls
        if self._partial_crawl_queue:
            self._perform_crawl(True, send_always=True)

    @send_msg
    def refresh(self):
        self._perform_crawl()

    @send_msg
    def set_config(self, config):
        if config and config != self._config:
            if DEBUG: print("New config received. Refreshing project %s" % config.db_location)
            self._config = config
            self.refresh()

    @send_msg
    def promote_buffer(self, file_path):

        if file_path in self._promotion_set:
            return

        base, name = os.path.split(file_path)
        st = os.stat(base)

        if st.st_ino in self._file_index:
            # in case the folder exists in the index under a different name
            # use that name instead
            base = self._file_index[st.st_ino]['path']
            file_path = os.path.join(base, name)

        if file_path in self._promotion_set:
            return

        if not self._config.file_matches(base, name):
            return

        if DEBUG: print("Promoting: %s" % file_path)

        if self._two_tier_mode:
            self._promotion_set.add(os.path.join(base, name))
            self._gen_index(full_update=False)
        elif not name in self._file_index.get(st.st_ino, {}).get('files',[]):
            # file not found in index
            self._perform_crawl()

    @send_msg
    def demote_buffer(self, file_path):

        if file_path not in self._promotion_set:
            return

        if file_path in self._demotion_set:
            return

        if DEBUG: print("Demoting: %s" % file_path)
        self._demotion_set.add(file_path)
        self._partial_crawl_queue.append(dirname(file_path))
        self._perform_crawl(True, send_always=True)



class Crawler(ActorBase):
    """ The Crawler scans the project folders for files to index. """
    @send_msg
    def crawl(self, config, user_data, start_path=None):
        result = defaultdict(dict)

        if start_path:
            base_path, follow_syms = config.find_base_path(start_path)
            folders_to_search = [(start_path, base_path, follow_syms)]
        else:
            folders_to_search = [(base_path, base_path, follow_syms) for
                                     base_path, follow_syms in config.base_paths()]

        for start, base, follow_syms in folders_to_search:
            os_walk = partial(os.walk, followlinks=follow_syms)
            os_stat = partial(os.stat, follow_symlinks=follow_syms)
            file_matcher = partial(config.file_matches, base_path=base)
            folder_matcher = partial(config.folder_matches, base_path=base)
            visited_files = set()
            self._crawl_one_subfolder(start, result,
                                      os_walk, os_stat,
                                      file_matcher, folder_matcher,
                                      visited_files)

        return (result, user_data)

    def _crawl_one_subfolder(self, start_path, result, os_walk,
                             os_stat, file_matcher,
                             folder_matcher, visited_files):

        if DEBUG: print("Starting to crawl folder: %s" % start_path)
        prev = None
        prev_inode = 0

        for current, subdirs, files in os_walk(start_path):
            inode = prev_inode

            if current != prev:
                prev = current
                inode = os_stat(current).st_ino
                if inode in result:
                    AssertionError("Inode %d already seen. path: %s == %s" %
                                    (inode, current, result[inode]['path']))

                result[inode]['path'] = current
                result[inode]['magic'] = 0
                result[inode]['files'] = []

            self._process_files(current, files, result[inode],
                                os_stat, file_matcher, visited_files)
            self._process_subfolders(current, subdirs, os_stat,
                                     folder_matcher, result.keys())

    def _process_files(self, path, files, result,
                       os_stat, file_matcher, visited_files):

        for f in files:
            st = os_stat(os.path.join(path, f))

            if st.st_ino in visited_files:
                if DEBUG: print("File %s was already visited" % os.path.join(path, f))
                continue

            if file_matcher(path, f, st.st_mode):
                result['files'].append(f)
                result['magic'] += st.st_size + st.st_mtime
                visited_files.add(st.st_ino)


    def _process_subfolders(self, path, subdirs, os_stat,
                            folder_matcher, visited_folders):
        filtered_subdirs = []
        for d in subdirs:
            st = os_stat(os.path.join(path, d))

            if st.st_ino in visited_folders:
                if DEBUG: print("File %s was already visited" % os.path.join(path, d))
                continue

            if folder_matcher(path, d, st.st_mode):
                filtered_subdirs.append(d)

        subdirs.clear()
        subdirs.extend(filtered_subdirs)



class IndexerConfig():
    def __init__(self, window):
        self._is_complete = False
        self._file_exts = None
        self._db_location = get_db_location(window)

        if not self._db_location:
            return

        self._file_exts = _set_from_sorted_list(settings.get('index_file_extensions', window))
        if not self._file_exts:
            print("%s: The list of file extensions to index was empty. \
                        Please check your settings." % PACKAGE_NAME)
            return

        self._search_std_incl_folders = settings.get('search_std_include_folders', window)
        self._std_incl_folders = _set_from_sorted_list(settings.get('std_include_folders', window))
        self._folder_configs = {}
        self._index_blacklist = set()
        global_folder_exclude = []
        global_folder_include = []
        global_file_exclude = []
        global_file_include = []


        if window.active_view():
            s = window.active_view().settings()
            self._index_blacklist = _set_from_sorted_list(s.get('index_exclude_patterns', []))
            global_folder_exclude = s.get('folder_exclude_patterns', [])
            global_folder_include = s.get('folder_include_patterns', [])
            global_file_exclude = s.get('file_exclude_patterns', [])
            global_file_include = s.get('file_include_patterns', [])

        proj_data = window.project_data()

        for folder in proj_data['folders']:
            folder_path = folder['path']
            if not folder_path:
                next

            if not os.path.isabs(folder_path):
                base_path, _ = os.path.split(self._db_location)
                if DEBUG:
                    print("Found relative folder: %s. prepending %s" %
                                    (folder_path, base_path + os.path.sep))
                folder_path = os.path.join(base_path, folder_path)

            folder_config = {}
            folder_config['follow_symlinks'] = folder.get('follow_symlinks', True)
            folder_config['file_whitelist'] = _set_from_sorted_list(global_file_include + \
                                                        folder.get('file_include_patterns',[]))
            folder_config['file_blacklist'] = _set_from_sorted_list(global_file_exclude + \
                                                        folder.get('file_exclude_patterns',[]))
            folder_config['folder_whitelist'] = _set_from_sorted_list(global_folder_include + \
                                                        folder.get('folder_include_patterns',[]))
            folder_config['folder_blacklist'] = _set_from_sorted_list(global_folder_exclude + \
                                                        folder.get('folder_exclude_patterns',[]))

            self._folder_configs[folder_path] = folder_config

        # For the config to be consider complete (i.e. usable) we need at least
        # one file extention and one folder.
        self._is_complete = len(self._file_exts) > 0 and len(self._folder_configs) > 0

    @property
    def is_complete(self):
        return self._is_complete

    @property
    def file_exts(self):
        return self._file_exts

    @property
    def db_location(self):
        return self._db_location

    @property
    def search_std_incl_folders(self):
        return self._search_std_incl_folders

    @property
    def std_incl_folders(self):
        return self._std_incl_folders


    def __eq__(self, r):
        res = True

        if self is r:
            return True
        elif not isinstance(r, self.__class__):
            res = NotImplemented
        else:
            keys_to_cmp = [
                           '_is_complete',
                           '_db_location',
                           '_file_exts',
                           '_folder_configs',
                           '_index_blacklist',
                           '_search_std_incl_folders',
                           '_std_incl_folders'
                          ]
            ldict = self.__dict__
            rdict = r.__dict__

            results = list(filterfalse(lambda k: ldict.get(k, None) == rdict.get(k, None),
                                              keys_to_cmp))

            # if results is empty, all keys evaluated to equal
            res = bool(not results)

            if DEBUG_INDEXERCONFIG and not res:
                for key in results:
                    print("%s failed: '%s' != '%s'" %
                                    (key, ldict.get(key, None), rdict.get(key, None)))

        return res

    def __ne__(self, r):
        res = self.__eq__(r)

        if res is NotImplemented:
            return res

        return not res

    def _is_whitelisted_file(self, base_path, dirpath, file_name):
        _, ext = os.path.splitext(file_name)

        if not ext in self._file_exts:
            return False

        full_name = os.path.join(dirpath, file_name)
        include_patterns = self._folder_configs[base_path]['file_whitelist']

        # if the list is empty then all files are allowed
        if not include_patterns:
            return True

        for pattern in include_patterns:
            if fnmatch.fnmatch(file_name, pattern):
                return True

            if fnmatch.fnmatch(full_name, pattern):
                return True

        return False


    def _is_blacklisted_file(self, base_path, dirpath, file_name):
        exclude_patterns = self._folder_configs[base_path]['file_blacklist']

        # if the list is empty then all files are allowed
        if not exclude_patterns:
            return False

        full_name = os.path.join(dirpath, file_name)

        for pattern in exclude_patterns:
            if fnmatch.fnmatch(file_name, pattern):
                return True

            if fnmatch.fnmatch(full_name, pattern):
                return True

        for pattern in self._index_blacklist:
            if fnmatch.fnmatch(file_name, pattern):
                return True

            if fnmatch.fnmatch(full_name, pattern):
                return True

        return False

    def _is_whitelisted_folder(self, base_path, dirpath, folder):
        include_patterns = self._folder_configs[base_path]['folder_whitelist']

        # if the list is empty then all files are allowed
        if not include_patterns:
            return True

        full_path = os.path.join(dirpath, folder)

        for pattern in include_patterns:
            if fnmatch.fnmatch(folder, pattern):
                return True

            if fnmatch.fnmatch(full_path, pattern):
                return True

        return False

    def _is_blacklisted_folder(self, base_path, dirpath, folder):
        exclude_patterns = self._folder_configs[base_path]['folder_blacklist']

        # if the list is empty then all files are allowed
        if not exclude_patterns:
            return False

        full_path = os.path.join(dirpath, folder)

        for pattern in exclude_patterns:
            if fnmatch.fnmatch(folder, pattern):
                return True

            if fnmatch.fnmatch(full_path, pattern):
                return True

        for pattern in self._index_blacklist:
            if fnmatch.fnmatch(folder, pattern):
                return True

            if fnmatch.fnmatch(full_path, pattern):
                return True

        return False

    def find_base_path(self, dirpath):
        not_found = (None, None)

        if not dirpath:
            return not_found

        for bp in self._folder_configs.keys():
            if dirpath.startswith(bp):
                return (bp, self._folder_configs[bp]['follow_symlinks'])

        if DEBUG:
            print("No base path found for '%s' in (%s)" % (dirpath, self._folder_configs.keys()))
        return not_found


    def base_paths(self):
        return tuple((key, self._folder_configs[key]['follow_symlinks'])
                                        for key in self._folder_configs.keys())

    def file_matches(self, dirpath, file_name, st_mode=0, base_path=None):
        if not base_path:
            base_path, follow_symlinks = self.find_base_path(dirpath)
            if not base_path:
                return False

            st_mode = os.stat(os.path.join(dirpath, file_name),
                                follow_symlinks=follow_symlinks).st_mode

        if not stat.S_ISREG(st_mode):
            return False

        if not self._is_whitelisted_file(base_path, dirpath, file_name):
            return False

        if self._is_blacklisted_file(base_path, dirpath, file_name):
            return False

        return True


    def folder_matches(self, dirpath, folder, st_mode=0, base_path=None):
        if not base_path:
            base_path, follow_symlinks = self.find_base_path(dirpath)
            if not base_path:
                return False

            st_mode = os.stat(os.path.join(dirpath, file_name), follow_symlinks=follow_symlinks)

        if not stat.S_ISDIR(st_mode):
            return False

        if not self._is_whitelisted_folder(base_path, dirpath, folder):
            return False

        if self._is_blacklisted_folder(base_path, dirpath, folder):
            return False

        return True


def _get_proj_name(view_or_window):
    proj_name = None
    win = view_or_window

    if hasattr(view_or_window, 'window'):
        win = view_or_window.window()

    # we are only interested in windows with folders open
    if win and win.folders():
        proj_name = win.project_file_name()
        # if the window doesn't have a proj_name, generate a dummy_one
        if not proj_name:
            proj_name = os.path.join(sublime.cache_path(),
                                     PACKAGE_NAME,
                                     'tmp_index_' + win.id(),
                                     'dummy_project.txt')
    return proj_name

def _set_from_sorted_list(l):
    if not l:
        return set()

    l.sort()
    return set(l)

def _disassociate_window(proj_file, win):
    indexer_data = _indexers.get(proj_file, None)
    if indexer_data:
        indexer_data['windows'].remove(win)
        if not indexer_data['windows']:
            return True
    return False

def _trim_indexers():
    for key, indexer_data in list(_indexers.items()):
        # remove indexers that are not associated with any windows
        if not indexer_data['windows']:
            indexer = _indexers.pop(key)['indexer']
            indexer.quit()

def _find_window_from_proj_file(proj_file):
    win = None

    if proj_file in _indexers:
        indexer_data = _indexers[proj_file]
        windows = [w for w in sublime.windows() if w.id() in indexer_data['windows']]
        if windows:
            win = windows[0]

    return win

def _find_window_from_indexer(indexer):
    win = None

    for proj_file, indexer_data in _indexers.items():
        if indexer is indexer_data['indexer']:
            win = _find_window_from_proj_file(proj_file)

    return win

# The module level API
def get_db_location(win):
    if not win:
        return None

    proj_name = _get_proj_name(win)

    if not proj_name:
        return None

    path, name_ext = os.path.split(proj_name)

    if not os.path.exists(path):
        print("%s: Path: %s does not exist. Will not attempt to index project: %s"
                        % (PACKAGE_NAME, path, proj_name))
        return None

    name, ext = os.path.splitext(name_ext)

    db_location = os.path.join(path, name + DB_FOLDER_POSTFIX)
    if os.path.isfile(db_location):
        print("%s: Path: %s already exists but is not a folder. \
            Will not attempt to index project: %s" % (PACKAGE_NAME, db_location, proj_name))
        return None

    return db_location


def refresh(win=None, explicit_refresh=True):
    """
    Refresh the file tree of the indexer belonging to window
    if win is None refresh all indexers.
    """
    windows = [win] if win else sublime.windows()
    indexer_win_pair = [(_get_proj_name(win), win) for win in windows
                        if _get_proj_name(win)]

    for proj_file, win in indexer_win_pair:
        # in case the window is being reused with a new project,
        # disassociate from the old project
        if win.id() in _indexers_by_win and _indexers_by_win[win.id()] != proj_file:
            _disassociate_window(_indexers_by_win[win.id()], win.id())

        indexer_data = _indexers.setdefault(proj_file, {})
        indexer = indexer_data.setdefault('indexer', Indexer())
        indexer_cfg = IndexerConfig(win)
        if indexer_cfg != indexer_data.get('config', None):
            # Since there is a change in the config
            # The indexer will do an implicit refresh
            explicit_refresh = False
            indexer.set_config(indexer_cfg)
            indexer_data['config'] = indexer_cfg

        indexer_windows = indexer_data.setdefault('windows', [])
        if not win.id() in indexer_windows:
            indexer_windows.append(win.id())

        _indexers_by_win[win.id()] = proj_file

        indexer.start()

        if explicit_refresh:
            indexer.refresh()


def buffer_promoted(file_path):
    """
    The file located at 'file_path' has been opened and modified and should
    therefore be promoted to the indexers' active list.
    """

    # Special case were the file is a project file
    if file_path in _indexers:
        sublime.set_timeout_async(lambda: settings_changed(file_path), 1000)
        return

    # Notify all indexers that the buffer should be promoted
    # The indexers will ignore this call if the buffer doesn't belong to their
    # project
    for indexer_data in _indexers.values():
        indexer_data['indexer'].promote_buffer(file_path)

    if DEBUG: print("buffer_promoted: '%s'" % file_path)


def buffer_demoted(file_path):
    """
    The file located at 'file_path' has been closed and should therefore
    be demoted to the indexers' passive list.
    """
    #ignore any project files being closed
    if file_path in _indexers:
        return

    for indexer_data in _indexers.values():
        indexer_data['indexer'].demote_buffer(file_path)


def window_state_changed():
    """
    Called every time there is a significant state change in the currently
    open windows and we need to take action.
    """

    # look for any indexers to close
    curr_windows = {win.id() for win in sublime.windows()}
    old_windows = _indexers_by_win.keys()

    obsolete_windows = old_windows - curr_windows
    for key in obsolete_windows:
        proj_file = _indexers_by_win.pop(key)
        _disassociate_window(proj_file, key)

    # implicitly refresh all active windows
    refresh(explicit_refresh=False)

    # Remove orphan indexers
    _trim_indexers()


def settings_changed(proj_file=None):
    """
    Called each time our settings object
    (or project file) has been modified
    """

    if proj_file and proj_file in _indexers:
        # A specific project file was modified.
        # Notify the indexer if the config differs.
        indexer_data = _indexers[proj_file]
        indexer = indexer_data['indexer']
        config = indexer_data['config']
        win = _find_window_from_proj_file(proj_file)
        if not win:
            return
        new_config = IndexerConfig(win)
        if new_config != config:
           indexer.set_config(new_config)
           indexer_data['config'] = new_config

    else:
        # implicitly refresh all active windows
        refresh(explicit_refresh=False)


def quit():
    """Closes all indexers and removes them."""

    _indexers_by_win.clear()
    for indexer_data in _indexers.values():
        indexer_data.setdefault('windows',[]).clear()

    _trim_indexers()
