#!/usr/bin/env python3
"""test_pipeline_reap: check the batch bookkeeping in tools/pipeline.py (reap) without running a build or Comparator.

Purpose: pipeline.py submits a batch's checks right after its build and archives the batch's generated C only when all its checks
are done, keeping files another pending batch or the next build still needs. It cannot be imported (it runs on import), so this
pulls the reap function out of the source, runs it against stub futures and a recording archive(), and asserts the cases:
nothing archived while a check runs; a finished batch is archived; shared files are kept; a slow batch does not block a later
finished one; block_oldest waits for the oldest. Usage: test_pipeline_reap.py   (exit 0 and "ok" when all pass)
"""
import ast, os, time, threading, concurrent.futures as cf
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pipeline.py')).read()
fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == 'reap')
calls = []
ns = dict(pending=[], archive=lambda name, files: calls.append((name.split('-')[0], sorted(files))), time=time)
exec(compile(ast.Module([fn], []), 'reap', 'exec'), ns)
reap, pending = ns['reap'], ns['pending']
pool = cf.ThreadPoolExecutor(4); gate = threading.Event()
slow = pool.submit(gate.wait); fast = pool.submit(lambda: None); fast.result()
pending += [([slow], ['a', 'shared'], 'b1'), ([fast], ['c', 'shared', 'd'], 'b2')]
reap(keep=['d'])
assert calls == [('batchb2', ['c'])], calls                      # b2 done: archived without 'shared' (b1 still needs it) or 'd' (next build)
assert [e[2] for e in pending] == ['b1']                         # the slow batch stays; it did not block b2
gate.set(); reap(block_oldest=True)
assert calls[-1] == ('batchb1', ['a', 'shared']) and not pending, calls
print('ok')
