"""Command line: python -m app.cli run "Which teams at Groww are growing fastest?" [--company Groww] [--offline]
                python -m app.cli resume RUN_ID
                python -m app.cli show RUN_ID"""
import argparse
import json
import sys
import time

from .config import settings
from .pipeline import execute, new_run
from .store import Store


def _print_events(store, run_id, last):
    for ev in store.events_after(run_id, last):
        d = ev["data"]
        print("[%s] %s" % (ev["kind"], d.get("message") or d.get("step") or d))
        last = ev["id"]
    return last


def main(argv=None):
    ap = argparse.ArgumentParser(prog="xray")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("request")
    r.add_argument("--company")
    r.add_argument("--offline", action="store_true")
    r.add_argument("--crash-after", default="")
    rs = sub.add_parser("resume")
    rs.add_argument("run_id")
    sh = sub.add_parser("show")
    sh.add_argument("run_id")
    args = ap.parse_args(argv)

    sys.stdout.reconfigure(encoding="utf-8")
    store = Store(settings()["db"])
    if args.cmd == "show":
        run = store.get_run(args.run_id)
        print(json.dumps(run["result"] or {"status": run["status"], "error": run["error"]}, indent=1)[:6000])
        return 0
    if args.cmd == "run":
        if args.crash_after:
            import os
            os.environ["XRAY_CRASH_AFTER"] = args.crash_after
        run_id = new_run(store, args.request, company=args.company, offline=True if args.offline else None)
        print("run id:", run_id)
    else:
        run_id = args.run_id
    status = execute(store, run_id)
    _print_events(store, run_id, 0)
    run = store.get_run(run_id)
    print("status:", status, "| credits this run:", run["credits"])
    if status == "done":
        b = run["result"]["brief"]
        print("\nHEADLINE:", b["headline"])
        for f in b["findings"]:
            print(" -", f["text"], f["fact_ids"])
        if b.get("inference"):
            print("INFERENCE (%s):" % b["inference"]["confidence"], b["inference"]["text"])
    return 0 if status == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
