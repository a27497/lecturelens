#!/usr/bin/env python3
"""Offline frozen SQL parsing with filtered output; never connect a database."""
import json
from pathlib import Path
import subprocess

PUBLIC = Path(__file__).resolve().parent
ROOT = PUBLIC.parents[1]
PRIVATE = ROOT / '.data' / PUBLIC.name
cp = ':'.join(str(PRIVATE/p) for p in ['extra', 'runtime/BOOT-INF/classes', 'runtime/BOOT-INF/lib/*'])
r = subprocess.run(['/usr/bin/java', '-cp', cp, 'com.example.courselingo.systemmodel.FrozenMigrationCheck',
                    str(PRIVATE/'runtime/BOOT-INF/classes/db/migration')],
                   capture_output=True, text=True, timeout=30)
assert r.returncode == 0, 'OFFLINE_PARSER_PROCESS_FAILED'
values = [json.loads(line.removeprefix('P21_OFFLINE_MIGRATIONS ')) for line in r.stdout.splitlines()
          if line.startswith('P21_OFFLINE_MIGRATIONS ')]
assert len(values) == 1 and len(values[0]) == 32
result = dict(database_connected=False, runtime_configuration_read=False, spring_application_started=False,
              parsing_only=True, resources=values[0])
with (PUBLIC/'offline-migrations.json').open('x') as f:
    json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({'offline_migrations':len(values[0]), 'parser_passed':sum(v['parser_passed'] for v in values[0]),
                  'database_connected':False}))
