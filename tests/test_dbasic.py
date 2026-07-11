"""Acceptance and unit tests for dbasic (spec section 8, T1-T4).

Run with:  python3 -m unittest discover -s tests -v
       or: make test
       or: python3 -m pytest tests/
"""

import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DBASIC = os.path.join(ROOT, 'dbasic.py')
LIBRARY = os.path.join(ROOT, 'library')
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')


def run_file(path, stdin='', timeout=30):
    """Run a program file in batch mode; return (stdout, stderr, exitcode)."""
    p = subprocess.run([sys.executable, DBASIC, path],
                       input=stdin, capture_output=True, text=True,
                       timeout=timeout)
    return p.stdout, p.stderr, p.returncode


def run_src(src, stdin='', timeout=30):
    """Run BASIC source text in batch mode via a temporary file."""
    with tempfile.NamedTemporaryFile('w', suffix='.bas', delete=False) as f:
        f.write(src)
        path = f.name
    try:
        return run_file(path, stdin=stdin, timeout=timeout)
    finally:
        os.unlink(path)


def love_reference_rows():
    with open(os.path.join(FIXTURES, 'LOVE.txt')) as f:
        return [line.rstrip('\n') for line in f]


def mask(row):
    return [c == ' ' for c in row]


class T1LoveReconstruction(unittest.TestCase):
    """T1: the Spahn reconstruction must reproduce the space/non-space
    mask of every row of the reference LOVE.txt image."""

    def test_love_mask(self):
        out, err, rc = run_file(os.path.join(LIBRARY, 'LOVE'))
        self.assertEqual(rc, 0, "LOVE failed: %s" % err)
        lines = out.split('\n')
        # two header lines + two blank lines, then the 36 image rows
        rows = lines[4:40]
        ref = love_reference_rows()
        self.assertEqual(len(ref), 36)
        self.assertEqual(len(rows), 36, "expected 36 image rows")
        for i, (got, want) in enumerate(zip(rows, ref), start=1):
            w = max(len(got), len(want))
            got_mask = mask(got.ljust(w))
            want_mask = mask(want.ljust(w))
            self.assertEqual(got_mask, want_mask,
                             "space mask mismatch in row %d:\n got: %r\nwant: %r"
                             % (i, got, want))


class T2ColumnLocked(unittest.TestCase):
    """T2: the column-locked variant must reproduce LOVE.txt exactly,
    character for character."""

    def test_love2_exact(self):
        out, err, rc = run_file(os.path.join(LIBRARY, 'LOVE2'))
        self.assertEqual(rc, 0, "LOVE2 failed: %s" % err)
        with open(os.path.join(FIXTURES, 'LOVE.txt')) as f:
            self.assertEqual(out, f.read())


class T3Print(unittest.TestCase):
    def test_comma_zones(self):
        out, _, rc = run_src('10 PRINT 1,2\n20 END\n')
        self.assertEqual(rc, 0)
        self.assertEqual(out, ' 1 ' + ' ' * 12 + ' 2 \n')

    def test_semicolon_packing_numbers(self):
        out, _, rc = run_src('10 PRINT 1;2;-3\n20 END\n')
        self.assertEqual(rc, 0)
        self.assertEqual(out, ' 1  2 -3 \n')

    def test_string_packing(self):
        out, _, rc = run_src('10 PRINT "TIME-";"SHAR";"ING"\n20 END\n')
        self.assertEqual(rc, 0)
        self.assertEqual(out, 'TIME-SHARING\n')

    def test_print_l_semicolon_emits_exactly_l(self):
        out, _, rc = run_src('10 PRINT "L";\n20 PRINT\n30 END\n')
        self.assertEqual(rc, 0)
        self.assertEqual(out, 'L\n')

    def test_trailing_semicolon_suppresses_newline(self):
        out, _, rc = run_src('10 PRINT "AB";\n20 PRINT "CD"\n30 END\n')
        self.assertEqual(rc, 0)
        self.assertEqual(out, 'ABCD\n')

    def test_trailing_comma_continues_in_next_zone(self):
        out, _, rc = run_src('10 PRINT "A",\n20 PRINT "B"\n30 END\n')
        self.assertEqual(rc, 0)
        self.assertEqual(out, 'A' + ' ' * 14 + 'B\n')

    def test_empty_print_is_blank_line(self):
        out, _, rc = run_src('10 PRINT\n20 END\n')
        self.assertEqual(rc, 0)
        self.assertEqual(out, '\n')

    def test_tab_moves_forward(self):
        out, _, rc = run_src('10 PRINT TAB(10);"X"\n20 END\n')
        self.assertEqual(rc, 0)
        self.assertEqual(out, ' ' * 10 + 'X\n')

    def test_tab_never_moves_backward(self):
        out, _, rc = run_src('10 PRINT "ABCDE";TAB(3);"X"\n20 END\n')
        self.assertEqual(rc, 0)
        self.assertEqual(out, 'ABCDEX\n')

    def test_tab_modulo_75(self):
        out, _, rc = run_src('10 PRINT TAB(80);"X"\n20 END\n')
        self.assertEqual(rc, 0)
        self.assertEqual(out, ' ' * 5 + 'X\n')

    def test_fifth_zone_comma_wraps(self):
        out, _, rc = run_src('10 PRINT 1,2,3,4,5,6\n20 END\n')
        self.assertEqual(rc, 0)
        lines = out.split('\n')
        self.assertTrue(lines[0].startswith(' 1 '))
        self.assertEqual(lines[1], ' 6 ')


class T3NumberFormat(unittest.TestCase):
    def cases(self, pairs):
        for expr, want in pairs:
            out, err, rc = run_src('10 PRINT %s\n20 END\n' % expr)
            self.assertEqual(rc, 0, err)
            self.assertEqual(out, want + '\n', "PRINT %s" % expr)

    def test_integers(self):
        self.cases([
            ('0', ' 0 '),
            ('12', ' 12 '),
            ('-7', '-7 '),
            ('12345678', ' 12345678 '),
        ])

    def test_large_integers_use_e_notation(self):
        self.cases([
            ('32437580259', ' 3.24376 E+10 '),
            ('123456789', ' 1.23457 E+8 '),
        ])

    def test_decimals(self):
        self.cases([
            ('2.35', ' 2.35 '),
            ('0.5', ' 0.5 '),
            ('1/3', ' 0.333333 '),
            ('2/3', ' 0.666667 '),
        ])

    def test_small_magnitudes(self):
        self.cases([
            ('.03456', ' 0.03456 '),
            ('.0500548', ' 5.00548 E-2 '),
        ])

    def test_int_function(self):
        self.cases([
            ('INT(2.35)', ' 2 '),
            ('INT(-2.35)', '-3 '),
            ('INT(12)', ' 12 '),
        ])

    def test_sgn(self):
        self.cases([
            ('SGN(7.23)', ' 1 '),
            ('SGN(0)', ' 0 '),
            ('SGN(-.2387)', '-1 '),
        ])

    def test_cot(self):
        # COT is in the manual's sec. 1.2 function table
        self.cases([
            ('COT(1)', ' 0.642093 '),
        ])
        out, err, rc = run_src('10 PRINT COT(0)\n20 END\n')
        self.assertEqual(rc, 0)
        self.assertEqual(out, ' 1.70141 E+38 \n')
        self.assertIn('DIVISION BY ZERO IN 10', err)


class T3ForNext(unittest.TestCase):
    def test_basic_and_step_and_zero_trip(self):
        src = ('10 FOR I = 1 TO 3\n'
               '20 PRINT I;\n'
               '30 NEXT I\n'
               '40 PRINT\n'
               '50 FOR J = 5 TO 1 STEP -2\n'
               '60 PRINT J;\n'
               '70 NEXT J\n'
               '80 PRINT\n'
               '90 FOR K = 1 TO 0\n'
               '100 PRINT "NEVER"\n'
               '110 NEXT K\n'
               '120 PRINT "DONE"\n'
               '130 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 1  2  3 \n 5  3  1 \nDONE\n')

    def test_boundary_inclusive(self):
        out, _, rc = run_src('10 FOR I = 1 TO 1\n20 PRINT I;\n30 NEXT I\n40 END\n')
        self.assertEqual(rc, 0)
        self.assertEqual(out, ' 1 \n')

    def test_loop_variable_after_exit(self):
        # NEXT adds the step and re-tests, so the variable overshoots
        out, _, rc = run_src('10 FOR I = 1 TO 3\n20 NEXT I\n30 PRINT I\n40 END\n')
        self.assertEqual(rc, 0)
        self.assertEqual(out, ' 4 \n')

    def test_improper_nesting_rejected(self):
        src = ('10 FOR I = 1 TO 2\n20 FOR J = 1 TO 2\n'
               '30 NEXT I\n40 NEXT J\n50 END\n')
        _, err, rc = run_src(src)
        self.assertNotEqual(rc, 0)
        self.assertIn('NEXT WITHOUT FOR', err)


class T3Arrays(unittest.TestCase):
    def test_auto_dim_0_through_10(self):
        out, _, rc = run_src('10 LET A(10) = 7\n20 PRINT A(10);A(0)\n30 END\n')
        self.assertEqual(rc, 0)
        self.assertEqual(out, ' 7  0 \n')

    def test_subscript_beyond_auto_bound_is_error(self):
        _, err, rc = run_src('10 LET A(11) = 1\n20 END\n')
        self.assertNotEqual(rc, 0)
        self.assertIn('SUBSCRIPT', err)

    def test_dim_extends_bound(self):
        out, _, rc = run_src('10 DIM A(15)\n20 LET A(15) = 3\n'
                             '30 PRINT A(15)\n40 END\n')
        self.assertEqual(rc, 0)
        self.assertEqual(out, ' 3 \n')

    def test_two_dimensional(self):
        src = ('10 DIM B(2,3)\n20 LET B(2,3) = 9\n'
               '30 PRINT B(2,3);B(0,0)\n40 END\n')
        out, _, rc = run_src(src)
        self.assertEqual(rc, 0)
        self.assertEqual(out, ' 9  0 \n')

    def test_expression_subscripts(self):
        src = ('10 LET I = 2\n20 LET K = 3\n30 LET B(I+K) = 8\n'
               '40 PRINT B(5)\n50 END\n')
        out, _, rc = run_src(src)
        self.assertEqual(rc, 0)
        self.assertEqual(out, ' 8 \n')

    def test_list_and_table_conflict(self):
        _, err, rc = run_src('10 LET A(1) = 1\n20 LET A(1,2) = 3\n30 END\n')
        self.assertNotEqual(rc, 0)
        self.assertIn('SUBSCRIPT', err)

    def test_scalar_and_array_may_share_a_letter(self):
        src = ('10 LET A = 5\n20 LET A(3) = 7\n'
               '30 PRINT A;A(3)\n40 END\n')
        out, _, rc = run_src(src)
        self.assertEqual(rc, 0)
        self.assertEqual(out, ' 5  7 \n')


class T3GosubOn(unittest.TestCase):
    def test_gosub_return_nesting(self):
        src = ('10 GOSUB 100\n'
               '20 PRINT "MAIN"\n'
               '30 GO TO 200\n'
               '100 GOSUB 150\n'
               '110 PRINT "SUB1"\n'
               '120 RETURN\n'
               '150 PRINT "SUB2"\n'
               '160 RETURN\n'
               '200 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, 'SUB2\nSUB1\nMAIN\n')

    def test_return_before_gosub(self):
        _, err, rc = run_src('10 RETURN\n20 END\n')
        self.assertNotEqual(rc, 0)
        self.assertIn('RETURN BEFORE GOSUB', err)

    def test_on_goto(self):
        src = ('10 LET X = 2\n'
               '20 ON X GO TO 40, 60, 80\n'
               '40 PRINT "ONE"\n'
               '50 GO TO 90\n'
               '60 PRINT "TWO"\n'
               '70 GO TO 90\n'
               '80 PRINT "THREE"\n'
               '90 END\n')
        out, _, rc = run_src(src)
        self.assertEqual(rc, 0)
        self.assertEqual(out, 'TWO\n')

    def test_on_out_of_range(self):
        src = '10 ON 5 GO TO 20, 30\n20 PRINT "A"\n30 END\n'
        _, err, rc = run_src(src)
        self.assertNotEqual(rc, 0)
        self.assertIn('OUT OF RANGE', err)


class T3Change(unittest.TestCase):
    def test_round_trip(self):
        src = ('10 DIM N(30)\n'
               '20 LET A$ = "ABC"\n'
               '30 CHANGE A$ TO N\n'
               '40 PRINT N(0);N(1);N(2);N(3)\n'
               '50 CHANGE N TO B$\n'
               '60 PRINT B$\n'
               '70 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 3  65  66  67 \nABC\n')

    def test_manual_example_codes(self):
        # manual sec. 2.7: CHANGE of the alphabet yields 26, 65, 66, ... 90
        src = ('5 DIM A(65)\n'
               '10 READ A$\n'
               '15 CHANGE A$ TO A\n'
               '20 FOR I = 0 TO A(0)\n'
               '25 PRINT A(I);\n'
               '30 NEXT I\n'
               '40 DATA ABCDEFGHIJKLMNOPQRSTUVWXYZ\n'
               '45 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        first = out.split('\n')[0]
        self.assertTrue(first.startswith(' 26  65  66  67 '))

    def test_vector_to_string(self):
        src = ('10 FOR I = 0 TO 5\n'
               '15 READ A(I)\n'
               '20 NEXT I\n'
               '25 DATA 5, 65, 66, 67, 68, 69\n'
               '30 CHANGE A TO A$\n'
               '35 PRINT A$\n'
               '40 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, 'ABCDE\n')


class T3Strings(unittest.TestCase):
    def test_string_vector_indexing(self):
        src = ('10 DIM V$(12)\n'
               '20 FOR I = 1 TO 3\n'
               '30 READ V$(I)\n'
               '40 NEXT I\n'
               '50 PRINT V$(2);V$(1);V$(3)\n'
               '60 DATA ING, SHAR, "TIME-"\n'
               '70 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, 'SHARINGTIME-\n')

    def test_string_comparison_ignores_trailing_blanks(self):
        src = ('10 LET A$ = "YES  "\n'
               '20 IF A$ = "YES" THEN 50\n'
               '30 PRINT "NO"\n'
               '40 GO TO 60\n'
               '50 PRINT "EQ"\n'
               '60 END\n')
        out, _, rc = run_src(src)
        self.assertEqual(rc, 0)
        self.assertEqual(out, 'EQ\n')


class T3ReadData(unittest.TestCase):
    def test_separate_numeric_and_string_pools(self):
        src = ('10 READ A, A$, B, B$\n'
               '20 PRINT A;B\n'
               '30 PRINT A$;B$\n'
               '40 DATA 10, ABC, 5\n'
               '50 DATA XY\n'
               '60 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 10  5 \nABCXY\n')

    def test_restore(self):
        src = ('10 READ A,B\n20 RESTORE\n30 READ C\n'
               '40 PRINT A;B;C\n50 DATA 1,2\n60 END\n')
        out, _, rc = run_src(src)
        self.assertEqual(rc, 0)
        self.assertEqual(out, ' 1  2  1 \n')

    def test_out_of_data(self):
        _, err, rc = run_src('10 READ A,B\n20 DATA 1\n30 END\n')
        self.assertNotEqual(rc, 0)
        self.assertIn('OUT OF DATA', err)


class T3Syntax(unittest.TestCase):
    def test_if_then_line_number_only(self):
        _, err, rc = run_src('10 IF X = 1 THEN PRINT "NO"\n20 END\n')
        self.assertNotEqual(rc, 0)
        self.assertIn('LINE NUMBER', err)

    def test_multi_statement_lines_rejected(self):
        _, err, rc = run_src('10 LET A = 1 : LET B = 2\n20 END\n')
        self.assertNotEqual(rc, 0)
        self.assertIn('ONE STATEMENT', err)

    def test_let_keyword_required(self):
        _, err, rc = run_src('10 A = 1\n20 END\n')
        self.assertNotEqual(rc, 0)

    def test_end_required(self):
        _, err, rc = run_src('10 PRINT "X"\n')
        self.assertNotEqual(rc, 0)
        self.assertIn('NO END', err)

    def test_end_must_be_last(self):
        # the one-pass DTSS compiler required END to be the final line;
        # trailing DATA is rejected (manual sec. 2.8)
        _, err, rc = run_src('10 READ A\n20 END\n30 DATA 1\n')
        self.assertNotEqual(rc, 0)
        self.assertIn('END IS NOT LAST', err)

    def test_only_one_end(self):
        _, err, rc = run_src('10 END\n20 END\n')
        self.assertNotEqual(rc, 0)
        self.assertIn('END IS NOT LAST', err)

    def test_data_before_end_is_fine(self):
        out, err, rc = run_src('10 READ A\n20 PRINT A\n30 DATA 7\n40 END\n')
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 7 \n')

    def test_undefined_line_number(self):
        _, err, rc = run_src('10 GO TO 500\n20 END\n')
        self.assertNotEqual(rc, 0)
        self.assertIn('UNDEFINED LINE NUMBER', err)

    def test_goto_and_go_to_both_accepted(self):
        src = '10 GOTO 30\n20 PRINT "NO"\n30 GO TO 50\n40 PRINT "NO"\n50 END\n'
        out, _, rc = run_src(src)
        self.assertEqual(rc, 0)
        self.assertEqual(out, '')

    def test_apostrophe_remark(self):
        # manual sec. 2.5: ' at end of line begins a remark
        src = "10 LET A = 5 'SET A TO FIVE\n20 PRINT A 'AND PRINT IT\n30 END\n"
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 5 \n')

    def test_apostrophe_kept_in_data_and_quotes(self):
        # the manual's caveat: in an unquoted string the apostrophe is
        # part of the string, so DATA lines keep it
        src = ("10 READ A$\n20 PRINT A$;\"N'T\"\n"
               "30 DATA DO\n40 END\n")
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, "DON'T\n")
        src = "10 READ A$\n20 PRINT A$\n30 DATA CAN'T\n40 END\n"
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, "CAN'T\n")

    def test_if_go_to_form(self):
        # manual sec. 1.7.6: IF X > 5 GO TO 200 == IF X > 5 THEN 200
        src = ('10 LET X = 9\n20 IF X > 5 GO TO 40\n'
               '30 PRINT "NO"\n40 END\n')
        out, _, rc = run_src(src)
        self.assertEqual(rc, 0)
        self.assertEqual(out, '')

    def test_on_then_form(self):
        # manual sec. 1.7.6: THEN may be used in an ON statement
        src = ('10 ON 2 THEN 20, 40\n20 PRINT "ONE"\n'
               '30 GO TO 50\n40 PRINT "TWO"\n50 END\n')
        out, _, rc = run_src(src)
        self.assertEqual(rc, 0)
        self.assertEqual(out, 'TWO\n')

    def test_print_juxtaposition_documented_form(self):
        # manual sec. 1.7.3 type (c): PRINT "THE VALUE OF X IS" X
        src = ('10 LET X = 3\n20 PRINT "THE VALUE OF X IS" X\n30 END\n')
        out, _, rc = run_src(src)
        self.assertEqual(rc, 0)
        self.assertEqual(out, 'THE VALUE OF X IS 3 \n')

    def test_not_equal_hash_form(self):
        src = ('10 LET A = 1\n20 IF A # 2 THEN 40\n'
               '30 PRINT "EQ"\n40 END\n')
        out, _, rc = run_src(src)
        self.assertEqual(rc, 0)
        self.assertEqual(out, '')


def crunch(line):
    """Delete spaces outside quoted strings (DTSS free-form source)."""
    out, inq = [], False
    for ch in line:
        if ch == '"':
            inq = not inq
            out.append(ch)
        elif ch == ' ' and not inq:
            continue
        else:
            out.append(ch)
    return ''.join(out)


class T3FreeForm(unittest.TestCase):
    """DTSS source is free-form: spaces outside quotes have no meaning."""

    def test_run_together_statement(self):
        # the manual's LINEAR program line 15, crunched
        src = ('10READA,B,D,E\n'
               '15LETG=A*E-B*D\n'
               '20PRINTG\n'
               '30DATA1,2,4,2\n'
               '40END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, '-6 \n')

    def test_crunched_for_next_if(self):
        src = ('10FORI=1TO3\n'
               '20PRINTI;\n'
               '30NEXTI\n'
               '40IFI>3THEN60\n'
               '50PRINT"NO"\n'
               '60END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 1  2  3 \n')

    def test_spaces_merge_within_names(self):
        # true insensitivity: X 1 is the variable X1
        src = '10 LET X 1 = 7\n20 PRINT X 1\n30 END\n'
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 7 \n')

    def test_crunched_def_mat_change(self):
        src = ('10DEFFNS(X)=X*X\n'
               '20MATA=CON(2,2)\n'
               '30MATA=(FNS(2))*A\n'
               '40MATPRINTA;\n'
               '50LETA$="HI"\n'
               '60CHANGEA$TON\n'
               '70PRINTN(0)\n'
               '80END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 4  4 \n 4  4 \n 2 \n')

    def test_quoted_strings_keep_spaces(self):
        src = '10PRINT"A B  C"\n20END\n'
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, 'A B  C\n')

    def test_crunched_love2_matches_reference(self):
        # crunching the whole column-locked LOVE program must not change
        # a single output character
        with open(os.path.join(LIBRARY, 'LOVE2')) as f:
            crunched = ''.join(crunch(ln) + '\n'
                               for ln in f.read().splitlines())
        out, err, rc = run_src(crunched)
        self.assertEqual(rc, 0, err)
        with open(os.path.join(FIXTURES, 'LOVE.txt')) as f:
            self.assertEqual(out, f.read())


class T3Functions(unittest.TestCase):
    def test_def_fn(self):
        src = ('10 DEF FNT(X) = SQR(ABS(X)) + 5*X^3\n'
               '20 PRINT FNT(1)\n30 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 6 \n')

    def test_def_uses_global_variables(self):
        src = ('10 DEF FNA = 3.1416*R^2\n'
               '20 LET R = 2\n30 PRINT FNA\n40 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 12.5664 \n')

    def test_rnd_repeatable_across_runs(self):
        src = '10 PRINT RND;RND;RND\n20 END\n'
        out1, _, rc1 = run_src(src)
        out2, _, rc2 = run_src(src)
        self.assertEqual(rc1, 0)
        self.assertEqual(rc2, 0)
        self.assertEqual(out1, out2)
        # E-notation contains a space ("2.91349 E-2"), so match whole numbers
        import re
        nums = re.findall(r'\d+(?:\.\d+)?(?: E[+-]\d+)?', out1)
        vals = [float(v.replace(' E', 'E')) for v in nums]
        self.assertEqual(len(vals), 3)
        for v in vals:
            self.assertGreater(v, 0.0)
            self.assertLess(v, 1.0)

    def test_precedence(self):
        # ^ binds tighter than unary minus: -2^2 = -(2^2) = -4
        out, _, rc = run_src('10 PRINT -2^2\n20 END\n')
        self.assertEqual(rc, 0)
        self.assertEqual(out, '-4 \n')


class T3MathWarnings(unittest.TestCase):
    """Manual sec. 2.8: arithmetic anomalies print a warning, supply a
    value, and the program continues running (exit code stays 0; in batch
    mode the warning goes to stderr)."""

    def warn_case(self, expr, want_out, want_msg):
        out, err, rc = run_src('10 PRINT %s\n20 END\n' % expr)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, want_out + '\n', "PRINT %s" % expr)
        self.assertIn(want_msg + ' IN 10', err)

    def test_division_by_zero(self):
        self.warn_case('1/0', ' 1.70141 E+38 ', 'DIVISION BY ZERO')

    def test_zero_to_a_negative_power(self):
        self.warn_case('0^(-1)', ' 1.70141 E+38 ', 'ZERO TO A NEGATIVE POWER')

    def test_log_of_zero(self):
        self.warn_case('LOG(0)', '-1.70141 E+38 ', 'LOG OF ZERO')

    def test_log_of_negative_number(self):
        self.warn_case('LOG(-EXP(1))', ' 1 ', 'LOG OF NEGATIVE NUMBER')

    def test_square_root_of_negative_number(self):
        self.warn_case('SQR(-4)', ' 2 ', 'SQUARE ROOT OF A NEGATIVE NUMBER')

    def test_absolute_value_raised_to_power(self):
        self.warn_case('(-8)^(1/3)', ' 2 ', 'ABSOLUTE VALUE RAISED TO POWER')

    def test_negative_base_integer_power_is_exact(self):
        out, err, rc = run_src('10 PRINT (-3)^3\n20 END\n')
        self.assertEqual(rc, 0)
        self.assertEqual(out, '-27 \n')
        self.assertEqual(err, '')

    def test_overflow_supplies_maxnum(self):
        self.warn_case('1E30*1E30', ' 1.70141 E+38 ', 'OVERFLOW')

    def test_exp_too_large(self):
        self.warn_case('EXP(89)', ' 1.70141 E+38 ', 'EXP TOO LARGE')

    def test_underflow_supplies_zero(self):
        self.warn_case('1E-30*1E-30', ' 0 ', 'UNDERFLOW')

    def test_execution_continues_after_warning(self):
        src = ('10 LET X = LOG(0)\n'
               '20 PRINT "STILL RUNNING"\n'
               '30 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0)
        self.assertEqual(out, 'STILL RUNNING\n')
        self.assertIn('LOG OF ZERO IN 10', err)

    def test_mismatched_string_operation_is_fatal(self):
        _, err, rc = run_src('10 LET A = "X"\n20 END\n')
        self.assertNotEqual(rc, 0)
        self.assertIn('MISMATCHED STRING OPERATION', err)

    def test_illegal_constant(self):
        _, err, rc = run_src('10 PRINT 1E50\n20 END\n')
        self.assertNotEqual(rc, 0)
        self.assertIn('ILLEGAL CONSTANT', err)


class T3Mat(unittest.TestCase):
    """MAT statements per manual sec. 2.6 (strings: sec. 2.7)."""

    def test_manual_matrix_example(self):
        # the MATRIX sample program from manual p. 60, output verified
        # against the printed teletype transcript
        src = ('10 DIM A(20,20),B(20,20),C(20,20)\n'
               '20 READ M,N\n'
               '30 MAT READ A(M,N),B(N,N)\n'
               '40 MAT C = A + A\n'
               '50 MAT PRINT C;\n'
               '60 MAT C = A*B\n'
               '70 PRINT\n'
               '75 PRINT "A*B =",\n'
               '80 MAT PRINT C\n'
               '90 DATA 2,3\n'
               '91 DATA 1,2,3\n'
               '92 DATA 4,5,6\n'
               '93 DATA 1,0,-1\n'
               '94 DATA 0,-1,-1\n'
               '95 DATA -1,0,0\n'
               '99 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        zone = ' ' * 12
        self.assertEqual(out,
                         ' 2  4  6 \n'
                         ' 8  10  12 \n'
                         '\n'
                         'A*B =' + ' ' * 10 + '\n'
                         '-2 ' + zone + '-2 ' + zone + '-3 \n'
                         '-2 ' + zone + '-5 ' + zone + '-9 \n')

    def test_zer_con_idn_ignore_row_and_column_zero(self):
        src = ('10 DIM M(3,3)\n'
               '20 LET M(0,1) = 9\n'
               '30 MAT M = CON\n'
               '40 PRINT M(0,1);M(1,1);M(0,0)\n'
               '50 MAT M = IDN\n'
               '60 PRINT M(1,1);M(1,2);M(2,2)\n'
               '70 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 9  1  0 \n 1  0  1 \n')

    def test_redimension_capacity_manual_example(self):
        # manual p. 56: DIM M(20,7) allows ZER(25,5) (156 <= 168
        # components) but not ZER(16,10) (187 > 168)
        ok = ('10 DIM M(20,7)\n20 MAT M = ZER(25,5)\n'
              '30 PRINT M(25,5)\n40 END\n')
        out, err, rc = run_src(ok)
        self.assertEqual(rc, 0, err)
        bad = '10 DIM M(20,7)\n20 MAT M = ZER(16,10)\n30 END\n'
        _, err, rc = run_src(bad)
        self.assertNotEqual(rc, 0)
        self.assertIn('DIMENSION ERROR', err)

    def test_redimension_relocates_row_zero_manual_example(self):
        # manual p. 56: after MAT READ M(2,2), M(1,0) and M(2,0) are 0
        src = ('10 DIM M(20,7)\n'
               '20 LET M(1,0) = 1\n'
               '30 LET M(2,0) = 1\n'
               '40 MAT READ M(2,2)\n'
               '50 PRINT M(1,0);M(2,0);M(2,2)\n'
               '60 DATA 5,6,7,8\n'
               '70 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 0  0  8 \n')

    def test_matrix_times_vector(self):
        src = ('10 DIM A(2,2),V(2),W(2)\n'
               '20 MAT READ A(2,2),V(2)\n'
               '30 MAT W = A*V\n'
               '40 MAT PRINT W;\n'
               '50 DATA 1,2,3,4,10,20\n'
               '60 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 50  110 \n')

    def test_transpose_and_illegal_forms(self):
        src = ('10 MAT READ A(2,3)\n'
               '20 MAT B = TRN(A)\n'
               '30 MAT PRINT B;\n'
               '40 DATA 1,2,3,4,5,6\n'
               '50 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 1  4 \n 2  5 \n 3  6 \n')
        _, err, rc = run_src('10 MAT READ A(2,2)\n20 MAT A = TRN(A)\n'
                             '30 DATA 1,2,3,4\n40 END\n')
        self.assertNotEqual(rc, 0)
        self.assertIn('ILLEGAL MAT TRANSPOSE', err)
        _, err, rc = run_src('10 MAT A = CON(2,2)\n20 MAT B = CON(2,2)\n'
                             '30 MAT A = A*B\n40 END\n')
        self.assertNotEqual(rc, 0)
        self.assertIn('ILLEGAL MAT MULTIPLE', err)

    def test_inv_and_det(self):
        src = ('10 MAT READ A(2,2)\n'
               '20 MAT B = INV(A)\n'
               '30 MAT PRINT B;\n'
               '40 PRINT DET\n'
               '50 DATA 2,0,0,4\n'
               '60 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 0.5  0 \n 0  0.25 \n 8 \n')

    def test_inv_singular_continues_with_det_zero(self):
        src = ('10 MAT A = ZER(2,2)\n'
               '20 MAT B = INV(A)\n'
               '30 PRINT DET\n'
               '40 PRINT "STILL RUNNING"\n'
               '50 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 0 \nSTILL RUNNING\n')

    def test_scalar_multiplication(self):
        src = ('10 MAT READ A(2,2)\n'
               '20 LET K = 3\n'
               '30 MAT A = (K+1)*A\n'
               '40 MAT PRINT A;\n'
               '50 DATA 1,2,3,4\n'
               '60 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 4  8 \n 12  16 \n')

    def test_add_dimension_mismatch(self):
        src = ('10 MAT A = CON(2,2)\n20 MAT B = CON(3,3)\n'
               '30 MAT C = A + B\n40 END\n')
        _, err, rc = run_src(src)
        self.assertNotEqual(rc, 0)
        self.assertIn('DIMENSION ERROR', err)

    def test_mat_input_ampersand_and_num(self):
        src = ('10 DIM V(20)\n'
               '20 MAT INPUT V\n'
               '30 PRINT NUM;V(NUM)\n'
               '40 END\n')
        out, err, rc = run_src(src, stdin='1,2,3&\n4,5\n')
        self.assertEqual(rc, 0, err)
        self.assertIn(' 5  5 \n', out)

    def test_mat_input_empty_line_gives_num_zero(self):
        src = '10 MAT INPUT V\n20 PRINT NUM\n30 END\n'
        out, err, rc = run_src(src, stdin='\n')
        self.assertEqual(rc, 0, err)
        self.assertIn(' 0 \n', out)

    def test_string_vector_mat_read_and_packed_print(self):
        src = ('10 DIM M$(5)\n'
               '20 MAT READ M$(3)\n'
               '30 MAT PRINT M$;\n'
               '40 DATA "TIME-", SHAR, ING\n'
               '50 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, 'TIME-SHARING\n')

    def test_vector_prints_as_column_by_default(self):
        src = ('10 MAT READ V(3)\n20 MAT PRINT V\n'
               '30 DATA 1,2,3\n40 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 1 \n 2 \n 3 \n')

    def test_copy_redimensions_target(self):
        src = ('10 DIM B(10,10)\n'
               '20 MAT READ A(2,3)\n'
               '30 MAT B = A\n'
               '40 MAT PRINT B;\n'
               '50 DATA 1,2,3,4,5,6\n'
               '60 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 1  2  3 \n 4  5  6 \n')


class T3MultiLineDef(unittest.TestCase):
    """Multiple-line DEF ... FNEND (manual sec. 2.2)."""

    def test_manual_max_and_factorial_examples(self):
        src = ('10 DEF FNM(X,Y)\n'
               '20 LET FNM = X\n'
               '30 IF Y <= X THEN 50\n'
               '40 LET FNM = Y\n'
               '50 FNEND\n'
               '60 DEF FNF(N)\n'
               '70 LET FNF = 1\n'
               '80 FOR K = 1 TO N\n'
               '90 LET FNF = K * FNF\n'
               '100 NEXT K\n'
               '110 FNEND\n'
               '120 PRINT FNM(3,7);FNM(12,5);FNF(5)\n'
               '130 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 7  12  120 \n')

    def test_body_is_skipped_when_not_called(self):
        src = ('10 DEF FNA(X)\n'
               '20 PRINT "INSIDE"\n'
               '30 LET FNA = X\n'
               '40 FNEND\n'
               '50 PRINT "OUTSIDE"\n'
               '60 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, 'OUTSIDE\n')

    def test_globals_visible_inside(self):
        src = ('10 LET A = 10\n'
               '20 DEF FNG(X)\n'
               '30 LET FNG = X + A\n'
               '40 FNEND\n'
               '50 PRINT FNG(5)\n'
               '60 END\n')
        out, err, rc = run_src(src)
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, ' 15 \n')

    def test_nested_def_rejected(self):
        src = ('10 DEF FNA(X)\n20 DEF FNB(Y)\n30 FNEND\n'
               '40 FNEND\n50 END\n')
        _, err, rc = run_src(src)
        self.assertNotEqual(rc, 0)
        self.assertIn('NESTED DEF', err)

    def test_unfinished_def_rejected(self):
        src = '10 DEF FNA(X)\n20 LET FNA = X\n30 END\n'
        _, err, rc = run_src(src)
        self.assertNotEqual(rc, 0)
        self.assertIn('UNFINISHED DEF', err)

    def test_transfer_into_def_rejected(self):
        src = ('10 GO TO 40\n'
               '20 DEF FNA(X)\n30 LET FNA = X\n40 LET FNA = 1\n50 FNEND\n'
               '60 END\n')
        _, err, rc = run_src(src)
        self.assertNotEqual(rc, 0)
        self.assertIn('TRANSFER', err)

    def test_transfer_out_of_def_rejected(self):
        src = ('10 DEF FNA(X)\n20 GO TO 60\n30 LET FNA = X\n40 FNEND\n'
               '60 END\n')
        _, err, rc = run_src(src)
        self.assertNotEqual(rc, 0)
        self.assertIn('TRANSFER', err)

    def test_fnend_without_def_rejected(self):
        _, err, rc = run_src('10 FNEND\n20 END\n')
        self.assertNotEqual(rc, 0)
        self.assertIn('FNEND WITHOUT DEF', err)

    def test_let_fn_outside_def_rejected(self):
        src = ('10 DEF FNA(X)\n20 LET FNA = X\n30 FNEND\n'
               '40 LET FNA = 5\n50 END\n')
        _, err, rc = run_src(src)
        self.assertNotEqual(rc, 0)
        self.assertIn('OUTSIDE ITS DEF', err)


class T3Input(unittest.TestCase):
    def test_input_reads_stdin(self):
        src = '10 INPUT A, B\n20 PRINT A+B\n30 END\n'
        out, err, rc = run_src(src, stdin='3, 4\n')
        self.assertEqual(rc, 0, err)
        self.assertIn(' 7 ', out)

    def test_input_at_eof_errors_cleanly(self):
        _, err, rc = run_src('10 INPUT A\n20 END\n', stdin='')
        self.assertEqual(rc, 1)
        self.assertIn('END OF INPUT', err)
        self.assertNotIn('Traceback', err)


class T4FtballSmoke(unittest.TestCase):
    """T4: FTBALL loads and runs on canned input without crashing."""

    def test_ftball(self):
        plays = '\n'.join(['1', '2', '3', '4', '3', '1'] * 20)
        stdin = '150\n' + plays + '\n'
        out, err, rc = run_file(os.path.join(LIBRARY, 'FTBALL'),
                                stdin=stdin, timeout=60)
        self.assertIn('THIS IS DARTMOUTH CHAMPIONSHIP FOOTBALL.', out)
        self.assertIn('WON THE TOSS', out)
        self.assertNotIn('Traceback', err)
        # either the game ended (0) or the canned input ran out (1)
        self.assertIn(rc, (0, 1))


DBASIC2 = os.path.join(ROOT, 'dbasic2.py')

def _find_python2():
    from shutil import which
    return which('python2') or which('python2.7')


PYTHON2 = _find_python2()

# a program touching the cross-version hazards: RNG integer division,
# round() tie-breaking in subscripts, and E-notation formatting
EQUIV_SRC = ('10 PRINT RND;RND\n'
             '20 PRINT .0500548;1/3\n'
             '30 LET A(2) = 7\n'
             '40 LET I = 1.5\n'
             '50 PRINT A(I+0.5)\n'
             '60 END\n')


class Python2Fork(unittest.TestCase):
    """dbasic2.py is a maintained-in-parallel Python 2.7 fork of dbasic.py
    for legacy machines.  It must produce byte-identical output.  The
    python3 checks always run (guarding against fork rot); the python2
    checks run whenever a python2 interpreter is present."""

    def test_fork_love2_exact_under_python3(self):
        p = subprocess.run([sys.executable, DBASIC2,
                            os.path.join(LIBRARY, 'LOVE2')],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(os.path.join(FIXTURES, 'LOVE.txt')) as f:
            self.assertEqual(p.stdout, f.read())

    def test_fork_matches_primary_under_python3(self):
        with tempfile.NamedTemporaryFile('w', suffix='.bas',
                                         delete=False) as f:
            f.write(EQUIV_SRC)
            path = f.name
        try:
            pf = subprocess.run([sys.executable, DBASIC2, path],
                                capture_output=True, text=True, timeout=60)
            pp = subprocess.run([sys.executable, DBASIC, path],
                                capture_output=True, text=True, timeout=60)
        finally:
            os.unlink(path)
        self.assertEqual(pf.returncode, 0, pf.stderr)
        self.assertEqual(pf.stdout, pp.stdout,
                         'dbasic2.py and dbasic.py outputs differ')

    @unittest.skipUnless(PYTHON2, 'no python2 interpreter on this machine')
    def test_fork_love2_exact_under_python2(self):
        p = subprocess.run([PYTHON2, DBASIC2,
                            os.path.join(LIBRARY, 'LOVE2')],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(os.path.join(FIXTURES, 'LOVE.txt')) as f:
            self.assertEqual(p.stdout, f.read())

    @unittest.skipUnless(PYTHON2, 'no python2 interpreter on this machine')
    def test_fork_matches_primary_under_python2(self):
        with tempfile.NamedTemporaryFile('w', suffix='.bas',
                                         delete=False) as f:
            f.write(EQUIV_SRC)
            path = f.name
        try:
            p2 = subprocess.run([PYTHON2, DBASIC2, path],
                                capture_output=True, text=True, timeout=60)
            p3 = subprocess.run([sys.executable, DBASIC, path],
                                capture_output=True, text=True, timeout=60)
        finally:
            os.unlink(path)
        self.assertEqual(p2.returncode, 0, p2.stderr)
        self.assertEqual(p2.stdout, p3.stdout,
                         'python2 fork and python3 primary outputs differ')


class InteractiveSmoke(unittest.TestCase):
    def test_empty_workspace_list_is_silent_and_run_reports_no_end(self):
        session = 'LIST\nNEW TEST\nLIST\nRUN\nBYE\n'
        p = subprocess.run([sys.executable, DBASIC], input=session,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = p.stdout.splitlines()
        # banner, READY, READY (LIST: silent), READY (NEW),
        # READY (LIST: still silent), NO END INSTRUCTION, READY (RUN)
        self.assertEqual(lines[1:], ['READY', 'READY', 'READY', 'READY',
                                     'NO END INSTRUCTION', 'READY'])

    def test_repl_session(self):
        session = ('NEW TEST\n'
                   '10 PRINT "HI"\n'
                   '20 END\n'
                   'RUN\n'
                   'BYE\n')
        p = subprocess.run([sys.executable, DBASIC], input=session,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('READY', p.stdout)
        self.assertIn('HI', p.stdout)
        # the RUN header starts one space in (manual pp. 10, 24, 27, 60)
        import re
        self.assertTrue(re.search(r'\n TEST\s+\d\d:\d\d', p.stdout),
                        'RUN header should begin with one space')


if __name__ == '__main__':
    unittest.main()
