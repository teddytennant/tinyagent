from __future__ import annotations
import os, sys
from tinyagent.graph import getenv
from tinyagent.schedule import run
from tinyagent.tools import sh

def main(argv:list[str]) -> int:
  if not argv: print("usage: agent 'make test_conv.py::test_padded pass'", file=sys.stderr); return 2
  if sh(["git", "rev-parse", "--git-dir"]).returncode: print("not a git repo. git is the only undo there is", file=sys.stderr); return 2
  root, st = run(" ".join(argv))
  print(f"\n{root.arg}\n{st}", file=sys.stderr)
  if not getenv("NODIFF"):
    # a file the model created is part of the diff, git just does not think so yet. only the files it
    # wrote, not everything untracked, or the diff is mostly build output
    if st.wrote: sh(["git", "add", "-N", "--"] + sorted(st.wrote))
    print(sh(["git", "--no-pager", "diff"]).stdout, end="")
  if (v:=os.getenv("VERIFY")): return sh(v, shell=True).returncode
  return 1 if root.arg.startswith(("gave up", "out of steps")) else 0

def cli(): raise SystemExit(main(sys.argv[1:]))

if __name__ == "__main__": cli()
