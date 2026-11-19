"""Per-thread CPU of a process tree, until its root exits: what each Dolphin and ffmpeg thread used.

    python3 thread_sampler.py ROOT_PID [INTERVAL]

Reads /proc/PID/task/TID/stat (utime + stime) of every descendant, keeping each thread's last value, and prints
CPU seconds per process and thread name, and the cores they kept busy on average.
"""
import os
import sys
import time

root, interval = int(sys.argv[1]), float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
tick = os.sysconf("SC_CLK_TCK")


def stat(path):
    with open(path) as f:
        text = f.read()
    comm = text[text.index("(") + 1:text.rindex(")")]
    rest = text[text.rindex(")") + 2:].split()
    return comm, int(rest[1]), int(rest[11]) + int(rest[12])   # comm, ppid, utime + stime


def tree():
    kids = {}
    for pid in os.listdir("/proc"):
        if pid.isdigit():
            try:
                _, ppid, _ = stat(f"/proc/{pid}/stat")
            except (OSError, ValueError):
                continue
            kids.setdefault(ppid, []).append(int(pid))
    out, todo = [], [root]
    while todo:
        p = todo.pop()
        out.append(p)
        todo += kids.get(p, [])
    return out


threads, procs = {}, {}   # (pid, tid) -> (process name, thread name, ticks); pid -> (name, ticks)
t0 = time.monotonic()
while os.path.exists(f"/proc/{root}"):
    for pid in tree():
        try:
            pname, _, pticks = stat(f"/proc/{pid}/stat")
            procs[pid] = (pname, pticks)
            for tid in os.listdir(f"/proc/{pid}/task"):
                tname, _, ticks = stat(f"/proc/{pid}/task/{tid}/stat")
                threads[(pid, int(tid))] = (pname, tname, ticks)
        except (OSError, ValueError):
            continue
    time.sleep(interval)
wall = time.monotonic() - t0

print(f"wall {wall:.1f} s")
print("processes (CPU s, average cores):")
for pid, (name, ticks) in sorted(procs.items(), key=lambda kv: -kv[1][1]):
    if ticks / tick >= 0.5:
        print(f"  {name:<18} pid {pid:<8} {ticks / tick:8.1f} s  {ticks / tick / wall:5.2f}")
groups = {}
for (pid, _), (pname, tname, ticks) in threads.items():
    key = (pname, tname.rstrip("0123456789") or tname)
    n, total = groups.get(key, (0, 0))
    groups[key] = (n + 1, total + ticks)
print("threads, grouped by name (CPU s, average cores, threads):")
for (pname, tname), (n, ticks) in sorted(groups.items(), key=lambda kv: -kv[1][1]):
    if ticks / tick >= 0.5:
        print(f"  {pname:<18} {tname:<20} {ticks / tick:8.1f} s  {ticks / tick / wall:5.2f}  x{n}")
