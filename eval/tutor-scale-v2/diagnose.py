"""Export all failed, malformed, timed-out and absent scheduled turns separately."""

import argparse
import json

from records import failure_items, read_run
from shared import write

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--queue", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    report = failure_items(read_run(a.queue, a.run))
    write(a.output, report)
    print(
        json.dumps(
            dict(counts=report["counts"], diagnostic_items=len(report["items"]), quality_status="NOT_RUN")
        )
    )
