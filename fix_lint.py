"""Fix remaining ruff errors"""
import re
import subprocess

r=subprocess.run('python -m ruff check src/',shell=True,capture_output=True,text=True,cwd=r'C:\Users\john\AppData\Roaming\reasonix\global-workspace\job-hunter')
if not r.stdout and not r.stderr:
    print("✅ Clean!")
else:
    print(r.stdout[-1000:] if r.stdout else r.stderr[-1000:])
