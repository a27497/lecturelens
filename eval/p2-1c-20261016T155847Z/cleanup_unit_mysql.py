#!/usr/bin/env python3
"""Stop/remove only the exact approved test container recorded by this run."""
import datetime as dt
import json
from pathlib import Path
import subprocess

PUBLIC=Path(__file__).resolve().parent


def main():
    output=PUBLIC/"test-database-cleanup.json"
    if output.exists():
        raise SystemExit("existing cleanup evidence must not be overwritten")
    record=json.loads((PUBLIC/"test-database.json").read_text())
    assert record["name"]=="lecturelens-p21c-unit-mysql-20261017" and record["authorized"]
    identity=subprocess.check_output(["docker","inspect","--format",
        '{{.Id}} {{.Image}} {{index .Config.Labels "lecturelens.eval"}}',record["name"]],text=True).strip().split()
    assert identity[0]==record["identity"][0] and identity[1]==record["identity"][1] and identity[2]=="p2-1c-unit"
    subprocess.run(["docker","stop","--time","10",identity[0]],check=True)
    subprocess.run(["docker","rm",identity[0]],check=True)
    absent=subprocess.run(["docker","container","inspect","--format","{{.Id}}",identity[0]],capture_output=True)
    assert absent.returncode!=0
    output.write_text(json.dumps({"at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"name":record["name"],
        "id":identity[0],"image":identity[1],"stopped":True,"removed":True,"other_containers_changed":False},indent=2)+"\n")


if __name__=="__main__":
    main()
