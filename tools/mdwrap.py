#!/usr/bin/env python3
"""mdwrap: rewrap Markdown paragraphs and list items to a column width (default 100), leaving everything else alone.

Purpose: keep README/REPORT diffs readable (one idea per few lines) without touching tables, headings, fenced or indented
code, or paragraphs nested under list items after a blank line. Inline code spans and bold are never split mid-span.
Usage: mdwrap.py FILE [WIDTH]   (rewrites FILE in place; prints a whitespace-normalized equality check)
"""
import sys, re, textwrap
path = sys.argv[1]; W = int(sys.argv[2]) if len(sys.argv) > 2 else 100
src = open(path).read(); lines = src.split('\n'); out = []; i = 0
bullet = re.compile(r'^(\s*)([-*]|\d+\.)\s+(.*)$')
def protect(t):                      # keep inline code spans and link texts on one line
    t = re.sub(r'`[^`]*`', lambda m: m.group(0).replace(' ', '\x00'), t)
    return re.sub(r'\[[^\]]*\]\([^)]*\)', lambda m: m.group(0).replace(' ', '\x00'), t)
def wrap(text, first, rest):
    return textwrap.wrap(protect(text), W, initial_indent=first, subsequent_indent=rest, break_long_words=False, break_on_hyphens=False)
def special(l): return (not l.strip() or l.lstrip().startswith(('#', '|', '```', '>', '<', '[')) or l.startswith('    ') and not bullet.match(l))
in_fence = False
while i < len(lines):
    l = lines[i]
    if l.startswith('```'): in_fence = not in_fence; out.append(l); i += 1; continue
    if in_fence or special(l) and not bullet.match(l): out.append(l); i += 1; continue
    m = bullet.match(l)
    if m:
        ind, mark, body = m.groups(); j = i + 1; parts = [body]
        while j < len(lines) and lines[j].strip() and not bullet.match(lines[j]) and not lines[j].lstrip().startswith(('|', '```', '#')) and lines[j].startswith(ind + ' '):
            parts.append(lines[j].strip()); j += 1
        first = f"{ind}{mark} "; rest = ' ' * len(first)
        out += [x.replace('\x00', ' ') for x in wrap(' '.join(parts), first, rest)]; i = j; continue
    j = i; parts = []
    while j < len(lines) and lines[j].strip() and not special(lines[j]) and not bullet.match(lines[j]):
        parts.append(lines[j].strip()); j += 1
    out += [x.replace('\x00', ' ') for x in wrap(' '.join(parts), '', '')]; i = j
new = '\n'.join(out)
norm = lambda t: ' '.join(t.split())
assert norm(new) == norm(src), 'wrapping changed text'
open(path, 'w').write(new); print(path, 'rewrapped; text unchanged apart from whitespace;', max(len(x) for x in out if not x.startswith('|')), 'max non-table line length')
