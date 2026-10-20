"""Bounded, expiring main-thread work. No Isaac dependency."""
from collections import deque
from dataclasses import dataclass, field
import queue
import threading
import time

@dataclass
class Work:
    op: str
    args: dict
    deadline: float
    reply: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=1))
    cancelled: bool = False
    started: bool = False

    def finish(self, ok, result):
        try:
            self.reply.put_nowait((ok, result))
        except queue.Full:
            pass

class WorkQueue:
    def __init__(self, limit=256, clock=time.monotonic):
        self.items = deque()
        self.lock = threading.Lock()
        self.limit = limit
        self.clock = clock
        self.expired = self.superseded = 0

    def put(self, op, args, ttl):
        work = Work(op, args, self.clock() + max(0, ttl))
        with self.lock:
            kept = deque()
            for old in self.items:
                replace = (op == old.op == 'capture_frame' or
                           op == old.op == 'teleop_sample' and
                           args.get('token') == old.args.get('token'))
                if old.cancelled or old.deadline <= self.clock() or replace:
                    old.cancelled = True
                    old.finish(False, 'superseded' if replace else 'expired')
                    if replace: self.superseded += 1
                    else: self.expired += 1
                else:
                    kept.append(old)
            self.items = kept
            if len(self.items) >= self.limit:
                raise RuntimeError('bridge is saturated; try again')
            self.items.append(work)
        return work

    def cancel(self, work):
        with self.lock:
            work.cancelled = True

    def take(self):
        with self.lock:
            while self.items:
                work = self.items.popleft()
                if work.cancelled or work.deadline <= self.clock():
                    self.expired += 1
                    work.finish(False, 'expired before execution')
                    continue
                work.started = True
                return work
        return None

    def status(self):
        with self.lock:
            return dict(pending=len(self.items), expired=self.expired, superseded=self.superseded)
