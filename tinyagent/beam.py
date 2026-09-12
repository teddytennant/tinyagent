from __future__ import annotations
import os, shutil, tempfile
from concurrent.futures import ThreadPoolExecutor
from tinyagent.graph import Op, DEBUG, getenv
from tinyagent.tools import parse, sh

BEAM, TEMP = getenv("BEAM"), float(os.getenv("TEMP", "0.8"))

def sample(dev, ctx:str, k:int) -> tuple[str, int, int]:
  # kernel search, pointed at patches. sample k, apply each in its own worktree, keep one that passes
  # VERIFY. ties go to the fewest output tokens, so the choice is reproducible and not a race
  assert (v:=os.getenv("VERIFY")), "BEAM needs VERIFY, there is nothing to search against without it"
  with ThreadPoolExecutor(k) as p: outs = list(p.map(lambda i: dev.sample(ctx, 0.0 if i == 0 else TEMP), range(k)))
  base = sh(["git", "diff", "HEAD"]).stdout
  scored = []
  for i, o in enumerate(outs):
    ws = [n.arg for n in parse(o[0]) if n.op is Op.WRITE]
    rc = try_it(ws, base, v) if ws else 2
    scored.append((rc if rc in (0, 2) else 1, o[2], i, o))
    if DEBUG >= 1: print(f"  beam {i}: {len(ws)} writes, {o[2]} tok, verify {'pass' if rc == 0 else 'fail' if rc == 1 else 'n/a'}")
  scored.sort(key=lambda x: x[:3])
  return scored[0][3]

def try_it(writes:list[tuple[str, str]], base:str, verify:str) -> int:
  d = tempfile.mkdtemp(prefix="tinyagent-")
  if sh(["git", "worktree", "add", "--detach", "-q", d, "HEAD"]).returncode: shutil.rmtree(d, True); return 1
  try:
    # the candidate gets tested against what is actually in the tree, not against HEAD. a worktree at
    # HEAD is a different repo than the one the model has been reading all session
    if base.strip():
      open(pf:=os.path.join(d, ".tinyagent.patch"), "w").write(base)
      sh(["git", "-C", d, "apply", pf]); os.unlink(pf)
    for path, content in writes:
      full = os.path.join(d, path)
      if (p:=os.path.dirname(full)): os.makedirs(p, exist_ok=True)
      open(full, "w").write(content)
    return sh(f"cd {d} && {verify}", shell=True).returncode
  finally:
    sh(["git", "worktree", "remove", "--force", d]); shutil.rmtree(d, True)
