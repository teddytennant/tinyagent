from __future__ import annotations
from typing import Any, Callable, Optional
from tinyagent.graph import N, Op, TOOL, MAXOUT

class Pat:
  __slots__ = ("op", "src", "arg", "name")
  def __init__(self, op:Optional[Op|tuple[Op, ...]]=None, src:Optional[tuple[Pat, ...]]=None, arg:Any=None, name:Optional[str]=None):
    self.op:Optional[tuple[Op, ...]] = (op,) if isinstance(op, Op) else op
    self.src, self.arg, self.name = src, arg, name
  def match(self, n:N, store:dict[str, N]) -> bool:
    if self.op is not None and n.op not in self.op: return False
    if self.arg is not None and n.arg != self.arg: return False
    if self.src is not None and (len(self.src) != len(n.src) or not all(p.match(s, store) for p, s in zip(self.src, n.src))): return False
    if self.name is not None: store[self.name] = n
    return True

class PatternMatcher:
  def __init__(self, patterns:list[tuple[Pat, Callable]]):
    self.pdict:dict[Optional[Op], list[tuple[Pat, Callable]]] = {}
    for p, fn in patterns:
      for op in (p.op if p.op is not None else [None]): self.pdict.setdefault(op, []).append((p, fn))
  def rewrite(self, n:N) -> Optional[N]:
    for p, fn in self.pdict.get(n.op, []) + self.pdict.get(None, []):
      if p.match(n, store:={}) and (ret:=fn(**store)) is not None and ret is not n: return ret
    return None

def graph_rewrite(root:N, pm:PatternMatcher, depth:int=8) -> N:
  for _ in range(depth):
    if (new:=_rw(root, pm, {})) is root: return root
    root = new
  raise RuntimeError("rewrite did not converge, a rule is oscillating")

def _rw(n:N, pm:PatternMatcher, cache:dict[N, N]) -> N:
  if (r:=cache.get(n)) is not None: return r
  src = tuple(_rw(s, pm, cache) for s in n.src)
  cache[n] = ret = pm.rewrite(nn:=(N(n.op, src, n.arg) if src != n.src else n)) or nn
  return ret

# the loop. every rule here is a line of control flow you did not have to write as control flow

def dce(x:N) -> Optional[N]:
  # walk backwards keeping the newest of everything. a read the model already redid, or of a file it
  # has since overwritten, is dead, and dead nodes do not render. this is why there is no compaction step
  out, wrote, read = [], set(), set()
  for n in reversed(x.src):
    t = n.tool
    if t.op is Op.WRITE:
      if t.arg[0] in wrote: continue
      wrote.add(t.arg[0])
    elif t.op is Op.READ:
      if t.arg in read or t.arg in wrote: continue
      read.add(t.arg)
    out.append(n)
  return N(Op.SPEC, tuple(reversed(out)), x.arg) if len(out) != len(x.src) else None

def giveup(x:N) -> Optional[N]:
  # three identical failures is not a fourth attempt, it is a bug report. the retry limit is a graph
  # property, not a counter threaded through five call frames
  cmds = [n.tool.arg for n in x.src if n.op is Op.FAIL and n.tool.op is Op.RUN]
  for c in cmds:
    if cmds.count(c) >= 3: return N(Op.DONE, (), f"gave up: `{c}` failed 3 times")
  return None

def finish(x:N) -> Optional[N]:
  # DONE only wins once the work queued in the same turn has run
  if any(n.op in TOOL for n in x.src): return None
  return next((n for n in x.src if n.op is Op.DONE), None)

def trunc(x:N) -> Optional[N]:
  s = x.arg if x.op is Op.TEXT else x.arg[1]
  if len(s) <= MAXOUT: return None
  assert MAXOUT > 256, "MAXOUT too small to cut"
  head, mark = MAXOUT//4, "\n...[%d bytes cut]...\n"
  tail = MAXOUT - head - len(mark % len(s))
  ns = s[:head] + (mark % (len(s)-head-tail)) + s[-tail:]
  return N(Op.TEXT, x.src, ns) if x.op is Op.TEXT else N(Op.FAIL, x.src, (x.arg[0], ns))

rules = PatternMatcher([
  (Pat(Op.SPEC, name="x"), finish),
  (Pat(Op.SPEC, name="x"), giveup),
  (Pat(Op.SPEC, name="x"), dce),
  (Pat((Op.TEXT, Op.FAIL), name="x"), trunc),
])
