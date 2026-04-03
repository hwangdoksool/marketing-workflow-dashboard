// Workflow KV API Worker
// KV namespace: WORKFLOW_DATA

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

    // GET /api/items — list all
    if (path === '/api/items' && request.method === 'GET') {
      const data = await env.WORKFLOW_DATA.get('items', 'json') || [];
      return json(data);
    }

    // POST /api/items — create
    if (path === '/api/items' && request.method === 'POST') {
      const item = await request.json();
      const items = await env.WORKFLOW_DATA.get('items', 'json') || [];
      item.id = item.id || 'wf-' + Date.now();
      item.createdAt = item.createdAt || new Date().toISOString();
      item.updatedAt = new Date().toISOString();
      item.history = item.history || [];
      items.unshift(item);
      await env.WORKFLOW_DATA.put('items', JSON.stringify(items));
      return json(item, 201);
    }

    // PUT /api/items/:id — update
    if (path.startsWith('/api/items/') && request.method === 'PUT') {
      const id = path.split('/').pop();
      const updates = await request.json();
      const items = await env.WORKFLOW_DATA.get('items', 'json') || [];
      const idx = items.findIndex(i => i.id === id);
      if (idx === -1) return json({ error: 'Not found' }, 404);
      
      const old = items[idx];
      // Track status changes in history
      if (updates.status && updates.status !== old.status) {
        if (!old.history) old.history = [];
        old.history.push({ from: old.status, to: updates.status, at: new Date().toISOString() });
      }
      items[idx] = { ...old, ...updates, updatedAt: new Date().toISOString() };
      await env.WORKFLOW_DATA.put('items', JSON.stringify(items));
      return json(items[idx]);
    }

    // DELETE /api/items/:id
    if (path.startsWith('/api/items/') && request.method === 'DELETE') {
      const id = path.split('/').pop();
      let items = await env.WORKFLOW_DATA.get('items', 'json') || [];
      items = items.filter(i => i.id !== id);
      await env.WORKFLOW_DATA.put('items', JSON.stringify(items));
      return json({ ok: true });
    }

    // GET /api/export — full export
    if (path === '/api/export') {
      const data = await env.WORKFLOW_DATA.get('items', 'json') || [];
      return json({ exportedAt: new Date().toISOString(), count: data.length, items: data });
    }

    // POST /api/import — bulk import
    if (path === '/api/import' && request.method === 'POST') {
      const { items } = await request.json();
      if (!Array.isArray(items)) return json({ error: 'items array required' }, 400);
      await env.WORKFLOW_DATA.put('items', JSON.stringify(items));
      return json({ ok: true, count: items.length });
    }

    return json({ error: 'Not found' }, 404);
  }
};
