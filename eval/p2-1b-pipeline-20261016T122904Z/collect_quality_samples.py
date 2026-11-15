"""Private deterministic first/middle/last source-translation pairs, no provider calls."""
import sys
from runtime_support import *


def main():
    c=db(deployment(),SCHEMA)
    journal=[json.loads(line) for line in (PUBLIC/'trials.jsonl').read_text().splitlines()]
    tasks=[r for r in journal if r['phase']=='terminal' and r['kind']=='NORMAL']
    selected=set(sys.argv[1:])
    for row in tasks:
        task=row['task_id']
        if selected and task not in selected:continue
        bounds=query(c,'SELECT MIN(segment_index) first_idx,MAX(segment_index) last_idx FROM subtitle_segment WHERE task_id=%s AND user_id=9',(task,))[0]
        if bounds['first_idx'] is None:continue
        indices=[bounds['first_idx'],(bounds['first_idx']+bounds['last_idx'])//2,bounds['last_idx']]
        samples=query(c,"SELECT s.segment_index,s.text source,t.translated_text translation FROM subtitle_segment s JOIN subtitle_translation_segment t ON s.task_id=t.task_id AND s.user_id=t.user_id AND s.segment_index=t.segment_index WHERE s.task_id=%s AND s.user_id=9 AND t.target_language='zh-CN' AND s.segment_index IN (%s,%s,%s) ORDER BY s.segment_index",(task,*indices))
        path=PRIVATE/'quality-samples'/f'{task}.json'
        if not path.exists():save(path,samples)
        print(json.dumps(dict(task_id=task,trial_id=row['trial_id'],samples=samples),ensure_ascii=False))


if __name__=='__main__':main()
