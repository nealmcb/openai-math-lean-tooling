#!/usr/bin/env python3
"""test_memvalve: check the freeze/thaw rule of tools/memvalve.py without touching any process. Prints "ok" or fails an assertion."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memvalve import valve_decision as d
assert d(False, 0, 3, 20) == (None, 0)                     # calm and plenty of memory: nothing
assert d(False, 0, 26, 20) == ('pause', 0)                 # pressure above 25%
assert d(False, 0, 3, 2.5) == ('pause', 0)                 # available memory under 3 GiB
assert d(True, 0, 3, 3.5) == (None, 0)                     # still below the 4.5 GiB resume line: stay frozen
assert d(True, 0, 3, 8) == (None, 1) and d(True, 1, 3, 8) == (None, 2) and d(True, 2, 3, 8) == ('resume', 0)   # three calm samples
assert d(True, 2, 12, 8) == (None, 0)                      # pressure still above 8% resets the count
print('ok')
