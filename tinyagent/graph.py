from __future__ import annotations
import os, sys, weakref
from enum import Enum, auto
from typing import Any

def getenv(key:str, default=0): return type(default)(os.getenv(key, default))
DEBUG, MAXOUT = getenv("DEBUG"), getenv("MAXOUT", 8000)

class Op(Enum):
  SPEC=auto(); READ=auto(); GREP=auto(); RUN=auto(); WRITE=auto(); TEXT=auto(); FAIL=auto(); SAMPLE=auto(); DONE=auto()
  def __repr__(self): return self.name
TOOL = (Op.READ, Op.GREP, Op.RUN, Op.WRITE)
PURE = (Op.READ, Op.GREP)   # no side effects, safe to fuse

class N:
  __slots__ = ("op", "src", "arg", "__weakref__")
  cache:weakref.WeakValueDictionary = weakref.WeakValueDictionary()
  def __new__(cls, op:Op, src:tuple[N, ...]=(), arg:Any=None):
    if (ret:=N.cache.get(key:=(op, src, arg), None)) is not None: return ret
    N.cache[key] = ret = super().__new__(cls)
    ret.op, ret.src, ret.arg = op, src, arg
    return ret
  def __reduce__(self): return N, (self.op, self.src, self.arg)
  def __repr__(self): return f"N({self.op!r}, {len(self.src)} src, {short(self.arg)})"
  @property
  def tool(self) -> N: return self.src[0] if self.op in (Op.TEXT, Op.FAIL) else self
  def toposort(self) -> list[N]:
    ret, stack = [], [(self, False)]
    seen:set[int] = set()
    while stack:
      n, done = stack.pop()
      if done: ret.append(n); continue
      if id(n) in seen: continue
      seen.add(id(n)); stack.append((n, True))
      for s in n.src: stack.append((s, False))
    return ret

def short(x:Any, n:int=40) -> str: return (s if len(s:=repr(x)) <= n else s[:n]+"...")

def substitute(root:N, m:dict[N, N]) -> N:
  # a replacement keeps the node it replaced in its src, for provenance. that makes the values of m
  # opaque: descend into one and you rewrite a node's own history out from under it
  cache:dict[N, N] = {}
  vals = set(m.values())
  for n in root.toposort():
    if n in m: cache[n] = m[n]
    elif n in vals or not n.src: cache[n] = n
    else: cache[n] = N(n.op, tuple(cache[s] for s in n.src), n.arg)
  return cache[root]

PROTO = """you are editing a git repo from the shell. reply with commands only, no prose, no markdown.

READ <path>
GREP <pattern> <glob>
RUN <shell command>
WRITE <path>
<<<
the entire new contents of the file
>>>
DONE <one line, why you are done>

one command per line, at most 8 a turn. a RUN or a WRITE that needs more than one line puts its
body between <<< and >>> on the lines under it. you get the output of every command back before
your next turn.
you do not see your own previous replies, only what the commands printed. if a command
failed you will see its exit code and output. do not explain, do not apologize, do not
ask questions. if you know the answer already, WRITE it."""

def block(n:N) -> str:
  t = n.tool
  if t.op is Op.READ: head = f"$ cat {t.arg}"
  elif t.op is Op.GREP: head = f"$ grep -rn {t.arg[0]!r} {t.arg[1]}"
  elif t.op is Op.WRITE: head = f"$ write {t.arg[0]}"
  else: head = f"$ {t.arg}"
  if n.op is Op.FAIL: return f"{head}\nexit {n.arg[0]}\n{n.arg[1]}"
  return f"{head}\n{n.arg}"

def render(root:N, budget:int=0) -> str:
  budget = budget or getenv("CTX", 120000)
  assert root.op is Op.SPEC, f"can only render a SPEC, got {root.op}"
  blocks = [block(n) for n in root.src if n.op in (Op.TEXT, Op.FAIL)]
  fixed = len(PROTO) + len(root.arg) + 8
  # drop the oldest droppable block until it fits. reads and greps go first, a failure never goes
  droppable = [i for i, n in enumerate(root.src) if n.op is Op.TEXT and n.tool.op in PURE]
  while sum(len(b) for b in blocks) + fixed > budget and droppable:
    i = droppable.pop(0)
    blocks[i] = block(root.src[i]).split("\n")[0] + "\n[dropped, out of context budget]"
  return "\n\n".join([PROTO, f"# {root.arg}"] + blocks)

def printgraph(root:N):
  for i, n in enumerate(root.toposort()): print(f"{i:3d} {n.op.name:7s} {len(n.src)} {short(n.arg, 90)}", file=sys.stderr)
