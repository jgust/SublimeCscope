import re
import os.path

import sublime

from ..SublimeCscope import DEBUG, PACKAGE_NAME

DB_BUILD_PROGRESS_RE = r"^> Building symbol database (\d+) of (\d+)$"
QUERY_RE =  r"^(\S+)\s+(\S+)?\s*(\d+)\s+(.*)$"

# Used when sorting results, see below
OUT_OF_SUBTREE_CONSTANT = 2**31

# Results to buffer constants
RTB_FILENAME = 'Find Results'
RTB_SYNTAX_FILE = os.path.join('Packages', 'Default', 'Find Results.hidden-tmLanguage')

RESULT_LIMIT_MSG = ("The CScope query generated too many results. "
                    "Please refine your search or increase the maximum "
                    "result limit in SublimeCscope's settings.")

class CscopeResultLimitException(Exception):
    def __init__(self):
        super().__init__(RESULT_LIMIT_MSG)

class CscopeResultsToBuffer:

    @staticmethod
    def generate_results(action, search_term, results, win=None):

        if not win:
            win = sublime.active_window()

        found_buffers = [v for v in win.views()
                            if v.name() == RTB_FILENAME and v.is_scratch()]

        if not found_buffers:
            view = win.new_file()
            def wait_for_load():
                if view.is_loading():
                    sublime.set_async_timeout(wait_for_load, 10)

                view.set_scratch(True)
                view.set_name(RTB_FILENAME)
                view.set_syntax_file(RTB_SYNTAX_FILE)

                view.settings().set('line_numbers', False)
            wait_for_load()
        else:
            view = found_buffers.pop()
            win.focus_view(view)
            view.set_viewport_position(view.layout_extent(), False)

        view.run_command('sc_write_query_results',
                        {'action': action, 'search_term': search_term, 'results': results})



class CscopeResultsToQuickPanel:

    @staticmethod
    def generate_results(action, search_term, results, win=None):
        qp_results = []
        highlighted_view = None

        if not win:
            win = sublime.active_window()

        def on_highlighted_cb(index):
            if index < 0 or index > (len(results) - 1):
                return

            file_name = (results[index][0] + ":{:d}").format(results[index][1])
            highlighted_view = win.open_file(file_name,
                                             sublime.ENCODED_POSITION | sublime.TRANSIENT)


        def on_done_cb(index):
            if index < 0 or index > (len(results) - 1):
                return
            file_name = results[index][0]
            tmp_view = win.find_open_file(file_name)

            if tmp_view != highlighted_view:
                tmp_view = win.open_file((file_name + ":{:d}").format(results[index][1]),
                                         sublime.ENCODED_POSITION | sublime.TRANSIENT)

            if action == 'find_callees':
                goto_word = results[index][2]
            else:
                goto_word = search_term

            curr_pos = tmp_view.text_point(results[index][1] - 1, 0)
            new_pos = tmp_view.find(goto_word, curr_pos).a
            if new_pos > curr_pos:
                sel = tmp_view.sel()
                sel.clear()
                sel.add(new_pos)

        folders = win.folders()
        folders = [folder.rstrip(os.path.sep) for folder in folders]

        if len(folders) > 1:
            # If there are multiple base level folders open
            # we need to keep the base_name of each folder
            folders = [os.path.dirname(p) for p in folders]
            #remove duplicates
            folders = set(folders)


        for (fn, ln, func, txt) in results:
            tmp_fn = fn
            for folder in folders:
                if fn.startswith(folder):
                    tmp_fn = fn[len(folder + os.path.sep):]
            qp_results.append(['{}:{:d}'.format(tmp_fn, ln),'{}: {}'.format(func, txt)])

        if qp_results:
            win.show_quick_panel(qp_results, on_done_cb,
                                 0, 0, on_highlighted_cb)


class CscopeResult:
    def __init__(self, regexp):
        self._re = regexp

    def parse(self, line):
        if not line:
            self._post_process_results()
        else:
            m = self._re.match(line)
            if m:
                self._parse_matched_line(m)
            elif DEBUG:
                print("CscopeResult: Got unmatched line: %s" % line)


    def _parse_matched_line(self, m):
        raise NotImplementedError()


    def _post_process_results(self):
        raise NotImplementedError()



class CscopeBuildDbResult(CscopeResult):
    INDEXING_MESSAGE = "Cscope indexing %d%%"
    def __init__(self):
        regexp = re.compile(DB_BUILD_PROGRESS_RE)
        super().__init__(regexp)

    def _parse_matched_line(self, m):
        try:
            current = int(m.group(1))
            total = int(m.group(2))

            if total > 0:
                percent = round(current / total * 100)
                sublime.status_message(CscopeBuildDbResult.INDEXING_MESSAGE % percent)
        except ValueError:
            print("%s: Failed to convert progress strings to integers" % PACKAGE_NAME)

    def _post_process_results(self):
        sublime.status_message(CscopeBuildDbResult.INDEXING_MESSAGE % 100)



class CscopeResultSortHelper():
    def __init__(self, sort_by_file):
        self._path = os.path.dirname(sort_by_file)
        self._base = os.path.basename(sort_by_file)


    def get_key(self, item):
        """
        We want to sort the results so that the first results to show up
        are those in the same folder as the file we queried from. Next
        are those that reside in a subfolder of said folder. Finally show
        those that are outside of the subtree where the query was made.
        Results that are equal in the first criteria are then sorted by
        filename and finally by line number.
        """
        file_name, line, _, _ = item
        path = os.path.dirname(file_name)
        base = os.path.basename(file_name)

        common_prefix = os.path.commonprefix((self._path, path))
        if common_prefix == self._path:
            base_key = len(path.strip(common_prefix))
            if base == self._base:
                base = '' # an empty string will be sorted first when sorting by name.
        else:
            # since they don't have a common subtree, we give it a large
            # number so that it gets sorted after those that are in the same subtree.
            # Those that are closest in the file tree get a lower ranking and thus
            # get sorted before those that are farther away.
            base_key = OUT_OF_SUBTREE_CONSTANT - len(common_prefix)
            # since the base key will be the same for many results that end up here
            # we need the full file name to use when sorting by name.
            base = file_name

        return (base_key, base, line)



class CscopeQueryResult(CscopeResult):

    def __init__(self, result_limit=-1):
        regexp = re.compile(QUERY_RE)
        super().__init__(regexp)
        self._results = {}
        self._filter = set()
        self._result_count = 0
        self._result_limit = result_limit


    def _parse_matched_line(self, m):
        self._result_count += 1

        if self._result_limit > 0 and self._result_count > self._result_limit:
            self._results.clear()
            raise CscopeResultLimitException()

        file_name = m.group(1)

        if file_name in self._filter:
            return

        func = m.group(2)
        line = int(m.group(3))
        line_text = m.group(4)

        self._results.setdefault(file_name, []).append((line, func, line_text))


    def _post_process_results(self):
        if DEBUG:
            print("Total results from Cscope query: %d" % self._result_count)


    def get_sorted_results(self, sort_by=None):

        results = [(file_name, line, func, text) for file_name, item in self._results.items()
                                                                    for line, func, text in item]

        if sort_by:
            sort_helper = CscopeResultSortHelper(sort_by)
            results.sort(key=sort_helper.get_key)

        return results

    @property
    def filter(self):
        return self._filter

    @filter.setter
    def filter(self, value):
        self._filter = set(value)




