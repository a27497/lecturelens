// Offline HTTP fixtures for the built Vue app. No upstream, DB, credentials or provider client.
import { createServer } from 'node:http';
import { createReadStream } from 'node:fs';
import { readFile, stat } from 'node:fs/promises';
import { resolve, extname } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';

export async function createB1Fixture({ dist, media, port = 0 }) {
  dist = resolve(dist); media = resolve(media);
  const requests = [], errors = [];
  const citation = { evidence_id: 'course:synthetic:subtitle:2:r1', text: 'Group A scores 84. Group B scores 61. The difference is 23. This fictional result does not prove that every student improves by 23.', start_ms: 12000, end_ms: 30000, source_type: 'SUBTITLE' };
  const user = { userId: 1, email: 'synthetic@example.invalid', status: 'ACTIVE', role: 'USER' };
  const stamp = '2026-10-24T00:00:00Z';
  const task = id => ({ taskId: id, status: ({preparing:'RUNNING',failed:'FAILED',cancelled:'CANCELED'})[id] ?? 'SUCCEEDED', progressPercent: id === 'preparing' ? 40 : 100, currentStage: id === 'preparing' ? 'TRANSCRIBE' : 'DONE', targetLanguage: 'zh-CN', createdAt: stamp, updatedAt: stamp, startedAt: stamp, finishedAt: stamp, errorCode: null, errorMessage: null });
  const artifact = id => ({ artifact_id: `artifact-${id}`, title: '平均分、差值与结论边界', explanation: '这是合成课程。84 − 61 = 23；这不证明每个人都会提高23分。', evidence_ids: [citation.evidence_id], revision: 1, mode: 'mock', citations: [citation], questions: [{ question: '两组的平均分与差值是什么？为什么不能推广到所有学生？', evidence_ids: [citation.evidence_id] }, { question: '本课的示例复习安排是哪三天？示例是否等于普遍结论？', evidence_ids: [citation.evidence_id] }] });
  const run = (id, goal = '核对平均分与差值，解释结论边界。') => ({ run_id: id, session_id: 'session', goal, status: 'succeeded', model_mode: 'mock', model_calls: 0, tool_calls: 0, error_code: null, created_at: stamp, learning_scope: { version: 1, kind: 'course', policy: 'strict', revision: 1, evidence_ids: [] } });
  let state;
  function reset() {
    state = { revision: 1, denied: false, indexFailed: false, scopeFailed: false, slow: false, failSave: false, runs: [run('saved-run'), run('older-run', '另一条已保存的示例练习')], latest: 'saved-run', artifacts: {}, attempts: {}, feedbacks: [] };
    for (const row of state.runs) { state.artifacts[row.run_id] = artifact(row.run_id); state.attempts[row.run_id] = []; }
    requests.length = 0; errors.length = 0;
  }
  reset();
  const result = id => ({ taskId: id, sourceFullText: `Retrieval practice means recalling before reading the source. ${citation.text} Review on day one, day three and day seven.`, sourceParagraphs: [], translatedFullText: '检索练习是先回忆再查阅。虚构实验平均分84与61，差值23，不能推广。示例在第1、3、7天复习。', subtitles: [
    { segmentIndex: 1, startMillis: 0, endMillis: 12000, language: 'en', sourceText: 'Retrieval practice means recalling before reading the source.' },
    { segmentIndex: 2, startMillis: 12000, endMillis: 30000, language: 'en', sourceText: state.revision === 1 ? citation.text : 'REVISED synthetic source, no longer the cited passage.' },
    { segmentIndex: 3, startMillis: 30000, endMillis: 49600, language: 'en', sourceText: 'Review on day one, day three and day seven. This is an example, not a universal schedule.' },
  ], translations: [], learningPackage: null, keyframes: [], videoSegments: [], artifacts: [], aiCallRecords: [] });
  const readRun = id => {
    const row = state.runs.find(r => r.run_id === id) ?? state.runs[0];
    return { run: row, artifact: row.status === 'succeeded' ? state.artifacts[row.run_id] : null, attempts: [...new Map((state.attempts[row.run_id] ?? []).map(a => [a.question_index, a])).values()], feedback_enabled: true, feedback_runs: state.feedbacks.filter(f => f.parent === row.run_id) };
  };
  const json = (res, data, status = 200) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ code: status === 200 ? '0' : String(status), message: status === 200 ? 'ok' : '隔离夹具异常状态', data })); };
  const bodyOf = async req => { const chunks = []; for await (const c of req) chunks.push(c); return JSON.parse(Buffer.concat(chunks).toString() || '{}'); };
  const server = createServer(async (req, res) => {
    try {
      const path = new URL(req.url, 'http://127.0.0.1').pathname;
      if (path === '/__fixture' && req.method === 'POST') { Object.assign(state, await bodyOf(req)); return json(res, { ok: true }); }
      if (path === '/__fixture/reset') { reset(); return json(res, { ok: true }); }
      if (path === '/__fixture/state') return json(res, { ...state, requests, errors, physicalProviderCalls: 0 });
      if (path === '/__preview') { res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }); res.end('<title>B1 Vue 隔离预览</title><h1>B1 真实 Vue · 隔离 Mock 预览</h1><p>合成课程；所有 API 是本机夹具，无数据库、真实模型或生产连接。记录仅在此进程内，重启丢失；草稿不跨刷新。</p><button onclick="localStorage.setItem(\'courselingo.accessToken\',\'offline-fixture-token\');location.href=\'/tasks\'">进入合成课程</button><p><a href="/__fixture/reset">重置本机夹具记录</a></p>'); return; }
      if (path.startsWith('/api/')) {
        const command = req.method === 'POST' ? await bodyOf(req) : {};
        requests.push({ path, method: req.method, operation: command.operation ?? null, command });
        const id = path.split('/')[3];
        if (path === '/api/me') return json(res, user);
        if (path === '/api/auth/login') return json(res, { user, accessToken: 'offline-fixture-token', refreshToken: 'offline-fixture-refresh', tokenType: 'Bearer', expiresIn: 3600 });
        if (path === '/api/public/runtime-configuration') return json(res, { demoMode: true });
        if (path.startsWith('/api/tasks/') && state.denied) return json(res, null, 404);
        if (path === '/api/tasks') return json(res, { items: [task('synthetic'), task('preparing')], page: 1, pageSize: 100, total: 2 });
        if (path.endsWith('/results')) return json(res, result(id));
        if (path.endsWith('/playback-token')) return json(res, { playbackUrl: '/synthetic.mp4', expiresAt: '2099-01-01T00:00:00Z' });
        if (path.endsWith('/embedded-subtitles')) return json(res, { status: 'NOT_FOUND', selectedStreamIndex: null, tracks: [] });
        if (path.endsWith('/evidence/index-status')) return json(res, { status: state.indexFailed ? 'FAILED' : 'READY', revision: state.revision });
        if (path.endsWith('/evidence')) {
          if (state.scopeFailed) return json(res, null, 503);
          return json(res, { learningScopeVersion: 1, revision: state.revision, stale: false, nextCursor: null, items: result(id).subtitles.map(r => ({ evidenceId: r.segmentIndex === 2 ? citation.evidence_id : `course:synthetic:subtitle:${r.segmentIndex}:r1`, revision: state.revision, sourceType: 'SUBTITLE', startMs: r.startMillis, endMs: r.endMillis, normalizedText: r.sourceText, retrievable: true })) });
        }
        if (path.endsWith('/study/status')) return json(res, { enabled: true, revision: state.revision });
        if (path.endsWith('/events')) {
          res.writeHead(200, { 'Content-Type': 'text/event-stream' });
          if (path.includes('/study/')) res.end(`data: ${JSON.stringify({ sequence: 1, event_type: 'run_completed', payload: {} })}\n\n`);
          else res.end(`event: snapshot\ndata: ${JSON.stringify(task(id))}\n\n`);
          return;
        }
        if (path.endsWith('/qa') || path.endsWith('/qa/scoped')) return json(res, { answer: '合成回答：A组84，B组61，相差23分；不能从虚构小样本推断所有学生。', evidence: [{ sourceType: 'SUBTITLE', sourceId: '2', evidenceId: citation.evidence_id, revision: 1, startTimeMillis: 12000, endTimeMillis: 30000, timeText: '00:12–00:30', snippet: citation.text, confidence: 1 }], usage: null });
        if (/\/study\/(scoped-command|command)$/.test(path)) {
          const rid = command.run_id ?? state.latest;
          switch (command.operation) {
            case 'LIST': return json(res, { sessions: [{ session_id: 'session', revision: 1, created_at: stamp }] });
            case 'CREATE_SESSION': return json(res, { session_id: 'session', revision: state.revision });
            case 'RUNS': return json(res, { runs: state.runs });
            case 'START': { const row = { ...run(`run-${state.runs.length}`, command.goal), learning_scope: command.learning_scope, request_key: command.request_key, status: state.slow ? 'running' : 'succeeded' }; state.runs.unshift(row); state.latest = row.run_id; state.artifacts[row.run_id] = artifact(row.run_id); state.attempts[row.run_id] = []; return json(res, readRun(row.run_id)); }
            case 'READ': { const f = state.feedbacks.find(f => f.run_id === rid); return json(res, f ? { run: { ...run(rid), status: f.status }, feedback: f.feedback } : readRun(rid)); }
            case 'EVENTS': return json(res, { events: [] });
            case 'CANCEL': { const row = state.runs.find(r => r.run_id === rid) ?? state.feedbacks.find(f => f.run_id === rid); if (row) row.status = 'cancelled'; return json(res, { run: { ...run(rid), status: 'cancelled' } }); }
            case 'SAVE_ATTEMPT': {
              if (state.failSave) return json(res, null, 503);
              const rows = state.attempts[rid];
              const latest = rows.filter(a => a.question_index === command.question_index).at(-1);
              if ((latest?.version ?? 0) !== command.expected_version) return json(res, null, 409);
              const answer = { attempt_id: `a-${rid}-${rows.length}`, artifact_id: command.artifact_id, question_index: command.question_index, version: command.expected_version + 1, answer_text: command.answer_text, created_at: stamp };
              rows.push(answer); return json(res, { attempt: answer });
            }
            case 'ATTEMPT_HISTORY': return json(res, { attempts: state.attempts[rid].filter(a => a.question_index === command.question_index).toReversed(), next_before_version: null });
            case 'START_FEEDBACK': {
              const a = state.attempts[rid].find(a => a.attempt_id === command.attempt_id);
              if (!a) return json(res, null, 409);
              const feedback = { feedback_id: `feedback-${state.feedbacks.length}`, attempt_id: a.attempt_id, answer_version: a.version, question_index: a.question_index, answer_text: a.answer_text, note: null, content: { kind: 'guidance', mode: 'mock', citations: [citation], observations: [{ learner_quote: a.answer_text, observation: '请核对61与23，并区分虚构示例和普遍结论。', next_step: '回看00:12的原文，再修订自己的解释。', evidence_id: citation.evidence_id, evidence_quote: citation.text }] } };
              const f = { parent: rid, run_id: `feedback-run-${state.feedbacks.length}`, status: state.slow ? 'running' : 'succeeded', error_code: null, attempt_id: a.attempt_id, answer_version: a.version, question_index: a.question_index, feedback: state.slow ? null : feedback };
              state.feedbacks.unshift(f); return json(res, { run: { ...run(f.run_id), status: f.status }, feedback: f.feedback });
            }
            case 'SAVE_FEEDBACK_NOTE': { const f = state.feedbacks.find(f => f.run_id === rid); f.feedback.note = { note_id: 'note', version: command.expected_version + 1, disposition: command.disposition, note_text: command.note_text, created_at: stamp }; return json(res, { note: f.feedback.note }); }
            case 'FEEDBACK_NOTES': return json(res, { notes: [state.feedbacks.find(f => f.run_id === rid).feedback.note] });
            case 'ANSWERS': return json(res, { questions: state.artifacts[rid].questions.map(q => ({ ...q, answer: '84，61，23；不推断所有人。', rubric: '核对课程事实，区分结论边界。' })) });
            default: throw Error(`Unimplemented fixture operation: ${command.operation}`);
          }
        }
        if (path.endsWith('/model-usage')) return json(res, { taskId: id, current: null, pipeline: [], qa: [], calls: [] });
        if (/^\/api\/tasks\/[^/]+$/.test(path)) return json(res, task(id));
        throw Error(`Unimplemented fixture route: ${path}`);
      }
      if (path === '/synthetic.mp4') {
        const size = (await stat(media)).size, range = /bytes=(\d+)-(\d*)/.exec(req.headers.range ?? '');
        const start = range ? +range[1] : 0, end = range?.[2] ? Math.min(+range[2], size - 1) : size - 1;
        res.writeHead(range ? 206 : 200, { 'Content-Type': 'video/mp4', 'Accept-Ranges': 'bytes', 'Content-Length': end - start + 1, ...(range ? { 'Content-Range': `bytes ${start}-${end}/${size}` } : {}) }); createReadStream(media, { start, end }).pipe(res); return;
      }
      const pathname = decodeURIComponent(path), candidate = resolve(dist, '.' + pathname);
      if (!candidate.startsWith(dist + '/') && candidate !== dist) { res.writeHead(403); res.end(); return; }
      const file = extname(pathname) ? candidate : resolve(dist, 'index.html');
      const content = await readFile(file);
      res.writeHead(200, { 'Content-Type': ({ '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml', '.webp': 'image/webp' })[extname(file)] ?? 'application/octet-stream' }); res.end(content);
    } catch (e) { errors.push(String(e)); if (!res.headersSent) json(res, null, 500); else res.end(); }
  });
  await new Promise((yes, no) => { server.once('error', no); server.listen(port, '127.0.0.1', yes); });
  return { origin: `http://127.0.0.1:${server.address().port}`, requests, errors, reset, close: () => new Promise(r => { server.close(r); server.closeAllConnections(); }) };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const { values } = parseArgs({ options: { dist: { type: 'string', default: 'dist' }, media: { type: 'string' }, port: { type: 'string', default: '4391' } } });
  if (!values.media) throw Error('Require --media /path/to/approved-synthetic.mp4');
  const fixture = await createB1Fixture({ ...values, port: Number(values.port) });
  console.log(`Offline Vue preview: ${fixture.origin}/__preview (memory-only fixtures; no upstream)`);
  for (const signal of ['SIGTERM', 'SIGINT']) process.once(signal, async () => { await fixture.close(); process.exit(0); });
}
