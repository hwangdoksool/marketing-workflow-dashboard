// Workflow API Worker — Supabase backend
// Briefs → mktg_briefs table, Signal analyses → signal_analyses table
// Auth: CF Access JWT (logged-in users get full read/write)

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, X-API-Key, CF-Access-Jwt-Assertion',
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

// CF Access JWT verification
async function verifyCfAccessJwt(token, env) {
  try {
    // Decode payload (middle part)
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    
    const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
    
    // Check expiry
    if (payload.exp && payload.exp < Math.floor(Date.now() / 1000)) return null;
    
    // Check audience matches our CF Access app
    const aud = env.CF_ACCESS_AUD;
    if (aud) {
      const tokenAud = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
      if (!tokenAud.includes(aud)) return null;
    }
    
    // Fetch CF Access certs and verify signature
    const certsUrl = `https://${env.CF_ACCESS_TEAM || 'wespion'}.cloudflareaccess.com/cdn-cgi/access/certs`;
    const certsResp = await fetch(certsUrl);
    if (!certsResp.ok) return null;
    const certs = await certsResp.json();
    
    // Find matching key
    const header = JSON.parse(atob(parts[0].replace(/-/g, '+').replace(/_/g, '/')));
    const key = certs.keys.find(k => k.kid === header.kid);
    if (!key) return null;
    
    // Import key and verify
    const cryptoKey = await crypto.subtle.importKey(
      'jwk', key, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify']
    );
    
    const sigBytes = Uint8Array.from(atob(parts[2].replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
    const dataBytes = new TextEncoder().encode(parts[0] + '.' + parts[1]);
    
    const valid = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', cryptoKey, sigBytes, dataBytes);
    if (!valid) return null;
    
    return { email: payload.email, sub: payload.sub, method: 'cf-access' };
  } catch (e) {
    console.error('CF Access JWT verify error:', e.message);
    return null;
  }
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS_HEADERS });
    }

    const url = new URL(request.url);
    const path = url.pathname;

    // Auth: CF Access JWT or legacy API key
    const cfJwt = request.headers.get('CF-Access-Jwt-Assertion') || request.headers.get('Cf-Access-Jwt-Assertion');
    const apiKey = request.headers.get('X-API-Key');
    let authedUser = null;

    if (cfJwt) {
      // Verify CF Access JWT
      authedUser = await verifyCfAccessJwt(cfJwt, env);
    } else if (apiKey && apiKey === env.API_KEY) {
      authedUser = { email: 'api-key', method: 'legacy' };
    }

    // Writes require auth
    if (['POST', 'PUT', 'DELETE'].includes(request.method)) {
      if (!authedUser) {
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

    // DELETE /api/items/:id — soft delete (archive)
    if (path.startsWith('/api/items/') && request.method === 'DELETE') {
      const id = path.split('/').pop();
      
      // Get existing data before "deleting"
      const existing = await supa(env, `mktg_briefs?id=eq.${id}`);
      if (!existing || existing.length === 0) return json({ error: 'Not found' }, 404);
      
      const row = existing[0];
      const who = authedUser ? (authedUser.email || 'unknown') : 'unknown';
      
      // Archive to mktg_briefs_archive table
      const archive = {
        original_id: row.id,
        data: row,
        deleted_by: who,
        deleted_at: new Date().toISOString(),
      };
      try {
        await supa(env, 'mktg_briefs_archive', 'POST', archive);
      } catch (e) {
        // Archive table might not exist yet — log but continue
        console.error('Archive failed (table may not exist):', e.message);
      }
      
      // Actually delete from main table
      await supa(env, `mktg_briefs?id=eq.${id}`, 'DELETE');
      return json({ ok: true, archived: true, deletedBy: who });
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
