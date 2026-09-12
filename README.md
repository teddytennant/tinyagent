# tinyagent

a coding agent in 400 lines of python. no dependencies.

    agent 'the odd stride test fails, fix it'

it reads, greps, writes files, runs commands, stops. there is no agent loop in here.
the state is a graph and the loop is a rewrite table over it.

```
graph.py    78     device.py   42
rewrite.py  73     replay.py   39
schedule.py 55     beam.py     36
tools.py    54     main.py     19     total 396 / 1000
```

the 1000 is checked in CI. want a feature, go find the lines.

### the graph

nine ops. `SPEC READ GREP RUN WRITE TEXT FAIL SAMPLE DONE`. nodes are interned on
`(op, src, arg)`, so reading the same file twice is the same object and the dedup is
free. running a tool doesn't mutate anything, it makes a new node holding the old one,
so the history is the graph.

### the rules

no `while True` with branches in it. a PatternMatcher to fixpoint. here is the entire
retry policy:

```python
def giveup(x):
  cmds = [n.tool.arg for n in x.src if n.op is Op.FAIL and n.tool.op is Op.RUN]
  for c in cmds:
    if cmds.count(c) >= 3: return N(Op.DONE, (), f"gave up: `{c}` failed 3 times")
```

four rules run the thing: `finish`, `giveup`, `dce`, `trunc`. a rule that oscillates
raises after 8 passes. an agent that silently spins is worse than one that crashes.

### context

`render()` walks the live graph before every sample. a read of a file it has since
overwritten isn't reachable, so it doesn't render. that's the whole compaction story,
it's just DCE.

it never sees its own replies either, only what the commands printed. half of what most
harnesses bill you for every turn is the model talking to itself.

### scheduling

SAMPLE is the only op that costs money. reads and greps sitting next to each other go
out in one batch. a write or a run is a barrier, it asked for those in an order.

### models

40 lines a backend or it doesn't get merged. `MODEL=claude-opus-5`, `MODEL=gpt-5`, or
anything that speaks `/v1/chat/completions`:

    MODEL=qwen3-coder OPENAI_BASE=http://localhost:8080/v1 agent 'fix the flaky test'

the wire format is lines, not a vendor tool schema. a 3B model can emit lines, and you
can read a transcript without a json pretty printer.

```
READ tinyagent/graph.py
GREP def render *.py
RUN python -m pytest -x
WRITE hello.py
<<<
print("hi")
>>>
DONE it prints
```

### BEAM

`BEAM=4` samples 4 patches, applies each in its own git worktree, runs VERIFY in all of
them, keeps one that passes. ties go to fewest output tokens so it's reproducible. your
uncommitted changes get patched in first. a worktree at HEAD is not the repo the model
has been reading all session.

### replay

every context that ever went to a model is in sqlite, byte for byte.

    REPLAY=1 agent 'same thing again'   # no network, costs nothing
    python -m tinyagent.replay          # list runs
    python -m tinyagent.replay 41 42    # diff what the model saw

change the renderer and you see which bytes it stops seeing. prompt changes being
invisible is the whole problem with prompt changes.

## install

    pip install -e .
    export ANTHROPIC_API_KEY=...
    cd ~/some/repo
    VERIFY='python -m pytest -x' agent 'padding is wrong on odd strides'

it edits your working tree. commit first. git is the undo and this thing never pushes.

## env

```
MODEL     claude-opus-5, gpt-5, whatever your local server calls it
VERIFY    the command that decides if it's done. runs first, and last
CTX       context budget in bytes, default 120000
STEPS     max turns, default 24
BEAM      sample k patches a turn, keep one that passes VERIFY
TIMEOUT   per command, default 180s
MAXOUT    longest output it sees, default 8000 bytes
PRICE     "3,15" $/Mtok in,out, if you want the cost printed
REPLAY    replay the nth most recent run instead of sampling
DEBUG     1 cost, 2 the graph, 3 commands and replies, 4 the whole context
NODIFF    skip the diff at the end
```

## no

no permission prompts, you'd click through them anyway. no MCP, a tool is a subprocess
with argv and that protocol shipped in 1973. no plugins, add a rule. no subagents, a
subagent is a sample whose context is a subgraph, `render()` just needs to take a root.
no RAG, grep is exact and has no index to go stale. no memory directory, facts that
matter go in the repo where someone reviews them. no TODO list, `DEBUG=2` prints the
graph. no TUI, stdout is a diff, pipe it.

## tests

    python -m pytest test/ -q     # 60 of them, no network
    python sz.py                  # the line count
    python docs/abstractions.py   # the docs, which run

a rule without a test gets deleted, not documented. `docs/design.md` is what this
design costs you, read it before sending a PR that undoes something on purpose.
