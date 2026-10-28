"""Offline source-support arithmetic over independently supplied judgments.

Input: generated claims plus their actual cited Evidence and independent labels.
A resolvable ID is measured separately from semantic support. No model is called.
"""
import argparse
import hashlib
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def measure(candidate, ratings):
    if candidate['data_kind'] not in {'MOCK', 'REAL'}:
        raise ValueError('Explicit data provenance required')
    if ratings['candidate_sha256'] != digest(candidate):
        raise ValueError('Judgments belong to a different candidate')
    sources = {e['evidence_id']: e for e in candidate['evidence']}
    items = candidate['items']
    labels = {row['item_id']: row for row in ratings['judgments']}
    if not items or len(sources) != len(candidate['evidence']):
        raise ValueError('Nonempty items and unique Evidence required')
    if len(labels) != len(ratings['judgments']) or set(labels) != {item['item_id'] for item in items}:
        raise ValueError('Exactly one independent judgment per item required')
    if len({item['item_id'] for item in items}) != len(items):
        raise ValueError('Unique item identities required')
    resolved, supported, unsupported, uncertain = 0, 0, 0, 0
    for item in items:
        refs = item['evidence_ids']
        ok = bool(refs) and all(
            ref in sources and sources[ref]['revision'] == candidate['revision']
            and sources[ref]['course_id'] == candidate['course_id'] for ref in refs
        )
        resolved += ok
        label = labels[item['item_id']]
        if label['verdict'] not in {'supported', 'unsupported', 'uncertain'} or not label['reason'].strip():
            raise ValueError('Independent verdict and reason required')
        if label['verdict'] == 'supported':
            if not ok or not label.get('quotes'):
                raise ValueError('Support needs current references and exact supporting quotations')
            for quote in label['quotes']:
                if quote['evidence_id'] not in refs or not quote['text'].strip() or quote['text'] not in sources[quote['evidence_id']]['text']:
                    raise ValueError('Supporting quotation does not match attached Evidence')
            supported += 1
        elif label['verdict'] == 'unsupported':
            unsupported += 1
        else:
            uncertain += 1
    return {
        'data_kind': candidate['data_kind'], 'candidate_sha256': digest(candidate),
        'judgments_sha256': digest(ratings), 'items': len(items), 'resolved_items': resolved,
        'citation_resolution_rate': resolved/len(items), 'supported': supported,
        'unsupported': unsupported, 'uncertain': uncertain, 'source_support_rate': supported/len(items),
        'quality_status': 'MOCK_NOT_QUALITY' if candidate['data_kind'] == 'MOCK' else 'INDEPENDENT_JUDGMENTS_ONLY',
        'warning': 'Exact quotes and independent labels are auditable inputs, not proof that a reviewer is correct.',
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--candidate', required=True)
    p.add_argument('--ratings', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    result = measure(json.loads(Path(a.candidate).read_text()), json.loads(Path(a.ratings).read_text()))
    # Exclusive output preserves failed trials; never overwrite or relabel a consumed trial.
    with Path(a.output).open('x') as out:
        out.write(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
