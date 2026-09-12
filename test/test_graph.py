import unittest
from tinyagent.graph import N, Op, render, substitute, block

def read(p, out="x"): return N(Op.TEXT, (N(Op.READ, (), p),), out)

class TestGraph(unittest.TestCase):
  def test_interned(self):
    self.assertIs(N(Op.READ, (), "a.py"), N(Op.READ, (), "a.py"))
    self.assertIsNot(N(Op.READ, (), "a.py"), N(Op.READ, (), "b.py"))
  def test_interned_through_src(self):
    a, b = read("a.py"), read("a.py")
    self.assertIs(N(Op.SPEC, (a,), "go"), N(Op.SPEC, (b,), "go"))
  def test_toposort(self):
    r = N(Op.READ, (), "a.py")
    s = N(Op.SPEC, (t:=N(Op.TEXT, (r,), "x"),), "go")
    self.assertEqual([r, t, s], s.toposort())
  def test_toposort_diamond(self):
    r = N(Op.READ, (), "a.py")
    self.assertEqual(3, len(N(Op.SPEC, (N(Op.TEXT, (r,), "1"), N(Op.TEXT, (r,), "1")), "go").toposort()))
  def test_substitute(self):
    r = N(Op.READ, (), "a.py")
    out = substitute(N(Op.SPEC, (r,), "go"), {r: (t:=N(Op.TEXT, (r,), "hello"))})
    self.assertIs(N(Op.SPEC, (t,), "go"), out)
  def test_substitute_leaves_rest_alone(self):
    a, b = N(Op.READ, (), "a.py"), N(Op.READ, (), "b.py")
    self.assertIs(b, substitute(N(Op.SPEC, (a, b), "go"), {a: read("a.py")}).src[1])
  def test_substitute_does_not_rewrite_history(self):
    r = N(Op.RUN, (), "pytest")
    out = substitute(N(Op.SPEC, (f:=N(Op.FAIL, (r,), (1, "boom")), r), "go"), {r: f})
    self.assertIs(r, out.src[0].src[0])
    self.assertIs(f, out.src[1])
  def test_block(self):
    self.assertEqual("$ cat a.py\nhello", block(read("a.py", "hello")))
    self.assertEqual("$ pytest\nexit 2\nboom", block(N(Op.FAIL, (N(Op.RUN, (), "pytest"),), (2, "boom"))))
  def test_render_tail(self):
    out = render(N(Op.SPEC, (read("a.py", "AAA"), read("b.py", "BBB")), "fix it"))
    self.assertTrue(out.endswith("# fix it\n\n$ cat a.py\nAAA\n\n$ cat b.py\nBBB"), out[-80:])
  def test_render_drops_oldest_first(self):
    out = render(N(Op.SPEC, (read("a.py", "A"*400), read("b.py", "B"*400)), "fix it"), budget=1200)
    self.assertIn("$ cat a.py\n[dropped, out of context budget]", out)
    self.assertIn("B"*400, out)
  def test_render_never_drops_a_failure(self):
    f = N(Op.FAIL, (N(Op.RUN, (), "pytest"),), (1, "F"*400))
    self.assertIn("F"*400, render(N(Op.SPEC, (read("a.py", "A"*400), f), "fix it"), budget=100))

if __name__ == "__main__": unittest.main()
