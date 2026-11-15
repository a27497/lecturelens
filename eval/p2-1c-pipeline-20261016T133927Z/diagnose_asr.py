"""One bounded diagnostic inference; no worker, DB writes, retries or configuration changes."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timezone
import httpx

ROOT = Path('/home/dev/projects/lecturelens')
PUBLIC = Path(__file__).resolve().parent
PRIVATE = ROOT / '.data' / PUBLIC.name
sys.path.insert(0, str(ROOT / 'eval/p2-1b-pipeline-20261016T122904Z'))
from runtime_support import deployment, disk


def main():
    before = disk()
    assert before['percent'] <= 85 and before['available_bytes'] >= 2 * 1024 ** 3
    assert not (PUBLIC / 'asr-diagnostic.json').exists(), 'Do not silently repeat a diagnostic'
    env = deployment()
    audio = (ROOT / 'backend/src/main/resources/system-model-probe/tone.wav').read_bytes()
    body = json.dumps(dict(model=env['BAILIAN_ASR_MODEL'], input=dict(messages=[dict(
        role='user', content=[dict(type='input_audio', input_audio=dict(
            data='data:audio/wav;base64,' + base64.b64encode(audio).decode()))])]),
        parameters=dict(format='wav')), separators=(',', ':')).encode()
    intent = dict(utc=datetime.now(timezone.utc).isoformat(), kind='DIAGNOSTIC_NOT_ACCEPTANCE',
                  physical_call_limit=1, retries=0, model=env['BAILIAN_ASR_MODEL'],
                  endpoint_sha256=hashlib.sha256(env['BAILIAN_ASR_ENDPOINT'].encode()).hexdigest(),
                  audio_sha256=hashlib.sha256(audio).hexdigest(), request_sha256=hashlib.sha256(body).hexdigest(),
                  disk_before=before, credentials_exported=False, configuration_writes=0)
    PUBLIC.joinpath('asr-diagnostic-intent.json').write_text(json.dumps(intent, indent=2) + '\n')
    started = time.monotonic()
    with httpx.Client(trust_env=False, timeout=20, follow_redirects=False) as client:
        with client.stream('POST', env['BAILIAN_ASR_ENDPOINT'], content=body,
                           headers={'Authorization': 'Bearer ' + env['BAILIAN_ASR_API_KEY'],
                                    'Content-Type': 'application/json'}) as response:
            chunks = bytearray()
            for chunk in response.iter_bytes():
                if len(chunks) + len(chunk) > 65536:
                    raise RuntimeError('RESPONSE_LIMIT_EXCEEDED')
                chunks.extend(chunk)
            raw = bytes(chunks)
            status = response.status_code
    PRIVATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with os.fdopen(os.open(PRIVATE / 'diagnostic-response.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as f:
        f.write(raw)
    decoded = json.loads(raw)
    error = decoded.get('error') if isinstance(decoded.get('error'), dict) else decoded
    code = error.get('code') or error.get('type')
    if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', code):
        code = None
    result = dict(**intent, http_status=status, provider_error_code=code,
                  elapsed_seconds=time.monotonic()-started, response_bytes=len(raw),
                  response_chars=len(raw.decode()), response_sha256=hashlib.sha256(raw).hexdigest(),
                  usage=decoded.get('usage'), response_private=True, disk_after=disk())
    PUBLIC.joinpath('asr-diagnostic.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('http_status','provider_error_code','response_chars','elapsed_seconds')}))


if __name__ == '__main__':
    main()
