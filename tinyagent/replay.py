from __future__ import annotations
import difflib, os, sqlite3, sys, time
from tinyagent.graph import getenv

def db() -> sqlite3.Connection:
  DB = os.path.expanduser(os.getenv("TINYAGENT_DB", "~/.cache/tinyagent/replay.db"))
  os.makedirs(os.path.dirname(DB), exist_ok=True)
  c = sqlite3.connect(DB)
  c.execute("create table if not exists runs(id integer primary key, ts real, spec text, model text)")
  c.execute("create table if not exists samples(run int, i int, ctx text, out text, tin int, tout int)")
  return c

class Recorder:
  # every context that ever went to a model, byte for byte. REPLAY=1 runs the whole loop back off this
  # with no network, which is the only way to know what a prompt change actually changed
  def __init__(self, spec:str, model:str):
    self.c, self.src = db(), None
    if (replay:=getenv("REPLAY")):
      row = self.c.execute("select id from runs order by id desc limit ?", (replay,)).fetchall()
      assert row, "nothing recorded to replay"
      self.src = [r for r in self.c.execute("select ctx, out, tin, tout from samples where run=? order by i", (row[-1][0],))]
    self.run = self.c.execute("insert into runs(ts, spec, model) values(?,?,?)", (time.time(), spec, model)).lastrowid
    self.c.commit()
  def get(self, i:int):
    return self.src[i] if self.src is not None and i < len(self.src) else None
  def put(self, i:int, ctx:str, out:str, tin:int, tout:int):
    self.c.execute("insert into samples values(?,?,?,?,?,?)", (self.run, i, ctx, out, tin, tout)); self.c.commit()

def main(argv:list[str]):
  c = db()
  if not argv:
    for i, ts, spec, model in c.execute("select id, ts, spec, model from runs order by id desc limit 20"):
      n, = c.execute("select count(*) from samples where run=?", (i,)).fetchone()
      print(f"{i:5d} {time.strftime('%m-%d %H:%M', time.localtime(ts))} {model:22s} {n:2d} samples  {spec[:60]}")
    return 0
  a, b = (int(x) for x in argv[:2])
  for i, (x, y) in enumerate(zip(ctxs(c, a), ctxs(c, b))):
    d = list(difflib.unified_diff(x.split("\n"), y.split("\n"), f"run{a}/{i}", f"run{b}/{i}", lineterm=""))
    print("\n".join(d) if d else f"--- sample {i} identical")
  return 0

def ctxs(c:sqlite3.Connection, run:int) -> list[str]: return [r[0] for r in c.execute("select ctx from samples where run=? order by i", (run,))]

if __name__ == "__main__": raise SystemExit(main(sys.argv[1:]))
