"""One original CLOCK_BOOTTIME budget, including preparation and suspend.

A failed/rebooted clock prohibits dispatch. Recovery of closed bytes and bounded
safety cleanup remain possible. This is not a guarantee against OS/daemon hangs
or an owner killed before cleanup; such executions remain unclosed, never ready.
"""
from __future__ import annotations

import hashlib
import os
import re
import time


DEADLINE_POLICY = {'schema':1,'clock':'CLOCK_BOOTTIME','elapsed_seconds':6000,
                   'cleanup_reserve_seconds':60,'preparation_minimum_seconds':90,
                   'control_seconds':15,'cleanup_after_expiry':'bounded-stop-only-never-ready'}


class AttemptDeadlineError(ValueError):
    pass


def clock():
    fd = os.open('/proc/sys/kernel/random/boot_id',os.O_RDONLY|os.O_NOFOLLOW)
    try: boot = os.read(fd,128)
    finally: os.close(fd)
    if re.fullmatch(rb'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\n',boot) is None:
        raise AttemptDeadlineError('unknown attempt boot clock')
    return {'boot_id_sha256':hashlib.sha256(boot).hexdigest(),
            'host_id_sha256':hashlib.sha256(os.uname().nodename.encode()).hexdigest(),
            'boottime_ns':time.clock_gettime_ns(time.CLOCK_BOOTTIME),'epoch_ns':time.time_ns()}


class AttemptBudget:
    def __init__(self,start,initial_sha256):
        if (type(start) is not dict or set(start) != {'boot_id_sha256','host_id_sha256','boottime_ns','epoch_ns'}
                or any(type(start[k]) is not str or re.fullmatch(r'[0-9a-f]{64}',start[k]) is None
                       for k in ('boot_id_sha256','host_id_sha256'))
                or any(type(start[k]) is not int or start[k] < 0 for k in ('boottime_ns','epoch_ns'))
                or type(initial_sha256) is not str or re.fullmatch(r'[0-9a-f]{64}',initial_sha256) is None):
            raise AttemptDeadlineError('exact original attempt clock and initial SHA required')
        self.start = dict(start); self.initial_sha256 = initial_sha256
        self.deadline_ns = start['boottime_ns'] + DEADLINE_POLICY['elapsed_seconds']*10**9

    @property
    def binding(self):
        return {'schema':1,'initial_sha256':self.initial_sha256,'clock':dict(self.start),
                'deadline_boottime_ns':self.deadline_ns,'policy':dict(DEADLINE_POLICY)}

    def remaining(self,*,reserve=0):
        now = clock()
        if (now['boot_id_sha256'] != self.start['boot_id_sha256']
                or now['host_id_sha256'] != self.start['host_id_sha256']
                or now['boottime_ns'] < self.start['boottime_ns']):
            raise AttemptDeadlineError('attempt host/boot clock changed; never reset its budget')
        if type(reserve) not in (int,float) or not 0 <= reserve <= 6000:
            raise AttemptDeadlineError('invalid original budget reserve')
        return (self.deadline_ns-now['boottime_ns'])/1e9-reserve

    def admit(self,*,reserve=0):
        left = self.remaining(reserve=reserve)
        if left <= 0: raise AttemptDeadlineError('whole original attempt budget exhausted')
        return left
