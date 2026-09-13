import os, tempfile, unittest
from tinyagent.graph import N, Op
from tinyagent.tools import parse, exec_tool

class TestParse(unittest.TestCase):
  def one(self, txt): return parse(txt)[0]
  def test_read(self): self.assertEqual((Op.READ, "a/b.py"), (n:=self.one("READ a/b.py")).op and (n.op, n.arg))
  def test_grep(self): self.assertEqual(("def foo", "*.py"), self.one("GREP def foo *.py").arg)
  def test_grep_no_glob(self): self.assertEqual(("def foo", "*"), self.one("GREP def foo").arg)
  def test_run_keeps_the_whole_line(self): self.assertEqual("pytest -x -k 'a or b'", self.one("RUN pytest -x -k 'a or b'").arg)
  def test_write(self):
    self.assertEqual(("a.py", "x = 1\ny = 2\n"), self.one("WRITE a.py\n<<<\nx = 1\ny = 2\n>>>").arg)
  def test_write_keeps_blank_lines_and_indent(self):
    self.assertEqual(("a.py", "def f():\n\n  return 1\n"), self.one("WRITE a.py\n<<<\ndef f():\n\n  return 1\n>>>").arg)
  def test_write_body_is_not_reparsed(self):
    self.assertEqual(1, len(parse("WRITE a.py\n<<<\nRUN rm -rf /\n>>>")))
  def test_done(self): self.assertEqual((Op.DONE, "tests pass"), ((n:=self.one("DONE tests pass")).op, n.arg))
  def test_bare_done(self): self.assertEqual(Op.DONE, self.one("DONE").op)
  def test_prose_is_ignored(self):
    self.assertEqual([Op.READ], [n.op for n in parse("sure! let me look.\n\nREAD a.py\n\nhope that helps")])
  def test_fences_are_ignored(self):
    self.assertEqual([Op.WRITE], [n.op for n in parse("```\nWRITE a.py\n<<<\nx\n>>>\n```")])
  def test_run_with_a_body(self):
    self.assertEqual("python3 -\nimport sys\nprint(1)", self.one("RUN python3 -\n<<<\nimport sys\nprint(1)\n>>>").arg)
  def test_run_without_a_body_is_one_line(self):
    self.assertEqual([Op.RUN, Op.RUN], [n.op for n in parse("RUN ls\nRUN pwd")])
  def test_a_write_with_no_fence_is_dropped_not_greedy(self):
    self.assertEqual([Op.RUN], [n.op for n in parse("WRITE a.py\nRUN pytest")])
  def test_order_is_kept(self):
    self.assertEqual([Op.WRITE, Op.RUN, Op.DONE], [n.op for n in parse("WRITE a.py\n<<<\nx\n>>>\nRUN pytest\nDONE ok")])

class TestExec(unittest.TestCase):
  def setUp(self):
    self.d = tempfile.mkdtemp(); self.old = os.getcwd(); os.chdir(self.d)
  def tearDown(self): os.chdir(self.old)
  def go(self, n): return exec_tool[n.op](n)
  def test_write_then_read(self):
    self.assertEqual("wrote 6 bytes", self.go(N(Op.WRITE, (), ("a.py", "x = 1\n"))).arg)
    self.assertEqual("x = 1\n", self.go(N(Op.READ, (), "a.py")).arg)
  def test_write_makes_dirs(self):
    self.go(N(Op.WRITE, (), ("deep/er/a.py", "x\n")))
    self.assertTrue(os.path.exists("deep/er/a.py"))
  def test_rewriting_identical_content_does_not_touch_the_file(self):
    self.go(N(Op.WRITE, (), ("a.py", "x\n")))
    self.assertEqual("unchanged", self.go(N(Op.WRITE, (), ("a.py", "x\n"))).arg)
  def test_missing_file_fails(self):
    self.assertEqual(Op.FAIL, self.go(N(Op.READ, (), "nope.py")).op)
  def test_run_ok(self):
    self.assertEqual((Op.TEXT, "hi"), ((n:=self.go(N(Op.RUN, (), "echo hi"))).op, n.arg))
  def test_run_fail_carries_rc_and_output(self):
    n = self.go(N(Op.RUN, (), "echo boom >&2; exit 3"))
    self.assertEqual((Op.FAIL, 3, "boom"), (n.op, n.arg[0], n.arg[1]))
  def test_grep(self):
    self.go(N(Op.WRITE, (), ("a.py", "def foo(): pass\n")))
    self.assertIn("a.py:1:def foo", self.go(N(Op.GREP, (), ("def foo", "*.py"))).arg)
  def test_grep_no_match_is_not_a_failure(self):
    n = self.go(N(Op.GREP, (), ("zzzz", "*.py")))
    self.assertEqual((Op.TEXT, "no matches"), (n.op, n.arg))

if __name__ == "__main__": unittest.main()
