// Workflow API Worker — Supabase backend
// Briefs → mktg_briefs table, Signal analyses → signal_analyses table

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, X-API-Key',
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS_HEADERS },
  });
}

// Supabase REST helper
async function supa(env, path, method = 'GET', body = null) {
  const url = `${env.SUPABASE_URL}/rest/v1/${path}`;
  const headers = {
    'apikey': env.SUPABASE_KEY,
    'Authorization': `Bearer ${env.SUPABASE_KEY}`,
    'Content-Type': 'application/json',
    'Prefer': method === 'POST' ? 'return=representation' : 'return=representation',
  };
  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);
  const resp = await fetch(url, opts);
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Supabase ${method} ${path}: ${resp.status} ${text}`);
  }
  const text = await resp.text();
  return text ? JSON.parse(text) : null;
}

// Map brief object keys to snake_case for Supabase
function toDb(item) {
  return {
    id: item.id,
    title: item.title,
    status: item.status || 'signal',
    signal: item.signal,
    signal_type: item.signalType,
    source: item.source,
    source_detail: item.sourceDetail,
    hypothesis: item.hypothesis,
    criteria: item.criteria,
    target_vp: item.targetVp,
    target_problem: item.targetProblem,
    content_type: item.contentType,
    hook_type: item.hookType,
    channel: item.channel,
    deadline: item.deadline || null,
    assignee: item.assignee,
    learning_result: item.learningResult,
    verdict: item.verdict,
    history: item.history || [],
  };
}

// Map DB row back to camelCase for frontend
function fromDb(row) {
  return {
    id: row.id,
    title: row.title,
    status: row.status,
    signal: row.signal,
    signalType: row.signal_type,
    source: row.source,
    sourceDetail: row.source_detail,
    hypothesis: row.hypothesis,
    criteria: row.criteria,
    targetVp: row.target_vp,
    targetProblem: row.target_problem,
    contentType: row.content_type,
    hookType: row.hook_type,
    channel: row.channel,
    deadline: row.deadline,
    assignee: row.assignee,
    learningResult: row.learning_result,
    verdict: row.verdict,
    history: row.history || [],
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS_HEADERS });
    }

    const url = new URL(request.url);
    const path = url.pathname;

    // Auth check for writes
    if (['POST', 'PUT', 'DELETE'].includes(request.method)) {
      const key = request.headers.get('X-API-Key');
      if (key !== env.API_KEY) {
        return json({ error: 'Unauthorized' }, 401);
      }
    }

    try {

    // ─── Briefs CRUD ───

    // GET /api/items — list all briefs
    if (path === '/api/items' && request.method === 'GET') {
      const rows = await supa(env, 'mktg_briefs?order=created_at.desc');
      return json(rows.map(fromDb));
    }

    // POST /api/items — create brief
    if (path === '/api/items' && request.method === 'POST') {
      const item = await request.json();
      item.id = item.id || 'wf-' + Date.now();
      const dbItem = toDb(item);
      const rows = await supa(env, 'mktg_briefs', 'POST', dbItem);
      return json(fromDb(rows[0]), 201);
    }

    // PUT /api/items/:id — update brief
    if (path.startsWith('/api/items/') && request.method === 'PUT') {
      const id = path.split('/').pop();
      const updates = await request.json();
      
      // Get existing to track history
      const existing = await supa(env, `mktg_briefs?id=eq.${id}`);
      if (!existing || existing.length === 0) return json({ error: 'Not found' }, 404);
      
      const old = fromDb(existing[0]);
      let history = old.history || [];
      
      // Track status changes
      if (updates.status && updates.status !== old.status) {
        history.push({ from: old.status, to: updates.status, at: new Date().toISOString() });
      }
      
      const merged = { ...old, ...updates, history };
      const dbItem = toDb(merged);
      delete dbItem.id; // Don't update PK
      
      const rows = await supa(env, `mktg_briefs?id=eq.${id}`, 'PATCH', dbItem);
      return json(fromDb(rows[0]));
    }

    // DELETE /api/items/:id
    if (path.startsWith('/api/items/') && request.method === 'DELETE') {
      const id = path.split('/').pop();
      await supa(env, `mktg_briefs?id=eq.${id}`, 'DELETE');
      return json({ ok: true });
    }

    // GET /api/export — full export
    if (path === '/api/export') {
      const rows = await supa(env, 'mktg_briefs?order=created_at.desc');
      const items = rows.map(fromDb);
      return json({ exportedAt: new Date().toISOString(), count: items.length, items });
    }

    // POST /api/import — bulk import
    if (path === '/api/import' && request.method === 'POST') {
      const { items } = await request.json();
      if (!Array.isArray(items)) return json({ error: 'items array required' }, 400);
      
      // Upsert each item
      for (const item of items) {
        const dbItem = toDb(item);
        // Try insert, on conflict update
        await supa(env, 'mktg_briefs?on_conflict=id', 'POST', dbItem);
      }
      return json({ ok: true, count: items.length });
    }

    // ─── Signal Analysis ───

    // POST /api/analyze-signal — create analysis request
    if (path === '/api/analyze-signal' && request.method === 'POST') {
      const { text } = await request.json();
      if (!text) return json({ error: 'text required' }, 400);

      const id = 'sig-' + Date.now();
      const rows = await supa(env, 'signal_analyses', 'POST', {
        id, input_text: text, status: 'pending'
      });
      return json({ id, status: 'pending' });
    }

    // GET /api/analyze-signal/:id — poll result
    if (path.startsWith('/api/analyze-signal/') && request.method === 'GET') {
      const id = path.split('/').pop();
      const rows = await supa(env, `signal_analyses?id=eq.${id}`);
      if (!rows || rows.length === 0) return json({ error: 'Not found' }, 404);
      const row = rows[0];
      return json({
        id: row.id,
        text: row.input_text,
        status: row.status,
        ...(row.result || {}),
        createdAt: row.created_at,
        completedAt: row.completed_at,
      });
    }

    // PUT /api/analyze-signal/:id — agent saves result
    if (path.startsWith('/api/analyze-signal/') && request.method === 'PUT') {
      const id = path.split('/').pop();
      const result = await request.json();
      await supa(env, `signal_analyses?id=eq.${id}`, 'PATCH', {
        status: 'done',
        result,
        completed_at: new Date().toISOString(),
      });
      return json({ ok: true });
    }

    // GET /api/analyze-pending — pending list for agent
    if (path === '/api/analyze-pending' && request.method === 'GET') {
      const rows = await supa(env, 'signal_analyses?status=eq.pending&order=created_at.asc');
      return json(rows.map(r => ({ id: r.id, text: r.input_text, status: r.status, createdAt: r.created_at })));
    }

    return json({ error: 'Not found' }, 404);

    } catch (e) {
      return json({ error: e.message }, 500);
    }
  }
};
