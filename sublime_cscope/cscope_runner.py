import os
import subprocess

import sublime

from ..SublimeCscope import DEBUG, PACKAGE_NAME
from . import settings
from .indexer import PRIMARY_DB, SECONDARY_DB
from .cscope_results import CscopeBuildDbResult, CscopeQueryResult, CscopeResultLimitException

CSCOPE_FILE_LIST_EXT = 'files'
CSCOPE_DB_EXT = 'out'

CSCOPE_OPTIONS = {
    'build_db_only': '-b',
    'query_only': '-d',
    'db_name' : '-f',
    'inc_dir' : '-I',
    'file_list': '-i',
    'kernel_mode': '-k',
    'line_mode_search': '-L',
    'fast_index': '-q',
    'force_db_rebuild': '-u',
    'verbose': '-v',
    'find_symbol': '-0',
    'find_definition': '-1',
    'find_callees': '-2',
    'find_callers': '-3',
    'find_string': '-4',
    'find_egrep_pattern': '-6',
    'find_files_including': '-8'
}

class CscopeRunner:
    def __init__(self, cwd, win, results, arg_list):
        self._win = win
        self._cwd = cwd
        self._results = results
        self._arg_list = arg_list


    @property
    def _cscope(self):
        def is_exe(f):
            if not os.path.exists(f):
                return False
            if not os.path.isfile(f):
                return False
            if not os.access(f, os.X_OK):
                print("%s: Found cscope candidate: %s but it is not an executable" %
                    (PACKAGE_NAME, f))
                return False
            return True

        cscope = settings.get('cscope_path', self._win)

        if cscope and is_exe(cscope):
            return cscope

        path_env = os.defpath
        if os.environ['PATH']:
            path_env = os.environ['PATH']

        for path in os.environ['PATH'].split(os.pathsep):
            cscope = os.path.join(path, 'cscope')
            if 'nt' == os.name:
                cscope = os.extsep.join([cscope, 'exe'])
            if is_exe(cscope):
                if DEBUG: print("Saving %s in settings" % cscope)
                # save it for later since it will most likely not change
                settings.load_settings().set('cscope_path', cscope)
                return cscope

        raise FileNotFoundError("cscope executable not found in PATH")

    def run(self):
        cmd = [self._cscope]
        env = {}

        if not self._cwd:
            print("%s-CscopeRunner: No working directory given. Aborting")
            return

        tmp_folder = settings.get('tmp_folder', self._win)
        kernel_mode = not bool(settings.get('search_std_include_folders', self._win))
        extra_inc_folders = settings.get('extra_include_folders', self._win)

        if tmp_folder:
            env['TMPDIR'] = tmp_folder

        if kernel_mode:
            cmd.append(CSCOPE_OPTIONS['kernel_mode'])

        for folder in extra_inc_folders:
            cmd.extend([CSCOPE_OPTIONS['inc_dir'], folder])

        cmd.extend(self._arg_list)

        if DEBUG: print("%s-CscopeRunner: About to run %s" % (PACKAGE_NAME, cmd))
        try:
            with subprocess.Popen(cmd, cwd=self._cwd,
                                  universal_newlines=True,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT) as p:
                for line in p.stdout:
                    if not line:
                        continue
                    self._results.parse(line)

        except subprocess.CalledProcessError as e:
            print("%s: Running cscope returned an error. cmd_line: %s, cwd: %s, error_code: %d"
                               % (PACKAGE_NAME,  e.cmd, self._cwd, e.returncode))
        except CscopeResultLimitException as le:
            sublime.error_message(str(le))
        finally:
            self._results.parse(None)



class CscopeBuildDbCommand:

    def __init__(self, cwd, win=None, force_rebuild=False, name=SECONDARY_DB):
        if not win:
            win = sublime.active_window()

        args = []

        file_list = os.extsep.join([name, CSCOPE_FILE_LIST_EXT])
        db_name = os.extsep.join([name, CSCOPE_DB_EXT])

        args.append(CSCOPE_OPTIONS['build_db_only'])
        args.append(CSCOPE_OPTIONS['fast_index'])
        args.append(CSCOPE_OPTIONS['verbose'])
        args.append("%s%s" % (CSCOPE_OPTIONS['file_list'], file_list))
        args.append("%s%s" % (CSCOPE_OPTIONS['db_name'], db_name))

        if force_rebuild:
            args.append(CSCOPE_OPTIONS['force_db_rebuild'])

        self._results = CscopeBuildDbResult()

        self._runner = CscopeRunner(cwd, win, self._results, args)


    @property
    def results(self):
        return self._results

    def run(self):
        self._runner.run()



class CscopeQueryCommand:

    def __init__(self, action, search_term, win=None):
        self._win = win
        if not self._win:
            self._win = sublime.active_window()

        from .indexer import get_db_location

        self._cwd = get_db_location(win)
        self._results = CscopeQueryResult(settings.get('maximum_results', self._win))
        self._action = action
        self._search_term = search_term


    def _run_once(self, db_name, file_list=None, filter=None):
        args = []

        if file_list:
            args.append("%s%s" % (CSCOPE_OPTIONS['file_list'], file_list))
        else:
            args.append(CSCOPE_OPTIONS['query_only'])

        args.append(CSCOPE_OPTIONS['line_mode_search'])
        args.append("%s%s" % (CSCOPE_OPTIONS[self._action], self._search_term))
        args.append("%s%s" % (CSCOPE_OPTIONS['db_name'], db_name))

        if filter:
            self._results.filter = filter

        runner = self._runner = CscopeRunner(self._cwd, self._win, self._results, args)
        runner.run()


    @property
    def results(self):
        return self._results


    def run(self):

        file_list = os.extsep.join([PRIMARY_DB, CSCOPE_FILE_LIST_EXT])
        db_name = os.extsep.join([PRIMARY_DB, CSCOPE_DB_EXT])
        file_filter = []

        file_list_path_name = os.path.join(self._cwd, file_list)

        if os.path.isfile(file_list_path_name):
            if DEBUG:
                print("CscopeQueryCommand: querying primary DB")

            with open(file_list_path_name) as f:
                file_filter = filter(bool, [line.strip() for line in f])

            self._run_once(db_name, file_list=file_list)


        db_name = os.extsep.join([SECONDARY_DB, CSCOPE_DB_EXT])

        if os.path.isfile(os.path.join(self._cwd, db_name)):
            if DEBUG:
                print("CscopeQueryCommand: querying secondary DB")

            self._run_once(db_name, filter=file_filter)



def generate_index(cwd, win, force_rebuild=False):
    build_db_command = CscopeBuildDbCommand(cwd, win=win, force_rebuild=force_rebuild)
    build_db_command.run()
    return build_db_command.results
