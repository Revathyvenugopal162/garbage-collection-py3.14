import sys
import os
target_pid = 63892
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.remote_exec(target_pid, os.path.join(THIS_DIR, "target.py"))