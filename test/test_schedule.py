import os, subprocess, tempfile, unittest
from tinyagent.graph import N, Op
from tinyagent.schedule import groups, run

def r(p): return N(Op.READ, (), p)
def g(p): return N(Op.GREP, (), (p, "*.py"))
def w(p): return N(Op.WRITE, (), (p, "x\n"))
def c(x): return N(Op.RUN, (), x)

class TestGroups(unittest.TestCase):
  def ops(self, *ns): return [[x.op.name for x in grp] for grp in groups(list(ns))]
  def test_reads_fuse(self): self.assertEqual([["READ", "READ", "GREP"]], self.ops(r("a"), r("b"), g("x")))
  def test_write_is_a_barrier(self): self.assertEqual([["READ"], ["WRITE"], ["READ"]], self.ops(r("a"), w("b"), r("c")))
  def test_run_is_a_barrier(self): self.assertEqual([["WRITE"], ["RUN"]], self.ops(w("a"), c("pytest")))
  def test_nothing(self): self.assertEqual([], groups([]))

class TestRun(unittest.TestCase):
  def setUp(self):
    self.old, self.d = os.getcwd(), tempfile.mkdtemp()
    os.chdir(self.d); subprocess.run(["git", "init", "-q"], check=True)
    os.environ.update(MODEL="mock", TINYAGENT_DB=os.path.join(self.d, "db"))
    for k in ("REPLAY", "BEAM", "VERIFY", "STEPS", "MAXCMD"): os.environ.pop(k, None)
  def tearDown(self): os.chdir(self.old)
  def go(self, *turns):
    os.environ["MOCK"] = "|".join(t.replace("\n", "\\n") for t in turns)
    return run("make it work")

  def test_write_run_done(self):
    root, st = self.go('WRITE hi.py\n<<<\nprint("hi")\n>>>\nRUN python3 hi.py', "DONE it prints")
    self.assertEqual((Op.DONE, "it prints"), (root.op, root.arg))
    self.assertEqual((2, 3), (st.samples, st.tools))   # the seeded file list counts
    self.assertEqual('print("hi")\n', open("hi.py").read())
  def test_a_failing_command_comes_back_as_a_failure(self):
    root, st = self.go("RUN exit 7", "DONE whatever")
    self.assertEqual(2, st.tools)
    self.assertEqual("whatever", root.arg)
  def test_three_identical_failures_stop_the_run(self):
    root, st = self.go("RUN exit 7", "RUN exit 7", "RUN exit 7", "DONE never gets here")
    self.assertTrue(root.arg.startswith("gave up"), root.arg)
    self.assertEqual(3, st.samples)
  def test_out_of_steps(self):
    os.environ["STEPS"] = "2"
    try: self.assertIn("out of steps", self.go("RUN echo 1", "RUN echo 2", "RUN echo 3", "DONE never")[0].arg)
    finally: del os.environ["STEPS"]
  def test_the_model_sees_what_it_ran(self):
    self.assertEqual("saw it", self.go("RUN echo marker", "DONE saw it")[0].arg)
  def test_verify_runs_before_the_first_sample(self):
    os.environ["VERIFY"] = "echo the-failing-test; exit 1"
    try: root, st = self.go("DONE looked at it")
    finally: del os.environ["VERIFY"]
    self.assertEqual((1, 2), (st.samples, st.tools))
  def test_it_opens_on_the_file_list(self):
    root, st = self.go("DONE saw the tree")
    self.assertEqual((1, 1), (st.samples, st.tools))
  def test_at_most_eight_commands_a_turn(self):
    os.environ["MAXCMD"] = "3"
    try: root, st = self.go("\n".join(f"RUN echo {i}" for i in range(9)), "DONE enough")
    finally: del os.environ["MAXCMD"]
    self.assertEqual(4, st.tools)   # the file list, then three of the nine
  def test_a_multiline_command_runs_whole(self):
    root, st = self.go('RUN python3 -\n<<<\nprint("from stdin")\n>>>', "DONE ran it")
    self.assertEqual(2, st.samples)
  def test_replay_costs_nothing(self):
    self.go("RUN echo one", "DONE first")
    os.environ["REPLAY"], os.environ["MOCK"] = "1", "DONE this script is not used"
    try: root, st = run("make it work")
    finally: del os.environ["REPLAY"]
    self.assertEqual("first", root.arg)
    self.assertEqual(2, st.samples)

if __name__ == "__main__": unittest.main()
