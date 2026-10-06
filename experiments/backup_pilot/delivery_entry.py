"""Extra delivery validation only: execute the real CLI with site packages disabled.

exec preserves the process ID/group used by the frozen SIGKILL check. Script-local
modules remain available; ambient PYTHONPATH, user site and installed site do not.
"""
import os
import sys


def launch(candidate='/candidate/backup.py',arguments=None):
    arguments=sys.argv[1:] if arguments is None else arguments
    os.execv(sys.executable,[sys.executable,'-E','-s','-S','-B',str(candidate),*arguments])


if __name__=='__main__': launch()
