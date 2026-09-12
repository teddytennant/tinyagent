# what this buys, and what it costs

The README says what tinyagent does. This is the part you need before deciding to use
it, or before sending a pull request that undoes a decision on purpose.

## the tradeoffs, stated

**Context is recomputed from the graph, not accumulated.** The win is that dead context
disappears without a compaction step. The cost is real: recomputing the prefix every
turn fights provider side prompt caching, and on a cheap model a long session can pay
close to double for tokens it could have cached. The fix is a stable block order, not
an accumulating transcript, and the block order is stable today only because `dce`
preserves the order of `SPEC.src`. Break that and you will see it in the bill before
you see it in a test.

**The model never sees its own replies.** It sees what its commands printed. This is
most of the token saving and it also means the model cannot leave itself a note. When
it needs to remember something across turns it has to write it to a file, which is
where you wanted it anyway.

**Whole file writes.** `WRITE` sends the entire new contents of a file. It is one op, it
cannot half apply, and it never produces the "patch did not apply" spiral that eats
four turns. It also costs output tokens proportional to file size, which on a 2000 line
file is genuinely bad. Splitting the file is the answer, and mostly the file should
have been split anyway.

**No sandbox.** `RUN` is `subprocess.run(shell=True)` with a timeout and nothing else.
A model that decides to `rm -rf` gets to. The branch protects the repo, nothing protects
the rest of the disk, and if that is not acceptable then run it in a container. A
permission dialog would not have saved you, you would have clicked through it.

**Rewrite to fixpoint.** A rule that produces a node matching its own pattern raises
`RuntimeError` after eight passes instead of spinning. You will hit this while writing
rules. That is the intended failure.

## how it actually fails

- Three identical failures stop the run. Three *different* failures do not, so a model
  that fails in a slightly new way each turn burns all of `STEPS`. There is no rule for
  that yet and it is the most common expensive run.
- `MAXOUT` cuts the middle out of long output. A stack trace whose useful frame is in
  the middle gets cut. Raise it for that run rather than guessing.
- `GREP` decides the last word is a glob only if it has a `*` in it. A model that writes
  `GREP def foo src/` greps for `def foo src/` across everything.
- A `DONE` in the same turn as a `RUN` waits for the run, which is right, but a `DONE`
  in the same turn as a failing run still wins. The model gets no chance to see the
  failure it just caused.

## the number worth having

One number, dollars per solved task on a fixed suite, printed on every commit to master.
Not twelve subscores, because you cannot revert against twelve numbers. That harness
does not exist here yet, and until it does, treat every performance claim in this repo
as untested. `DEBUG=1` prints samples, tools, tokens and cost for a single run, which is
the honest version of the same thing.

## contributing

Features arrive as bounties with a test attached. Write the test first, price it, and a
pull request that passes the test without adding a dependency and without pushing the
line count over 1000 gets merged and paid. A pull request that passes the test by adding
a dependency does not.
