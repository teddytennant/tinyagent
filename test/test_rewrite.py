import unittest
from tinyagent.graph import N, Op, MAXOUT
from tinyagent.rewrite import rules, graph_rewrite, Pat, PatternMatcher

def read(p, out="x"): return N(Op.TEXT, (N(Op.READ, (), p),), out)
def wrote(p, c="new"): return N(Op.TEXT, (N(Op.WRITE, (), (p, c)),), f"wrote {len(c)} bytes")
def fail(cmd="pytest", out="boom"): return N(Op.FAIL, (N(Op.RUN, (), cmd),), (1, out))
def spec(*src): return graph_rewrite(N(Op.SPEC, src, "go"), rules)

class TestPat(unittest.TestCase):
  def test_op(self): self.assertTrue(Pat(Op.READ).match(N(Op.READ, (), "a"), {}))
  def test_op_tuple(self): self.assertTrue(Pat((Op.READ, Op.GREP)).match(N(Op.GREP, (), ("a", "*")), {}))
  def test_arg(self): self.assertFalse(Pat(Op.READ, arg="b").match(N(Op.READ, (), "a"), {}))
  def test_src(self):
    p = Pat(Op.TEXT, src=(Pat(Op.RUN, name="r"),))
    self.assertTrue(p.match(N(Op.TEXT, (N(Op.RUN, (), "ls"),), "out"), store:={}))
    self.assertEqual("ls", store["r"].arg)
  def test_src_arity(self): self.assertFalse(Pat(Op.TEXT, src=()).match(N(Op.TEXT, (N(Op.RUN, (), "ls"),), "o"), {}))
  def test_oscillation_is_an_error(self):
    pm = PatternMatcher([(Pat(Op.READ, name="x"), lambda x: N(Op.READ, (), x.arg + "!"))])
    with self.assertRaises(RuntimeError): graph_rewrite(N(Op.READ, (), "a"), pm)

class TestRules(unittest.TestCase):
  def test_write_supersedes_read(self):
    self.assertEqual((wrote("a.py"),), spec(read("a.py"), wrote("a.py")).src)
  def test_read_after_write_survives(self):
    self.assertEqual((wrote("a.py"), read("a.py")), spec(wrote("a.py"), read("a.py")).src)
  def test_stale_read_dropped(self):
    self.assertEqual((read("a.py", "2"),), spec(read("a.py", "1"), read("a.py", "2")).src)
  def test_last_write_wins(self):
    self.assertEqual((wrote("a.py", "2"),), spec(wrote("a.py", "1"), wrote("a.py", "2")).src)
  def test_unrelated_files_untouched(self):
    self.assertEqual(2, len(spec(read("a.py"), read("b.py")).src))
  def test_failures_are_never_dce_d(self):
    self.assertEqual(3, len(spec(fail(out="1"), fail(out="2"), read("a.py")).src))
  def test_giveup_at_three(self):
    self.assertEqual(2, len(spec(fail(out="1"), fail(out="2")).src))
    self.assertEqual(Op.DONE, spec(fail(out="1"), fail(out="2"), fail(out="3")).op)
  def test_giveup_needs_the_same_command(self):
    self.assertEqual(Op.SPEC, spec(fail("a"), fail("b"), fail("c")).op)
  def test_done_waits_for_pending_work(self):
    d, r = N(Op.DONE, (), "shipped"), N(Op.READ, (), "a.py")
    self.assertEqual(Op.SPEC, spec(r, d).op)
    self.assertEqual("shipped", spec(read("a.py"), d).arg)
  def test_trunc(self):
    self.assertEqual(MAXOUT, len(graph_rewrite(read("a.py", "z"*(MAXOUT*3)), rules).arg))
    self.assertIn("bytes cut", graph_rewrite(read("a.py", "z"*(MAXOUT*3)), rules).arg)
  def test_trunc_keeps_both_ends(self):
    out = graph_rewrite(read("a.py", "head" + "z"*MAXOUT + "tail"), rules).arg
    self.assertTrue(out.startswith("head") and out.endswith("tail"))
  def test_trunc_leaves_short_output_alone(self):
    self.assertIs(t:=read("a.py", "short"), graph_rewrite(t, rules))

if __name__ == "__main__": unittest.main()
