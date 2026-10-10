#!/usr/bin/env python3
"""idle_guard: run the Comparator job only while the user is away from the machine.

Purpose: the job is hot and loud and makes the laptop laggy, so the user pauses it by hand (tools/pause.sh, SIGSTOP).
This watches GNOME's idle time (Mutter IdleMonitor over D-Bus), the screensaver and the session lock, and RESUMES a
paused run (tools/resume.sh) when the screen blanks: input idle time reaches GNOME's own blank delay
(org.gnome.desktop.session idle-delay, re-read on every check so changing it in Settings applies at once), or logind
reports the session idle, or the screen is locked / the screensaver is active. --away-s adds an optional extra threshold. It NEVER pauses by itself unless started with --pause-on-activity. Works while the screen is locked. Disable temporarily by creating
results/cmp-all/IDLE_GUARD_OFF (the guard then does nothing; manual pause.sh/resume.sh still work).
Transitions are logged to results/cmp-all/idle_guard.log. Usage: idle_guard.py [--away-s N] [--pause-on-activity --active-s 3] [--dry-run]
"""
import os, sys, time, subprocess, argparse, datetime
ap = argparse.ArgumentParser()
ap.add_argument('--away-s', type=float, default=None, help='optional: also resume after this many idle seconds (default: follow the screen blank setting only)')
ap.add_argument('--active-s', type=float, default=3, help='idle below this means the user is active: pause')
ap.add_argument('--pause-on-activity', action='store_true', help='also pause as soon as there is input (off by default)')
ap.add_argument('--poll-s', type=float, default=2); ap.add_argument('--dry-run', action='store_true'); a = ap.parse_args()
base = '/home/srv/s/math/openai-math'; R = base + '/results/cmp-all'
env = dict(os.environ, DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
log = lambda m: (open(R + '/idle_guard.log', 'a').write(f"{datetime.datetime.now().astimezone().isoformat(timespec='seconds')} {m}\n"), print(m, flush=True))


def gdbus(*args):
    return subprocess.run(['gdbus', 'call', '--session'] + list(args), env=env, capture_output=True, text=True, timeout=5).stdout


def idle_seconds():
    out = gdbus('--dest', 'org.gnome.Mutter.IdleMonitor', '--object-path', '/org/gnome/Mutter/IdleMonitor/Core',
                '--method', 'org.gnome.Mutter.IdleMonitor.GetIdletime')
    return int(out.split('uint64')[1].split(',')[0]) / 1000.0              # "(uint64 12972,)"


def blank_delay():
    out = subprocess.run(['gsettings', 'get', 'org.gnome.desktop.session', 'idle-delay'], env=env, capture_output=True, text=True).stdout
    return int(out.split()[-1]) if out.strip() else 0                     # "uint32 480"; 0 means never blank


def away_reason(idle):
    """Why the user counts as away, or None. Follows the screen blank timeout instead of a private threshold."""
    delay = blank_delay()
    if delay and idle >= delay: return f"screen blank delay reached ({idle:.0f}s >= {delay}s)"
    if a.away_s and idle >= a.away_s: return f"idle {idle:.0f}s >= --away-s {a.away_s:.0f}"
    if 'true' in gdbus('--dest', 'org.gnome.ScreenSaver', '--object-path', '/org/gnome/ScreenSaver', '--method', 'org.gnome.ScreenSaver.GetActive'): return "screensaver/lock active"
    sid = subprocess.run(['loginctl', 'show-user', os.environ.get('USER', 'neal'), '-p', 'Display', '--value'], capture_output=True, text=True).stdout.strip()
    if sid:
        p = subprocess.run(['loginctl', 'show-session', sid, '-p', 'IdleHint', '-p', 'LockedHint'], capture_output=True, text=True).stdout
        if 'IdleHint=yes' in p: return "logind session idle"
        if 'LockedHint=yes' in p: return "session locked"
    return None


def paused(): return os.path.exists(R + '/PAUSED_PIDS')
def running(): return subprocess.run(['pgrep', '-f', '^python3 -I tools/pipeline.py'], capture_output=True).returncode == 0


def act(cmd):
    if a.dry_run: print('DRY-RUN would run', cmd); return
    subprocess.run([f'{base}/tools/{cmd}.sh'], stdout=subprocess.DEVNULL)


log(f"idle_guard started: follows screen blank delay ({blank_delay()}s now), away_s={a.away_s}, pause_on_activity={a.pause_on_activity}, dry_run={a.dry_run}")
last_state = None
while True:
    try:
        if os.path.exists(R + '/IDLE_GUARD_OFF'): time.sleep(a.poll_s * 3); continue
        if not running() and not paused(): time.sleep(a.poll_s * 5); continue
        idle = idle_seconds(); away = away_reason(idle)
        if paused() and away:
            log(f"away: {away} -> resume"); act('resume')
        elif a.pause_on_activity and not paused() and idle < a.active_s and running():
            log(f"activity (idle {idle:.1f}s) -> pause"); act('pause')
        if a.dry_run: print(f"idle={idle:.1f}s away={away!r} paused={paused()}")
    except Exception as e:
        log(f"error: {type(e).__name__}: {e}"); time.sleep(10)
    time.sleep(a.poll_s)
