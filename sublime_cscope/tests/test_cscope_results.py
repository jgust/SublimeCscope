import os
import unittest
from unittest.mock import call, patch, MagicMock

import sublime

from ..cscope_results import CscopeQueryResult, CscopeResultsToQuickPanel, CscopeResultsToBuffer


_results_package_path = 'SublimeCscope.sublime_cscope.cscope_results'
_sublime_to_mock = _results_package_path + '.sublime'


TEST_INPUT = [
    "/proj_root/subdir1/utils/util_package1/util_package_file1.c my_symbol 55 SymbolType my_symbol;",
    "/proj_root/subdir1/package1/srcfile1.c my_symbol 22 SymbolType *my_symbol;",
    "/proj_root/subdir1/package1/srcfile2.c my_symbol 42 SymbolType *my_symbol;",
    "/proj_root/subdir1/package1/srcfile3.c my_symbol 38 SymbolType *my_symbol;",
    "/proj_root/subdir1/package1/srcfile4.c my_symbol 38 SymbolType *my_symbol;",
    "/proj_root/subdir1/package1/hdrfile4.h my_symbol 24 SymbolType *my_symbol;",
    "/proj_root/subdir1/package1/srcfile5.c my_symbol 216 SymbolType *my_symbol;",
    "/proj_root/subdir1/package1/srcfile5.c my_symbol 223 SymbolType *my_symbol;",
    "/proj_root/subdir1/package1/srcfile5.c my_symbol 246 SymbolType *my_symbol;",
    "/proj_root/subdir1/package1/hdrfile5.h my_symbol 52 typedef gboolean (*func_ptr_type1)(SymbolType *my_symbol,",
    "/proj_root/subdir1/package1/hdrfile6.h my_symbol 32 void (*func_ptr_type2)(SymbolType *my_symbol, struct APIRequest *req);",
    "/proj_root/subdir1/package1/hdrfile6.h my_symbol 34 void (*func_ptr_type3)(SymbolType *my_symbol,",
    "/proj_root/subdir1/package1/hdrfile6.h my_symbol 38 void (*func_ptr_type4)(SymbolType *my_symbol,",
    "/proj_root/subdir1/package1/hdrfile6.h my_symbol 43 gboolean (*func_ptr_type5)(SymbolType *my_symbol,",
    "/proj_root/subdir1/package1/hdrfile6.h my_symbol 48 gboolean (*func_ptr_type6)(SymbolType *my_symbol,",
    "/proj_root/subdir1/package1/hdrfile6.h my_symbol 53 gboolean (*func_ptr_type7)(SymbolType *my_symbol,",
    "/proj_root/subdir1/package1/hdrfile6.h my_symbol 58 int (*func_ptr_type8)(SymbolType *my_symbol,",
    "/proj_root/subdir1/package1/hdrfile6.h my_symbol 61 int function1(SymbolType *my_symbol,",
    "/proj_root/subdir1/package1/hdrfile6.h my_symbol 64 void function2(SymbolType *my_symbol,",
    "/proj_root/subdir1/package1/hdrfile6.h my_symbol 67 void function3(SymbolType *my_symbol,",
    "/proj_root/subdir1/package2/subdir2/srcfile7.c my_symbol 50 static SymbolType2 *my_symbol;",
    "/proj_root/subdir1/package2/hdrfile7.h my_symbol 24 SymbolType2 *my_symbol;",
    "/proj_root/subdir1/package3/tests/hdrfile8.h my_symbol 11 SymbolType2 *my_symbol;",
    "/proj_root/subdir1/package3/srcfile1.c my_symbol 34 SymbolType *my_symbol;",
    "/proj_root/subdir1/package3/hdrfile1.h my_symbol 10 SymbolType *my_symbol;",
    "/proj_root/subdir1/package4/src/subdir/srcfile3.c my_symbol 71 SymbolType3 my_symbol;",
    "/proj_root/subdir2/package5/lib/srcfile6.c my_symbol 287 SymbolType5 *my_symbol;",
    "/proj_root/subdir2/package6/tests/testfile1.c my_symbol 54 gboolean my_symbol;",
    "/proj_root/subdir2/package7/lib/hdrfile2.h my_symbol 343 some_type2 my_symbol;",
    "/proj_root/subdir2/package8/sub1/sub2/src/inc/hdrfile1.h my_symbol 201 some_type3 my_symbol;"
]

EXPECTED_OUTPUT = [
    ("/proj_root/subdir1/utils/util_package1/util_package_file1.c", 55, "my_symbol", "SymbolType my_symbol;"),
    ("/proj_root/subdir1/package1/srcfile1.c", 22 , "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package1/srcfile2.c", 42 , "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package1/srcfile3.c", 38 , "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package1/srcfile4.c", 38 , "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package1/hdrfile4.h", 24 , "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package1/srcfile5.c", 216, "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package1/srcfile5.c", 223, "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package1/srcfile5.c", 246, "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package1/hdrfile5.h", 52 , "my_symbol", "typedef gboolean (*func_ptr_type1)(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 32 , "my_symbol", "void (*func_ptr_type2)(SymbolType *my_symbol, struct APIRequest *req);"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 34 , "my_symbol", "void (*func_ptr_type3)(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 38 , "my_symbol", "void (*func_ptr_type4)(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 43 , "my_symbol", "gboolean (*func_ptr_type5)(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 48 , "my_symbol", "gboolean (*func_ptr_type6)(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 53 , "my_symbol", "gboolean (*func_ptr_type7)(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 58 , "my_symbol", "int (*func_ptr_type8)(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 61 , "my_symbol", "int function1(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 64 , "my_symbol", "void function2(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 67 , "my_symbol", "void function3(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package2/subdir2/srcfile7.c", 50, "my_symbol", "static SymbolType2 *my_symbol;"),
    ("/proj_root/subdir1/package2/hdrfile7.h", 24, "my_symbol", "SymbolType2 *my_symbol;"),
    ("/proj_root/subdir1/package3/tests/hdrfile8.h", 11, "my_symbol", "SymbolType2 *my_symbol;"),
    ("/proj_root/subdir1/package3/srcfile1.c", 34, "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package3/hdrfile1.h", 10, "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package4/src/subdir/srcfile3.c", 71, "my_symbol", "SymbolType3 my_symbol;"),
    ("/proj_root/subdir2/package5/lib/srcfile6.c", 287, "my_symbol", "SymbolType5 *my_symbol;"),
    ("/proj_root/subdir2/package6/tests/testfile1.c", 54, "my_symbol", "gboolean my_symbol;"),
    ("/proj_root/subdir2/package7/lib/hdrfile2.h", 343, "my_symbol", "some_type2 my_symbol;"),
    ("/proj_root/subdir2/package8/sub1/sub2/src/inc/hdrfile1.h", 201, "my_symbol", "some_type3 my_symbol;")
]

TEST_SORT_BY = "/proj_root/subdir1/package3/srcfile1.c"
TEST_FILTER = [
    "/proj_root/subdir1/package1/srcfile1.c",
    "/proj_root/subdir1/package1/srcfile2.c",
    "/proj_root/subdir1/package1/srcfile3.c",
    "/proj_root/subdir1/package1/srcfile4.c",
    "/proj_root/subdir1/package1/hdrfile4.h",
    "/proj_root/subdir1/package1/srcfile5.c"
]

EXPECTED_OUTPUT_SORTED = [
    ("/proj_root/subdir1/package3/srcfile1.c", 34, "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package3/hdrfile1.h", 10, "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package3/tests/hdrfile8.h", 11, "my_symbol", "SymbolType2 *my_symbol;"),
    ("/proj_root/subdir1/package1/hdrfile4.h", 24 , "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package1/hdrfile5.h", 52 , "my_symbol", "typedef gboolean (*func_ptr_type1)(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 32 , "my_symbol", "void (*func_ptr_type2)(SymbolType *my_symbol, struct APIRequest *req);"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 34 , "my_symbol", "void (*func_ptr_type3)(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 38 , "my_symbol", "void (*func_ptr_type4)(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 43 , "my_symbol", "gboolean (*func_ptr_type5)(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 48 , "my_symbol", "gboolean (*func_ptr_type6)(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 53 , "my_symbol", "gboolean (*func_ptr_type7)(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 58 , "my_symbol", "int (*func_ptr_type8)(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 61 , "my_symbol", "int function1(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 64 , "my_symbol", "void function2(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/hdrfile6.h", 67 , "my_symbol", "void function3(SymbolType *my_symbol,"),
    ("/proj_root/subdir1/package1/srcfile1.c", 22 , "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package1/srcfile2.c", 42 , "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package1/srcfile3.c", 38 , "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package1/srcfile4.c", 38 , "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package1/srcfile5.c", 216, "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package1/srcfile5.c", 223, "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package1/srcfile5.c", 246, "my_symbol", "SymbolType *my_symbol;"),
    ("/proj_root/subdir1/package2/hdrfile7.h", 24, "my_symbol", "SymbolType2 *my_symbol;"),
    ("/proj_root/subdir1/package2/subdir2/srcfile7.c", 50, "my_symbol", "static SymbolType2 *my_symbol;"),
    ("/proj_root/subdir1/package4/src/subdir/srcfile3.c", 71, "my_symbol", "SymbolType3 my_symbol;"),
    ("/proj_root/subdir1/utils/util_package1/util_package_file1.c", 55, "my_symbol", "SymbolType my_symbol;"),
    ("/proj_root/subdir2/package5/lib/srcfile6.c", 287, "my_symbol", "SymbolType5 *my_symbol;"),
    ("/proj_root/subdir2/package6/tests/testfile1.c", 54, "my_symbol", "gboolean my_symbol;"),
    ("/proj_root/subdir2/package7/lib/hdrfile2.h", 343, "my_symbol", "some_type2 my_symbol;"),
    ("/proj_root/subdir2/package8/sub1/sub2/src/inc/hdrfile1.h", 201, "my_symbol", "some_type3 my_symbol;")
]

EXPECTED_QP_RESULT = [
    ["subdir1/package3/srcfile1.c:34", "my_symbol: SymbolType *my_symbol;"],
    ["subdir1/package3/hdrfile1.h:10", "my_symbol: SymbolType *my_symbol;"],
    ["subdir1/package3/tests/hdrfile8.h:11", "my_symbol: SymbolType2 *my_symbol;"],
    ["subdir1/package1/hdrfile4.h:24", "my_symbol: SymbolType *my_symbol;"],
    ["subdir1/package1/hdrfile5.h:52", "my_symbol: typedef gboolean (*func_ptr_type1)(SymbolType *my_symbol,"],
    ["subdir1/package1/hdrfile6.h:32", "my_symbol: void (*func_ptr_type2)(SymbolType *my_symbol, struct APIRequest *req);"],
    ["subdir1/package1/hdrfile6.h:34", "my_symbol: void (*func_ptr_type3)(SymbolType *my_symbol,"],
    ["subdir1/package1/hdrfile6.h:38", "my_symbol: void (*func_ptr_type4)(SymbolType *my_symbol,"],
    ["subdir1/package1/hdrfile6.h:43", "my_symbol: gboolean (*func_ptr_type5)(SymbolType *my_symbol,"],
    ["subdir1/package1/hdrfile6.h:48", "my_symbol: gboolean (*func_ptr_type6)(SymbolType *my_symbol,"],
    ["subdir1/package1/hdrfile6.h:53", "my_symbol: gboolean (*func_ptr_type7)(SymbolType *my_symbol,"],
    ["subdir1/package1/hdrfile6.h:58", "my_symbol: int (*func_ptr_type8)(SymbolType *my_symbol,"],
    ["subdir1/package1/hdrfile6.h:61", "my_symbol: int function1(SymbolType *my_symbol,"],
    ["subdir1/package1/hdrfile6.h:64", "my_symbol: void function2(SymbolType *my_symbol,"],
    ["subdir1/package1/hdrfile6.h:67", "my_symbol: void function3(SymbolType *my_symbol,"],
    ["subdir1/package1/srcfile1.c:22", "my_symbol: SymbolType *my_symbol;"],
    ["subdir1/package1/srcfile2.c:42", "my_symbol: SymbolType *my_symbol;"],
    ["subdir1/package1/srcfile3.c:38", "my_symbol: SymbolType *my_symbol;"],
    ["subdir1/package1/srcfile4.c:38", "my_symbol: SymbolType *my_symbol;"],
    ["subdir1/package1/srcfile5.c:216", "my_symbol: SymbolType *my_symbol;"],
    ["subdir1/package1/srcfile5.c:223", "my_symbol: SymbolType *my_symbol;"],
    ["subdir1/package1/srcfile5.c:246", "my_symbol: SymbolType *my_symbol;"],
    ["subdir1/package2/hdrfile7.h:24", "my_symbol: SymbolType2 *my_symbol;"],
    ["subdir1/package2/subdir2/srcfile7.c:50", "my_symbol: static SymbolType2 *my_symbol;"],
    ["subdir1/package4/src/subdir/srcfile3.c:71", "my_symbol: SymbolType3 my_symbol;"],
    ["subdir1/utils/util_package1/util_package_file1.c:55", "my_symbol: SymbolType my_symbol;"],
    ["subdir2/package5/lib/srcfile6.c:287", "my_symbol: SymbolType5 *my_symbol;"],
    ["subdir2/package6/tests/testfile1.c:54", "my_symbol: gboolean my_symbol;"],
    ["subdir2/package7/lib/hdrfile2.h:343", "my_symbol: some_type2 my_symbol;"],
    ["subdir2/package8/sub1/sub2/src/inc/hdrfile1.h:201", "my_symbol: some_type3 my_symbol;"]

]

class CscopeResultsTests(unittest.TestCase):
    def setUp(self):
        self._test_obj = CscopeQueryResult()


    def tearDown(self):
        pass


    def test_query(self):

        for line in TEST_INPUT:
            self._test_obj.parse(line)
        self._test_obj.parse(None)

        res = self._test_obj.get_sorted_results()
        self.assertEqual(len(res), len(EXPECTED_OUTPUT))
        for element in res:
            self.assertTrue(bool(element in EXPECTED_OUTPUT),
                "element %s was not found in %s" % (element, EXPECTED_OUTPUT))

    def test_query_with_filter(self):

        self._test_obj.filter = TEST_FILTER

        for line in TEST_INPUT:
            self._test_obj.parse(line)
        self._test_obj.parse(None)

        res = self._test_obj.get_sorted_results()
        filtered = set(EXPECTED_OUTPUT) - set(res)
        for element in res:
            self.assertFalse(bool(element[0] in TEST_FILTER), "element %s was not filtered out. Filter: %s" % (element, TEST_FILTER))

        for element in filtered:
            self.assertTrue(bool(element[0] in TEST_FILTER), "element %s was unexpectedly filtered out. Filter: %s" % (element, TEST_FILTER))


    def test_result_sorting(self):
        for line in TEST_INPUT:
            self._test_obj.parse(line)
        self._test_obj.parse(None)

        res = self._test_obj.get_sorted_results(sort_by=TEST_SORT_BY)
        self.assertEqual(len(res), len(EXPECTED_OUTPUT_SORTED))

        if res != EXPECTED_OUTPUT_SORTED:
            print("Mismatch in sorted output")
            row = 0
            for elem_res, elem_expect in zip(res, EXPECTED_OUTPUT_SORTED):
                if elem_res != elem_expect:
                    print("%d: %s <--> %s" % (row, elem_res, elem_expect))
                row += 1
            self.assertTrue(False)

    @unittest.skip("Unimplemented")
    def test_results_to_buffer(self):
        pass


    def test_results_to_quickpanel(self):
        mock_window = MagicMock(sublime.Window)
        mock_window.folders.return_value = ['/proj_root']

        CscopeResultsToQuickPanel.generate_results('find_symbol','my_symbol',
                                                    EXPECTED_OUTPUT_SORTED, mock_window)

        calls = mock_window.show_quick_panel.mock_calls
        self.assertEqual(len(calls), 1)

        _, args, _ = calls[0]
        self.assertEqual(args[0], EXPECTED_QP_RESULT)

        calls = mock_window.reset_mock()
        mock_window.folders.return_value = ['/proj_root/subdir1', '/proj_root/subdir2']

        CscopeResultsToQuickPanel.generate_results('find_symbol','my_symbol',
                                                    EXPECTED_OUTPUT_SORTED, mock_window)

        calls = mock_window.show_quick_panel.mock_calls
        self.assertEqual(len(calls), 1)

        _, args, _ = calls[0]
        self.assertEqual(args[0], EXPECTED_QP_RESULT)


        calls = mock_window.reset_mock()
        mock_window.folders.return_value = ['/proj_root/subdir1/',
                                            '/proj_root/subdir2/', '/proj_root/subdir3/']

        CscopeResultsToQuickPanel.generate_results('find_symbol','my_symbol',
                                                    EXPECTED_OUTPUT_SORTED, mock_window)

        calls = mock_window.show_quick_panel.mock_calls
        self.assertEqual(len(calls), 1)

        _, args, _ = calls[0]
        self.assertEqual(args[0], EXPECTED_QP_RESULT)
