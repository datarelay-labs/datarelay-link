#!/usr/bin/env python3
"""Persistent-host application traffic measurement; not a CLI user/actor."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

PROFILES={"warmup":60,"steady":300,"soak":3600,
          "extended":28800,"endurance":86400}
TRAFFIC_TOOLS={"curl","wget","iperf3","nc","ncat"}

def duration(name):
    if name not in PROFILES:
        raise ValueError("Unknown performance profile")
    return PROFILES[name]

def validate_command(argv):
    if not argv or Path(argv[0]).name not in TRAFFIC_TOOLS:
        raise ValueError("Only real, approved application traffic generators supported")
    if any(any(s in arg.lower() for s in ("password=","token=","bearer ","api_key="))
           for arg in argv):
        raise ValueError("Do not put secrets into recorded command arguments")

def timestamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-root",type=Path,required=True)
    p.add_argument("--scenario",required=True)
    p.add_argument("--profile",choices=sorted(PROFILES),required=True)
    p.add_argument("--sample-seconds",type=int,default=15)
    p.add_argument("command",nargs=argparse.REMAINDER)
    a=p.parse_args()
    cmd=a.command[1:] if a.command and a.command[0]=="--" else a.command
    validate_command(cmd)
    if not a.scenario.startswith("P-"):
        p.error("Only parent P-series real performance cases permitted")
    if (a.profile in ("extended","endurance")) != (a.scenario=="P-019"):
        p.error("8h/24h are planned P-019 profiles; otherwise use 60/300/3600")
    if a.sample_seconds<5 or a.sample_seconds>60:
        p.error("sample seconds outside 5..60")
    root=a.run_root
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode & 0o077:
        p.error("Existing private RUN_ID root (0700) required")
    out=root.resolve()/"performance"/(a.scenario+"-"+a.profile)
    out.mkdir(parents=True,mode=0o700,exist_ok=False)
    out.chmod(0o700)
    start=out/"start.json"
    samples=out/"samples.jsonl"
    stop=out/"exit.json"
    with start.open("x") as f:
        os.chmod(start,0o600)
        json.dump({"utc":timestamp(),"pid":os.getpid(),"argv":cmd,
                   "profile":a.profile,"minimum_seconds":duration(a.profile),
                   "evidence_only":True},f)
        f.write("\n")
    begin=time.monotonic()
    attempts=0
    failures=0
    exitcode=3
    try:
        with samples.open("x") as log:
            os.chmod(samples,0o600)
            while time.monotonic()-begin<duration(a.profile):
                before=time.monotonic()
                try:
                    cp=subprocess.run(cmd,capture_output=True,
                                      timeout=a.sample_seconds,check=False)
                    rc=cp.returncode;output=cp.stdout
                except subprocess.TimeoutExpired as err:
                    rc=124;output=err.stdout or b""
                attempts+=1
                failures+=(rc!=0)
                ru=resource.getrusage(resource.RUSAGE_CHILDREN)
                log.write(json.dumps({
                    "utc":timestamp(),"elapsed_monotonic":time.monotonic()-begin,
                    "command_elapsed":time.monotonic()-before,
                    "attempt":attempts,"exit_code":rc,
                    "stdout_bytes":len(output),
                    "stdout_sha256":hashlib.sha256(output).hexdigest(),
                    "children_cpu_user":ru.ru_utime,"children_cpu_system":ru.ru_stime,
                    "children_maxrss_kib":ru.ru_maxrss,
                })+"\n")
                log.flush();os.fsync(log.fileno())
                time.sleep(min(1,max(0,duration(a.profile)-(time.monotonic()-begin))))
        elapsed=time.monotonic()-begin
        exitcode=0 if elapsed>=duration(a.profile) and attempts>0 and not failures else 2
    finally:
        with stop.open("x") as f:
            os.chmod(stop,0o600)
            json.dump({"utc":timestamp(),"duration_seconds":time.monotonic()-begin,
                       "attempts":attempts,"nonzero_exits":failures,
                       "exit_code":exitcode,"receiver_data_integrity_proven":False,
                       "product_cli_e2e_pass":False},f,indent=2)
            f.write("\n")
    print(json.dumps({"status":"MEASUREMENT_ONLY","exit_code":exitcode,
                      "evidence":str(out)}))
    return exitcode

if __name__=="__main__":
    raise SystemExit(main())
