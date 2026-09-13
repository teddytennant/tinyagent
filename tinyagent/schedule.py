from __future__ import annotations
import os, time
from concurrent.futures import ThreadPoolExecutor
from tinyagent.graph import N, Op, TOOL, PURE, DEBUG, getenv, render, substitute, printgraph
from tinyagent.rewrite import rules, graph_rewrite
from tinyagent.tools import parse, exec_tool
from tinyagent.device import device, model
from tinyagent.beam import BEAM, sample as beamsample
from tinyagent.replay import Recorder

class Stats:
  def __init__(self):
    self.samples = self.tin = self.tout = self.tools = 0; self.cost = 0.0; self.wrote:set[str] = set(); self.t0 = time.perf_counter()
  def __repr__(self):
    return f"{self.samples} samples  {self.tools} tools  {self.tin} in  {self.tout} out  ${self.cost:.4f}  {time.perf_counter()-self.t0:.1f}s"

def groups(todo:list[N]) -> list[list[N]]:
  # reads and greps next to each other are one syscall batch and one turn. a write or a run is a
  # barrier, because the model asked for them in an order and it meant it
  out:list[list[N]] = []
  for n in todo:
    if n.op in PURE and out and out[-1][-1].op in PURE: out[-1].append(n)
    else: out.append([n])
  return out

def realize(g:list[N]) -> dict[N, N]:
  if len(g) == 1: return {g[0]: exec_tool[g[0].op](g[0])}
  with ThreadPoolExecutor(len(g)) as p: return dict(zip(g, p.map(lambda n: exec_tool[n.op](n), g)))

def run(spec:str, st:Stats|None=None) -> tuple[N, Stats]:
  # VERIFY is the first thing that runs, not the last. the model opens on the failure it has to fix
  # instead of spending a turn and 40k tokens finding out what the command is called
  dev, st = device(), st or Stats()
  # it opens on the file list and the failure, the way you would. a model that has to spend a turn
  # working out what the repo even contains spends the next one guessing at filenames
  seed = (N(Op.RUN, (), "git ls-files | head -200"),)
  if (v:=os.getenv("VERIFY")): seed += (N(Op.RUN, (), v),)
  rec, root = Recorder(spec, model()), N(Op.SPEC, seed, spec)
  for _ in range(steps:=getenv("STEPS", 24)):
    root = graph_rewrite(root, rules)
    if DEBUG >= 2: printgraph(root)
    if root.op is Op.DONE: break
    if todo:=[n for n in root.src if n.op in TOOL]:
      for g in groups(todo):
        st.tools += len(g); st.wrote.update(n.arg[0] for n in g if n.op is Op.WRITE)
        if DEBUG >= 1: print(f"  {' '.join(n.op.name.lower() for n in g)}")
        root = graph_rewrite(substitute(root, realize(g)), rules)
        if root.op is Op.DONE: break
      continue
    ctx = render(root)
    if (r:=rec.get(st.samples)) is not None: out, tin, tout = r[1], r[2], r[3]
    else:
      out, tin, tout = beamsample(dev, ctx, BEAM) if BEAM > 1 else dev.sample(ctx)
      rec.put(st.samples, ctx, out, tin, tout)
    st.samples, st.tin, st.tout = st.samples+1, st.tin+tin, st.tout+tout
    st.cost += dev.cost(tin, tout)
    if DEBUG >= 4: print(ctx)
    if DEBUG >= 1: print(f"sample {st.samples}: {len(ctx)}B in, {tout} tok out")
    if DEBUG >= 3: print(out)
    root = N(Op.SPEC, root.src + (N(Op.SAMPLE, (), (model(), tin, tout)),) + tuple(parse(out)), spec)
  else: root = N(Op.DONE, (), f"out of steps ({steps})")
  return root, st
