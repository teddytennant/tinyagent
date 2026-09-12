from __future__ import annotations
import os, shlex, subprocess
from tinyagent.graph import N, Op, DEBUG, getenv

TIMEOUT = getenv("TIMEOUT", 180)

def parse(txt:str) -> list[N]:
  # the wire format is lines, not a vendor tool schema. every model can emit lines, including the
  # 3B one you are running locally, and you can read the transcript without a json pretty printer
  out, lines, i = [], [l for l in txt.split("\n") if l.strip() != "```"], 0
  while i < len(lines):
    l, i = lines[i].strip(), i+1
    if not l or " " not in l and l not in ("DONE",): continue
    verb, _, rest = l.partition(" ")
    if verb == "READ" and rest: out.append(N(Op.READ, (), rest.strip()))
    elif verb == "GREP" and rest:
      pat, _, glob = rest.rpartition(" ")
      if "*" not in glob: pat, glob = rest, "*"   # models forget the glob. a trailing word with no star is pattern
      out.append(N(Op.GREP, (), (pat.strip(), glob.strip())))
    elif verb == "RUN" and rest: out.append(N(Op.RUN, (), rest.strip()))
    elif verb == "DONE": out.append(N(Op.DONE, (), rest.strip() or "done"))
    elif verb == "WRITE" and rest:
      body:list[str] = []
      while i < len(lines) and lines[i].strip() != "<<<": i += 1
      i += 1
      while i < len(lines) and lines[i].strip() != ">>>": body.append(lines[i]); i += 1
      i += 1
      out.append(N(Op.WRITE, (), (rest.strip(), "\n".join(body) + "\n")))
  return out

def ok(n:N, s:str) -> N: return N(Op.TEXT, (n,), s)
def bad(n:N, rc:int, s:str) -> N: return N(Op.FAIL, (n,), (rc, s))

def t_read(n:N) -> N:
  try: return ok(n, open(n.arg, errors="replace").read())
  except OSError as e: return bad(n, 1, str(e))

def t_grep(n:N) -> N:
  pat, glob = n.arg
  p = sh(["grep", "-rn", "--binary-files=without-match", "--exclude-dir=.git", f"--include={glob}", "-e", pat, "."])
  if p.returncode > 1: return bad(n, p.returncode, p.stderr or p.stdout)
  return ok(n, p.stdout or "no matches")

def t_run(n:N) -> N:
  p = sh(n.arg, shell=True)
  out = (p.stdout + p.stderr).strip() or "(no output)"
  return ok(n, out) if p.returncode == 0 else bad(n, p.returncode, out)

def t_write(n:N) -> N:
  path, content = n.arg
  try:
    if (d:=os.path.dirname(path)): os.makedirs(d, exist_ok=True)
    if os.path.exists(path) and open(path, errors="replace").read() == content: return ok(n, "unchanged")
    open(path, "w").write(content)
    return ok(n, f"wrote {len(content)} bytes")
  except OSError as e: return bad(n, 1, str(e))

def sh(cmd, shell=False) -> subprocess.CompletedProcess:
  if DEBUG >= 3: print(f"+ {cmd if shell else shlex.join(cmd)}")
  try: return subprocess.run(cmd, shell=shell, capture_output=True, text=True, errors="replace", timeout=TIMEOUT)
  except subprocess.TimeoutExpired: return subprocess.CompletedProcess(cmd, 124, "", f"timed out after {TIMEOUT}s")

exec_tool = {Op.READ: t_read, Op.GREP: t_grep, Op.RUN: t_run, Op.WRITE: t_write}
