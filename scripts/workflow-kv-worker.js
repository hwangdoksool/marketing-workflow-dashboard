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

    // POST /api/analyze-signal — LLM이 자유 텍스트를 분석해서 시그널 필드 추출
    if (path === '/api/analyze-signal' && request.method === 'POST') {
      const { text } = await request.json();
      if (!text) return json({ error: 'text required' }, 400);

      const SOURCES = [
        '주간리포트','Meta Ads','GA4','네이버SA','아임웹주문',
        'CS카카오','CS아임웹','CS커뮤니티','인스타그램',
        '현장','외부시장','내부논의','이전실험','기타'
      ];
      const TYPES = ['위협','기회','외부','루프','현장'];

      const systemPrompt = `You are a marketing signal analyzer for Roomfit (smart weight machine, ₩3.48M).
Given a free-text observation from a marketer, extract structured signal fields.

Available sources: ${SOURCES.join(', ')}
Available signal types: ${TYPES.join(', ')}

Respond ONLY with JSON (no markdown):
{
  "title": "concise signal title in Korean (max 40 chars)",
  "signal": "cleaned-up observation text in Korean",
  "source": "one of the available sources",
  "sourceDetail": "specific reference (e.g. W13 report, ASC campaign #3)",
  "signalType": "one of the available types",
  "confidence": "high/medium/low"
}`;

      try {
        const resp = await fetch('https://api.openai.com/v1/chat/completions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${env.OPENAI_KEY}`
          },
          body: JSON.stringify({
            model: 'gpt-4o-mini',
            messages: [
              { role: 'system', content: systemPrompt },
              { role: 'user', content: text }
            ],
            temperature: 0.3,
            max_tokens: 300
          })
        });
        const data = await resp.json();
        const content = data.choices?.[0]?.message?.content || '';
        // Parse JSON from response
        const parsed = JSON.parse(content.replace(/```json?\n?/g, '').replace(/```/g, '').trim());
        return json(parsed);
      } catch (e) {
        return json({ error: 'Analysis failed', detail: e.message }, 500);
      }
    }

    return json({ error: 'Not found' }, 404);
  }
};
