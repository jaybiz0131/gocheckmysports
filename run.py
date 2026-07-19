#!/usr/bin/env python3
"""
run.py: the orchestrator for Stages 1-5. FAIL-CLOSED. NEVER PUBLISHES.

Runs aggregate -> editor -> verifier -> researcher -> writer -> approver -> digest in order
and writes a run report.
If ANY stage errors, it stops, records status=failed, and exits non-zero so CI flags a human.
It deliberately does NOT call publish.py: publishing is a separate, human-approved step (Stage
6), the whole point of the design. The scheduled job runs THIS; a human reviews the digest and
runs publish.py only after approving.

USAGE
  python3 run.py                         # live run (needs ANTHROPIC_API_KEY)
  python3 run.py --mode replay           # offline end-to-end over fixtures (no key, no spend)
  python3 run.py --fixture fixtures/sample_feed.xml --mode replay   # full offline wiring test
"""

import os
import sys
import traceback

import common
import llm as llmlib
import aggregate
import editor
import verifier
import researcher
import writer
import approver
import digest


def run(mode="live", fixture=None):
    os.environ["DESK_LLM_MODE"] = mode
    cfg = common.load_config()
    client = llmlib.Client(cfg, mode=mode)  # one client => one shared budget across stages
    report = {"mode": mode, "stages": [], "status": "running"}

    def record(name, ok, detail=""):
        report["stages"].append({"stage": name, "ok": ok, "detail": detail})

    try:
        rc = aggregate.run(fixture=fixture, out_path=os.path.join(common.OUT_DIR, "items.json"))
        if rc != 0:
            record("1-aggregate", False, f"exit {rc}")
            raise RuntimeError("aggregation failed (zero sources or empty intake)")
        record("1-aggregate", True)

        editor.run(client=client);     record("2-editor", True)
        verifier.run(client=client);   record("3-verifier", True)
        researcher.run(client=client); record("3.5-researcher", True)
        writer.run(client=client);     record("4-writer", True)
        approver.run(client=client);   record("4.5-approver", True)

        date = common.read_out("items.json")["_meta"]["generated"][:10]
        digest.run(date=date);         record("5-digest", True)

        report["status"] = "ready-for-human-review"
        report["budget"] = client.budget.summary()
        report["review_queue"] = f"out/review_queue/{date}.md"
        common.write_out("run_report.json", report)
        print(f"\n[run] OK - mode={mode}, budget={client.budget.summary()}")
        print(f"[run] Review queue ready: out/review_queue/{date}.md")
        print(f"[run] Nothing published. Approve in out/approval_template.json, then run publish.py.")
        return 0
    except Exception as e:
        report["status"] = "failed"
        report["error"] = str(e)
        try:
            common.write_out("run_report.json", report)
        except Exception:
            pass
        common.gh("error", f"run: pipeline FAILED at "
                  f"{report['stages'][-1]['stage'] if report['stages'] else 'start'}: {e} "
                  f"-> FAIL-CLOSED, nothing published.")
        traceback.print_exc()
        return 1


def main():
    argv = sys.argv[1:]
    mode = argv[argv.index("--mode") + 1] if "--mode" in argv else "live"
    fixture = argv[argv.index("--fixture") + 1] if "--fixture" in argv else None
    sys.exit(run(mode=mode, fixture=fixture))


if __name__ == "__main__":
    main()
