#!/usr/bin/env python3
# the design doc. it runs. `python3 docs/abstractions.py` from the repo root
# if something here stops being true the doc fails, which is the only way a doc stays true

# %% 1. there is no message list

# state is one immutable graph. nine ops, and only one of them costs money
from tinyagent.graph import N, Op, render, substitute
print([o.name for o in Op])

# nodes are interned on (op, src, arg), so the same read twice is the same object. context dedup is
# not a feature anyone wrote, it falls out of the constructor
assert N(Op.READ, (), "graph.py") is N(Op.READ, (), "graph.py")

# a tool call is a leaf. running it does not mutate it, it produces a new node that keeps the old one
# in src. history is in the graph, not in a log file
read = N(Op.READ, (), "hello.py")
done = N(Op.TEXT, (read,), "print('hi')\n")
assert done.tool is read

# %% 2. the loop is a rewrite table

from tinyagent.rewrite import Pat, PatternMatcher, graph_rewrite, rules

# a rule is a pattern and a function. this one is the whole retry policy
giveup = PatternMatcher([(Pat(Op.FAIL, name="f"), lambda f: N(Op.DONE, (), f"stop: {f.arg[0]}"))])
assert graph_rewrite(N(Op.FAIL, (N(Op.RUN, (), "pytest"),), (1, "boom")), giveup).op is Op.DONE

# the real table is four rules. that is the entire control flow of the agent
print(sorted({fn.__name__ for lst in rules.pdict.values() for _, fn in lst}))

# three failures of the same command is not a fourth attempt, it is a bug report. note that the retry
# limit is a property of the graph, not a counter threaded through five call frames
fail = N(Op.FAIL, (N(Op.RUN, (), "pytest"),), (1, "boom"))
assert graph_rewrite(N(Op.SPEC, (fail, fail, fail), "fix it"), rules).op is Op.DONE

# %% 3. context is recomputed, never accumulated

# render() walks the live graph fresh before every sample. a read of a file the model has since
# overwritten is unreachable, so it does not render. that is the whole compaction story
stale = N(Op.TEXT, (N(Op.READ, (), "a.py"), ), "the old contents")
wrote = N(Op.TEXT, (N(Op.WRITE, (), ("a.py", "the new contents")),), "wrote 16 bytes")
live = graph_rewrite(N(Op.SPEC, (stale, wrote), "rewrite a.py"), rules)
assert "the old contents" not in render(live) and "wrote 16 bytes" in render(live)

# the model never sees its own previous replies, only what its commands printed. half the transcript
# most harnesses pay for every turn is the model talking to itself
print(render(live).split("\n\n")[-1])

# %% 4. scheduling

from tinyagent.schedule import groups

# reads and greps next to each other are one batch, one syscall round, one turn. a write or a run is a
# barrier because the model asked for them in an order and it meant it
plan = [N(Op.READ, (), "a.py"), N(Op.GREP, (), ("def f", "*.py")), N(Op.WRITE, (), ("a.py", "x\n")), N(Op.RUN, (), "pytest")]
assert [[n.op.name for n in g] for g in groups(plan)] == [["READ", "GREP"], ["WRITE"], ["RUN"]]

# realizing a group is a substitution. the tool nodes are replaced by their output everywhere at once
out = substitute(N(Op.SPEC, (read,), "go"), {read: done})
assert out.src[0] is done

# %% 5. what is left

# device.py  three backends behind sample(ctx, temp) -> (text, tin, tout)
# beam.py    BEAM=k samples k patches, applies each in its own git worktree, keeps one that passes VERIFY
# replay.py  every context that ever went to a model, byte for byte, in sqlite. REPLAY=1 needs no network
# main.py    argv in, git diff out
print("ok")
