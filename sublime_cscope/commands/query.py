import linecache as lc
import functools
import math
import os

import sublime
import sublime_plugin

from ...SublimeCscope import DEBUG, PACKAGE_NAME
from ..cscope_runner import CscopeQueryCommand
from ..cscope_results import CscopeResultsToBuffer, CscopeResultsToQuickPanel


# Results to buffer constants
RTB_CSCOPE_ACTIONS = {
                        'find_symbol': 'the symbol{}',
                        'find_definition': 'the definition of{}',
                        'find_callees': 'functions called by{}',
                        'find_callers': 'functions calling{}',
                        'find_string': 'the occurrences of string{}',
                        'find_egrep_pattern': 'the occurrences of egrep pattern{}',
                        'find_files_including': 'files #including{}'
                     }

RTB_HEADER = PACKAGE_NAME + ' results for {}\n'

RTB_MATCH_OR_MATCHES = ['match', 'matches']
RTB_IN_OR_ACCROSS = ['in', 'across']
RTB_FOOTER = '\n{0:d} {2} {3} {1:d} files\n'
RTB_LINE_PREFIX = '{0:>5}'
RTB_PRE_POST_MATCH = RTB_LINE_PREFIX + '  {1}'
RTB_MATCH = RTB_LINE_PREFIX + ': {1}'
RTB_CONTEXT_LINES = 2

class ScQueryCommand(sublime_plugin.TextCommand):

    @property
    def action(self):
        raise NotImplementedError()


    @property
    def search_term(self):
        if len(self.view.sel()) != 1:
            return None

        s = self.view.sel()[0]
        if s.b == s.a:
            selected_word_reg = self.view.word(self.view.sel()[0])
        else:
            selected_word_reg = s
        selected_word = self.view.substr(selected_word_reg).strip()
        return selected_word

    def is_enabled(self):
        from ..indexer import get_db_location

        return bool(get_db_location(self.view.window()))

    def run_with_input(self, input_str, results_to_buffer=False):
        if input_str:
            query_command = CscopeQueryCommand(self.action, input_str, win=self.view.window())
            query_command.run()

            results = query_command.results.get_sorted_results(sort_by=self.view.file_name())

            if not results:
                return

            if results_to_buffer:
                CscopeResultsToBuffer.generate_results(self.action,
                                                       input_str,
                                                       results,
                                                       win=self.view.window())
            else:
                CscopeResultsToQuickPanel.generate_results(self.action,
                                                           input_str,
                                                           results,
                                                           win=self.view.window())
        else:
            print(PACKAGE_NAME + ' -  Unable to run query since no input was given.')

    def run_in_background(self, input_str, rtb=False):
        runner_lambda = lambda: self.run_with_input(input_str, results_to_buffer=rtb)
        sublime.set_timeout_async(runner_lambda, 5)


    def run(self, edit, results_to_buffer=False):

        search_term = self.search_term
        run_cb = functools.partial(self.run_in_background, rtb=results_to_buffer)

        if search_term:
            run_cb(search_term)
        else:
            panel_text = (PACKAGE_NAME + ' - Find ' + RTB_CSCOPE_ACTIONS[self.action]).format(':')
            self.view.window().show_input_panel(panel_text, '', run_cb, None, None)



class ScFindSymbolCommand(ScQueryCommand):
    @ScQueryCommand.action.getter
    def action(self):
        return 'find_symbol'



class ScFindDefinitionCommand(ScQueryCommand):
    @ScQueryCommand.action.getter
    def action(self):
        return 'find_definition'



class ScFindCalleesCommand(ScQueryCommand):
    @ScQueryCommand.action.getter
    def action(self):
        return 'find_callees'



class ScFindCallersCommand(ScQueryCommand):
    @ScQueryCommand.action.getter
    def action(self):
        return 'find_callers'



class ScFindStringCommand(ScQueryCommand):
    @ScQueryCommand.action.getter
    def action(self):
        return 'find_string'



class ScFindEgrepPatternCommand(ScQueryCommand):
    @ScQueryCommand.action.getter
    def action(self):
        return 'find_egrep_pattern'



class ScFindFilesIncludingCommand(ScQueryCommand):
    @ScQueryCommand.action.getter
    def action(self):
        return 'find_files_including'


    @ScQueryCommand.search_term.getter
    def search_term(self):
        st = super().search_term

        if not st:
            return st

        if st.startswith('#include'):
            st = st[len('#include'):]
        st = st.lstrip(' "<').rstrip(' ">')

        root, ext = os.path.splitext(st)
        if not ext:
            st = os.extsep.join([st, 'h'])

        if DEBUG:
            print("Querying for h-file: %s" % st)
        return st


class ScWriteQueryResultsCommand(sublime_plugin.TextCommand):
    """
    Internal command that writes query results to the Results buffer.
    """
    def run(self, edit, action='', search_term='', results=[]):

        start_pos = self.view.size()
        current_pos = start_pos
        regions = []
        highlight_search_term = (action != 'find_callees')

        current_pos = self.write_header(edit, current_pos, action, search_term)

        prev_file = None
        prev_line = 0
        file_count = 0

        for res in results:
            tmp_file = prev_file
            prev_file, prev_line, current_pos, result_pos = self.write_result(edit, current_pos,
                                                                              prev_file, prev_line,
                                                                              res)
            if tmp_file != prev_file:
                file_count += 1

            if result_pos > 0:
                if highlight_search_term:
                    reg = self.view.find(search_term, result_pos)
                else:
                    _, _, func, _ = res
                    reg = self.view.find(func, result_pos)

                if reg:
                    regions.append(reg)

        current_pos = self.write_context_lines(edit, current_pos, prev_file,
                                               prev_line+1, RTB_CONTEXT_LINES)
        current_pos = self.write_footer(edit, current_pos, len(results), file_count)

        all_regions = self.view.get_regions(PACKAGE_NAME)
        all_regions.extend(regions)

        if all_regions:
            self.view.add_regions(PACKAGE_NAME, all_regions, 'text', '', sublime.DRAW_NO_FILL)


    def write_header(self, edit, pos, action, search_term):
        search_term_str = ' "' + search_term + '"'
        header = RTB_HEADER.format(RTB_CSCOPE_ACTIONS[action].format(search_term_str))
        if pos > 0:
            header = '\n' + header
        return pos + self.view.insert(edit, pos, header)


    def write_footer(self, edit, pos, results_total, files_total):
        footer = RTB_FOOTER.format(results_total, files_total,
                                   RTB_MATCH_OR_MATCHES[int(results_total > 1)],
                                   RTB_IN_OR_ACCROSS[int(files_total > 1)])
        return pos + self.view.insert(edit, pos, footer)


    def write_context_lines(self, edit, pos, file_name,
                            start_line, num_ctx_lines = RTB_CONTEXT_LINES):
        if num_ctx_lines > 0:
            for line_num in range(start_line, start_line + num_ctx_lines):
                line = lc.getline(file_name, line_num)
                if line:
                    pos += self.view.insert(edit, pos, RTB_PRE_POST_MATCH.format(line_num, line))
        return pos

    def write_result(self, edit, pos, prev_file, prev_line, result):
        fn, ln, func, _ = result

        if fn != prev_file:
            lc.checkcache(fn)
            prev_line = 0
            pos += self.view.insert(edit, pos, '\n{}:\n'.format(fn))

        matched_line = lc.getline(fn,ln)
        result_pos = 0

        if not matched_line:
            print("{} Could not find line {:d} in file {}" +
                  " while writing results to buffer.".format(PACKAGE_NAME, ln, fn))
            return (fn, ln, pos, result_pos)

        line_diff = ln - prev_line - 1
        if prev_line > 0:
            if line_diff > RTB_CONTEXT_LINES:
                pos = self.write_context_lines(edit, pos, fn, prev_line + 1)

                seperator_dots = math.ceil(math.log(ln, 10))
                sep = (RTB_LINE_PREFIX + '\n').format('.' * seperator_dots)
                pos += self.view.insert(edit, pos, sep)

        ctx_lines = min(line_diff, RTB_CONTEXT_LINES)
        pos = self.write_context_lines(edit, pos, fn, ln - ctx_lines, ctx_lines)


        result_pos = pos
        pos += self.view.insert(edit, pos, RTB_MATCH.format(ln, matched_line))

        return (fn, ln, pos, result_pos)









