#!/usr/bin/env python3
import os, sys
LIMIT = 1000   # the whole point. a feature that does not fit deletes something that does not earn its keep
def count(f): return sum(1 for l in open(os.path.join("tinyagent", f)) if l.strip())
rows = sorted(((count(f), f) for f in os.listdir("tinyagent") if f.endswith(".py")), reverse=True)
for n, f in rows: print(f"{f:15s} {n:5d}")
print(f"{'total':15s} {(tot:=sum(n for n, _ in rows)):5d} / {LIMIT}")
sys.exit(tot > LIMIT)
