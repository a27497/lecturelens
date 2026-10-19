#!/usr/bin/env python3
"""Compare every ZIP entry without executing the application or reading environment files."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import zipfile


def inventory(path):
    with zipfile.ZipFile(path) as jar:
        assert jar.testzip() is None
        names = [entry.filename for entry in jar.infolist()]
        assert len(names) == len(set(names)), 'duplicate ZIP entry'
        return {entry.filename: {
            'sha256': hashlib.sha256(jar.read(entry)).hexdigest(),
            'size': entry.file_size, 'compression': entry.compress_type,
            'directory': entry.is_dir(),
        } for entry in jar.infolist()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('live', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    assert not args.output.exists(), 'preserve previous evidence'
    old, new = inventory(args.live), inventory(args.candidate)
    added, deleted = sorted(new.keys() - old.keys()), sorted(old.keys() - new.keys())
    changed = sorted(n for n in old.keys() & new.keys() if old[n] != new[n])
    def subset(prefix):
        a, b = {n: v for n, v in old.items() if n.startswith(prefix)}, {n: v for n, v in new.items() if n.startswith(prefix)}
        return {'old_count': len(a), 'new_count': len(b), 'identical': a == b}
    config_names = [n for n in old.keys() | new.keys() if n.startswith('BOOT-INF/classes/application')]
    summary = {
        'live': str(args.live.resolve()), 'candidate': str(args.candidate.resolve()),
        'live_sha256': hashlib.sha256(args.live.read_bytes()).hexdigest(),
        'candidate_sha256': hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
        'added': [{'path': n, 'new': new[n]} for n in added],
        'deleted': [{'path': n, 'old': old[n]} for n in deleted],
        'changed': [{'path': n, 'old': old[n], 'new': new[n]} for n in changed],
        'unchanged_count': len(old.keys() & new.keys()) - len(changed),
        'dependencies': subset('BOOT-INF/lib/'), 'migrations': subset('BOOT-INF/classes/db/migration/'),
        'configurations': {'paths': sorted(config_names), 'identical': all(old.get(n) == new.get(n) for n in config_names)},
        'manifest_identical': old.get('META-INF/MANIFEST.MF') == new.get('META-INF/MANIFEST.MF'),
        'classpath_identical': old.get('BOOT-INF/classpath.idx') == new.get('BOOT-INF/classpath.idx'),
        'layers_identical': old.get('BOOT-INF/layers.idx') == new.get('BOOT-INF/layers.idx'),
        'zip_integrity': 'passed', 'duplicates': False,
    }
    args.output.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: summary[k] for k in ('live_sha256', 'candidate_sha256', 'dependencies', 'migrations', 'configurations')}))


if __name__ == '__main__':
    main()
