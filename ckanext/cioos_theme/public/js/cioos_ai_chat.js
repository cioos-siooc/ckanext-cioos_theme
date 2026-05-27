const CIOOS_AI = (function () {

  const API      = 'http://localhost:8000';
  const CKAN_API = '/api/3/action';

  // ── État ──────────────────────────────────────────────────
  let sessionId          = null;
  let panelOpen          = false;
  let isLoading          = false;
  let currentAbort       = null;
  let chatMessages       = [];

  // ── Session persistée ────────────────────────────────────
  function getSessionId()    { return sessionStorage.getItem('cioos_session'); }
  function setSessionId(id)  { sessionStorage.setItem('cioos_session', id); }
  function clearSession()    {
    sessionStorage.removeItem('cioos_session');
    sessionStorage.removeItem('cioos_chat_msgs');
  }

  function getSavedMessages() {
    try { return JSON.parse(sessionStorage.getItem('cioos_chat_msgs') || '[]'); }
    catch { return []; }
  }
  function saveMessages(msgs) {
    sessionStorage.setItem('cioos_chat_msgs',
      JSON.stringify(msgs.slice(-20)));
  }

  // ── Détection contexte CKAN ──────────────────────────────
  function detectContext() {
    const path   = window.location.pathname;
    const params = new URLSearchParams(window.location.search);
    const ctx    = { url: path + window.location.search };

    const datasetMatch = path.match(/\/dataset\/([^/?]+)$/);
    if (datasetMatch && !params.has('eov') && !params.has('q')) {
      ctx.type          = 'dataset';
      ctx.dataset_id    = datasetMatch[1];
      const titleEl     = document.querySelector('h1.page-heading, h1');
      ctx.dataset_title = titleEl ? titleEl.textContent.trim() : '';
      return ctx;
    }
    if (path.includes('/dataset')) {
      ctx.type         = 'search';
      ctx.eov_filter   = params.get('eov')          || '';
      ctx.org_filter   = params.get('organization') || '';
      ctx.search_query = params.get('q')            || '';
      return ctx;
    }
    if (path.includes('/organization/')) {
      ctx.type     = 'organization';
      ctx.org_slug = path.split('/organization/')[1]?.split('/')[0] || '';
      return ctx;
    }
    ctx.type = 'home';
    return ctx;
  }

  // ── Démarrer une session de chat ──────────────────────────
  async function startSession() {
    const existing = getSessionId();
    if (existing) { sessionId = existing; return; }
    const lang = document.documentElement.lang || 'fr';
    try {
      const r = await fetch(`${API}/conversation/start`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ lang }),
      });
      const d  = await r.json();
      sessionId = d.session_id;
      setSessionId(sessionId);
    } catch(e) {
      console.warn('CIOOS AI: session start failed', e);
    }
  }

  // ── Recherche fine-tunée ───────────────────────────────────
  async function searchFinetuned(query, topK = 10) {
    if (!query.trim()) return [];
    try {
      const r = await fetch(`${API}/search/finetuned`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ query, top_k: topK }),
      });
      const d = await r.json();
      return d.results || [];
    } catch(e) {
      console.warn('CIOOS AI: finetuned search failed', e);
      return [];
    }
  }

  // ── Envoi message avec streaming ──────────────────────────
  async function sendStreaming(query) {
    if (!sessionId) await startSession();
    if (currentAbort) currentAbort.abort();
    currentAbort = new AbortController();

    try {
      const r = await fetch(
        `${API}/conversation/${sessionId}/stream`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          query,
          page_context: detectContext(),
        }),
        signal: currentAbort.signal,
      });
      if (r.status === 404) {
        clearSession();
        await startSession();
        return sendStreaming(query);
      }
      return r;
    } catch(e) {
      if (e.name === 'AbortError') return null;
      throw e;
    }
  }

  // ── Construction du DOM ────────────────────────────────────
  function buildPanel() {
    const lang = document.documentElement.lang || 'fr';
    const isFr = lang === 'fr';

    // Bouton flottant
    const btn = document.createElement('button');
    btn.id = 'cioos-chat-btn';
    btn.title = isFr ? 'Assistant IA CIOOS' : 'CIOOS AI Assistant';
    btn.innerHTML = '💬';
    btn.style.cssText = `
      position:fixed; bottom:24px; right:24px;
      width:56px; height:56px;
      background:#52A79B; color:white;
      border:none; border-radius:50%;
      font-size:1.4rem; cursor:pointer;
      box-shadow:0 4px 16px rgba(0,0,0,0.2);
      z-index:9999;
      display:flex; align-items:center; justify-content:center;
      transform:scale(1); opacity:1;
      transition:background 0.15s, transform 0.2s, opacity 0.2s;
      font-family:inherit;
    `;
    btn.onmouseover = () => btn.style.background = '#3d8a7e';
    btn.onmouseout  = () => btn.style.background = '#52A79B';
    btn.onclick = togglePanel;

    // Panneau principal — largeur doublée pour 2 colonnes
    const panel = document.createElement('div');
    panel.id = 'cioos-chat-panel';
    panel.style.cssText = `
      position:fixed; right:-860px; top:0;
      height:100vh; width:min(840px, 100vw);
      background:#F7F9F9;
      box-shadow:-4px 0 20px rgba(0,0,0,0.12);
      z-index:9998;
      display:flex; flex-direction:column;
      transition:right 0.25s ease;
      font-family:inherit;
    `;

    panel.innerHTML = `
      <!-- Header -->
      <div style="
        background:#152F37; color:white;
        padding:0.85rem 1.2rem;
        display:flex; align-items:center;
        justify-content:space-between;
        flex-shrink:0;
      ">
        <div style="display:flex;align-items:center;gap:0.75rem;">
          <span style="font-size:1.1rem;"> </span>
          <div>
            <div style="font-weight:600;font-size:0.95rem;">
              ${isFr ? 'Assistant CIOOS' : 'CIOOS Assistant'}
            </div>
            <div style="font-size:0.72rem;opacity:0.6;">
              ${isFr ? 'Catalogue de données océanographiques'
                     : 'Ocean data catalogue'}
            </div>
          </div>
        </div>
        <div style="display:flex;gap:0.5rem;align-items:center;">
          <button id="cioos-reset-btn" title="${isFr ? 'Nouvelle session' : 'New session'}"
            style="
              background:rgba(255,255,255,0.1);
              border:1px solid rgba(255,255,255,0.25);
              color:white; border-radius:5px;
              padding:0.25rem 0.6rem; cursor:pointer;
              font-size:0.78rem; font-family:inherit;
            ">↺</button>
          <button id="cioos-close-btn"
            style="
              background:rgba(255,255,255,0.1);
              border:1px solid rgba(255,255,255,0.25);
              color:white; border-radius:5px;
              width:30px; height:30px; cursor:pointer;
              font-size:1rem; font-family:inherit;
              display:flex;align-items:center;justify-content:center;
            ">×</button>
        </div>
      </div>

      <!-- Corps à 2 colonnes -->
      <div style="
        flex:1; display:flex; gap:0;
        overflow:hidden; min-height:0;
      ">

        <!-- COLONNE GAUCHE — Chat -->
        <div style="
          flex:1; display:flex; flex-direction:column;
          border-right:1px solid #E2ECEA;
          background:white; min-height:0;
        ">
          <!-- Label colonne -->
          <div style="
            padding:0.5rem 1rem;
            background:#EBF8F4;
            border-bottom:1px solid #C6E3DF;
            font-size:0.75rem; font-weight:600;
            color:#0F6E56; letter-spacing:0.04em;
            text-transform:uppercase; flex-shrink:0;
          ">
             ${isFr ? 'Discussion' : 'Chat'}
          </div>

          <!-- Messages -->
          <div id="cioos-messages" style="
            flex:1; overflow-y:auto; padding:0.75rem;
            display:flex; flex-direction:column; gap:0.5rem;
          "></div>

          <!-- Suggestions -->
          <div id="cioos-suggestions" style="
            padding:0.4rem 0.6rem;
            border-top:1px solid #E2ECEA;
            display:flex; flex-wrap:wrap; gap:0.3rem;
            flex-shrink:0;
            background:#FAFAFA;
          "></div>

          <!-- Input chat -->
          <div style="
            padding:0.6rem 0.75rem;
            border-top:1px solid #E2ECEA;
            display:flex; gap:0.4rem;
            flex-shrink:0;
          ">
            <input id="cioos-chat-input" type="text"
              placeholder="${isFr ? 'Posez votre question…'
                                  : 'Ask a question…'}"
              style="
                flex:1; padding:0.5rem 0.75rem;
                border:1px solid #E2ECEA; border-radius:6px;
                font-size:0.85rem; font-family:inherit;
                outline:none;
              "
            />
            <button id="cioos-send-btn" style="
              padding:0.5rem 0.85rem;
              background:#52A79B; color:white;
              border:none; border-radius:6px;
              cursor:pointer; font-size:0.9rem;
              font-family:inherit; flex-shrink:0;
              transition:background 0.15s;
            ">→</button>
          </div>
        </div>

        <!-- COLONNE DROITE — Recherche fine-tunée -->
        <div style="
          width:340px; flex-shrink:0;
          display:flex; flex-direction:column;
          background:#F7F9F9; min-height:0;
        ">
          <!-- Label colonne -->
          <div style="
            padding:0.5rem 1rem;
            background:#FBF5E0;
            border-bottom:1px solid #F0E0A0;
            font-size:0.75rem; font-weight:600;
            color:#5C4200; letter-spacing:0.04em;
            text-transform:uppercase; flex-shrink:0;
          ">
             ${isFr ? 'Datasets correspondants' : 'Matching datasets'}
          </div>

          <!-- Barre de recherche fine-tunée -->
          <div style="padding:0.6rem 0.75rem;flex-shrink:0;
                      border-bottom:1px solid #E2ECEA;
                      background:white;">
            <div style="display:flex;gap:0.4rem;">
              <input id="cioos-search-input" type="text"
                placeholder="${isFr ? 'Recherche directe…'
                                    : 'Direct search…'}"
                style="
                  flex:1; padding:0.4rem 0.65rem;
                  border:1px solid #E2ECEA; border-radius:6px;
                  font-size:0.82rem; font-family:inherit;
                  outline:none;
                "
              />
              <button id="cioos-search-btn" style="
                padding:0.4rem 0.7rem;
                background:#152F37; color:white;
                border:none; border-radius:6px;
                cursor:pointer; font-size:0.82rem;
                font-family:inherit; flex-shrink:0;
              ">🔍</button>
            </div>
          </div>

          <!-- Résultats fine-tuned -->
          <div id="cioos-search-results" style="
            flex:1; overflow-y:auto; padding:0.5rem;
          ">
            <div style="
              text-align:center; color:#999;
              font-size:0.82rem; padding:2rem 1rem;
            ">
              ${isFr
                ? 'Les résultats apparaîtront ici lors de votre recherche ou discussion'
                : 'Results will appear here as you search or chat'}
            </div>
          </div>

          <!-- Footer stats -->
          <div id="cioos-search-meta" style="
            padding:0.4rem 0.75rem;
            border-top:1px solid #E2ECEA;
            font-size:0.72rem; color:#999;
            background:white; flex-shrink:0;
          "></div>
        </div>

      </div>
    `;

    document.body.appendChild(btn);
    document.body.appendChild(panel);

    // ── Event listeners ──────────────────────────────────────

    document.getElementById('cioos-close-btn').onclick = togglePanel;

    document.getElementById('cioos-reset-btn').onclick = async () => {
      clearSession();
      sessionId = null;
      chatMessages = [];
      document.getElementById('cioos-messages').innerHTML = '';
      document.getElementById('cioos-search-results').innerHTML = '';
      await startSession();
      appendWelcome();
      renderSuggestions();
    };

    // Envoi chat
    document.getElementById('cioos-send-btn').onclick = () => handleSend();
    document.getElementById('cioos-chat-input').onkeydown = e => {
      if (e.key === 'Enter' && !e.shiftKey) handleSend();
    };

    // Recherche fine-tunée directe
    document.getElementById('cioos-search-btn').onclick = () => handleSearch();
    document.getElementById('cioos-search-input').onkeydown = e => {
      if (e.key === 'Enter') handleSearch();
    };
  }

  // ── Envoi message chat + streaming ────────────────────────
  async function handleSend(text) {
    const input   = document.getElementById('cioos-chat-input');
    const sendBtn = document.getElementById('cioos-send-btn');
    const query   = text || (input ? input.value.trim() : '');
    if (!query) return;

    if (isLoading) {
      if (currentAbort) currentAbort.abort();
      return;
    }

    if (input)   input.value = '';
    isLoading = true;
    setLoadingState(true);

    // Message utilisateur
    appendUserMsg(query);

    // Lance la recherche fine-tunée EN PARALLÈLE
    const searchPromise = searchFinetuned(query);

    // Bulle bot vide pour le stream
    const botBubble = createBotBubble();
    document.getElementById('cioos-messages')?.appendChild(botBubble);
    scrollChatToBottom();

    const textEl   = botBubble.querySelector('.cioos-bubble-text');
    const cursorEl = botBubble.querySelector('.cioos-cursor');
    let   fullText = '';

    try {
      const response = await sendStreaming(query);
      if (!response) {
        if (textEl) textEl.textContent =
          document.documentElement.lang === 'fr'
            ? '⏹ Requête annulée.' : '⏹ Cancelled.';
        isLoading = false;
        setLoadingState(false);
        return;
      }

      const reader  = response.body.getReader();
      const decoder = new TextDecoder();
      let   buffer  = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          if (!part.startsWith('data: ')) continue;
          try {
            const ev = JSON.parse(part.slice(6));

            if (ev.type === 'token') {
              fullText += ev.content || '';
              if (textEl) textEl.textContent = fullText;
              scrollChatToBottom();
            }

            else if (ev.type === 'datasets' && ev.items?.length) {
              renderSearchResults(ev.items, ev.n_matching, 'chat');
            }

            else if (ev.type === 'action' && ev.action) {
              executeAction(ev.action, 0);
            }

            else if (ev.type === 'done') {
              if (cursorEl) cursorEl.remove();
              if (textEl) textEl.innerHTML = parseMarkdown(fullText);
              const metaEl = botBubble.querySelector('.cioos-bubble-meta');
              if (metaEl && ev.rag_mode && ev.rag_mode !== 'semantic') {
                metaEl.textContent =
                  `mode: ${ev.rag_mode}` +
                  (ev.n_matching > 0
                    ? ` · ${ev.n_matching} résultat(s)` : '');
                metaEl.style.display = 'block';
              }
            }

          } catch(e) { /* JSON parse error, skip */ }
        }
      }

    } catch(e) {
      if (cursorEl) cursorEl.remove();
      if (textEl) textEl.textContent =
        'Erreur de connexion à l\'API CIOOS.';
    }

    // Résultats de la recherche fine-tunée parallèle
    const results = await searchPromise;
    if (results.length > 0) {
      renderSearchResults(results, results.length, 'finetuned');
    }

    chatMessages.push({ role: 'user', text: query });
    chatMessages.push({ role: 'bot', text: fullText });
    saveMessages(chatMessages);

    isLoading = false;
    setLoadingState(false);
    renderSuggestions();
    currentAbort = null;
  }

  // ── Recherche directe fine-tunée ─────────────────────────
  async function handleSearch() {
    const input = document.getElementById('cioos-search-input');
    const query = input ? input.value.trim() : '';
    if (!query) return;

    const btn = document.getElementById('cioos-search-btn');
    if (btn) { btn.textContent = '⏳'; btn.disabled = true; }

    showSearchLoading();
    const results = await searchFinetuned(query, 10);
    renderSearchResults(results, results.length, 'finetuned');

    if (btn) { btn.textContent = '🔍'; btn.disabled = false; }
  }

  // ── Rendu des résultats dans le panneau droit ─────────────
  function renderSearchResults(results, total, source) {
    const container = document.getElementById('cioos-search-results');
    const metaEl    = document.getElementById('cioos-search-meta');
    if (!container) return;

    const lang = document.documentElement.lang || 'fr';
    const isFr = lang === 'fr';

    if (!results || results.length === 0) {
      container.innerHTML = `
        <div style="text-align:center;color:#999;
                    font-size:0.82rem;padding:2rem 1rem;">
          ${isFr ? 'Aucun résultat trouvé' : 'No results found'}
        </div>`;
      if (metaEl) metaEl.textContent = '';
      return;
    }

    container.innerHTML = results.map(ds => {
      const org = typeof ds.organization === 'object'
        ? ds.organization?.title || ''
        : ds.organization || '';
      const eovs = Array.isArray(ds.eov)
        ? ds.eov.slice(0, 2)
        : (ds.eov || '').split(',').slice(0, 2);
      const url  = `/dataset/${ds.name || ds.id || ''}`;
      const score = ds.score != null
        ? `${(ds.score * 100).toFixed(0)}%` : '';

      return `
        <a href="${url}" style="
          display:block;
          background:white; border:1px solid #E2ECEA;
          border-radius:7px; padding:0.7rem 0.8rem;
          margin-bottom:0.4rem; text-decoration:none;
          color:inherit; cursor:pointer;
          transition:border-color 0.15s;
        "
        onmouseover="this.style.borderColor='#52A79B'"
        onmouseout="this.style.borderColor='#E2ECEA'"
        >
          <div style="
            display:flex;justify-content:space-between;
            align-items:flex-start;gap:0.4rem;
            margin-bottom:0.3rem;
          ">
            <div style="
              font-weight:600;font-size:0.83rem;
              color:#152F37;line-height:1.3;flex:1;
            ">
              ${esc((ds.title || '').substring(0, 60))}
              ${(ds.title?.length||0) > 60 ? '…' : ''}
            </div>
            ${score ? `<span style="
              font-size:0.72rem;color:#888;
              background:#F0F0F0;padding:0.1rem 0.4rem;
              border-radius:4px;white-space:nowrap;
            ">${score}</span>` : ''}
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:0.3rem;">
            ${org ? `<span style="
              background:#152F37;color:white;
              padding:0.1rem 0.5rem;border-radius:4px;
              font-size:0.72rem;font-weight:500;
            ">${esc(org)}</span>` : ''}
            ${eovs.map(e => `
              <span style="
                background:#EBF8F4;color:#0F6E56;
                padding:0.1rem 0.5rem;border-radius:4px;
                font-size:0.72rem;
              ">${esc(e.trim())}</span>
            `).join('')}
            ${ds.period ? `<span style="
              color:#888;font-size:0.72rem;
            ">📅 ${esc(ds.period)}</span>` : ''}
          </div>
        </a>
      `;
    }).join('');

    if (metaEl) {
      const label = source === 'chat'
        ? (isFr ? 'depuis le chat' : 'from chat')
        : (isFr ? 'modèle fine-tuné' : 'fine-tuned model');
      metaEl.textContent =
        `${results.length}${total > results.length ? '/' + total : ''} ` +
        `${isFr ? 'résultat(s)' : 'result(s)'} · ${label}`;
    }
  }

  function showSearchLoading() {
    const container = document.getElementById('cioos-search-results');
    if (!container) return;
    container.innerHTML = [1,2,3,4].map(() => `
      <div style="
        background:#f0f0f0;
        border-radius:7px;height:70px;
        margin-bottom:0.4rem;
        background:linear-gradient(
          90deg,#f0f0f0 25%,#e0e0e0 50%,#f0f0f0 75%
        );
        background-size:200% 100%;
        animation:cioos-shimmer 1.4s infinite;
      "></div>
    `).join('');
  }

  // ── Bulle bot vide (remplie par le stream) ────────────────
  function createBotBubble() {
    const wrapper  = document.createElement('div');
    wrapper.style.cssText = 'display:flex;flex-direction:column;align-items:flex-start;';

    const bubble   = document.createElement('div');
    bubble.style.cssText = `
      background:#EBF8F4; color:#1A2E35;
      padding:0.55rem 0.8rem; border-radius:10px 10px 10px 2px;
      max-width:94%; font-size:0.85rem; line-height:1.5;
      font-family:inherit;
    `;

    const loadingEl = document.createElement('div');
    loadingEl.className = 'cioos-stream-loading';
    loadingEl.style.cssText =
      'font-size:0.75rem;color:#52A79B;margin-bottom:0.2rem;font-style:italic;';

    const textEl   = document.createElement('div');
    textEl.className = 'cioos-bubble-text';

    const cursor   = document.createElement('span');
    cursor.className = 'cioos-cursor';
    cursor.textContent = '▋';
    cursor.style.cssText =
      'color:#52A79B;animation:cioos-cursor-blink 0.7s step-end infinite;margin-left:1px;';

    const metaEl   = document.createElement('div');
    metaEl.className = 'cioos-bubble-meta';
    metaEl.style.cssText =
      'font-size:0.7rem;color:#52A79B;margin-top:0.3rem;display:none;';

    bubble.appendChild(loadingEl);
    bubble.appendChild(textEl);
    bubble.appendChild(cursor);
    bubble.appendChild(metaEl);
    wrapper.appendChild(bubble);

    if (!document.getElementById('cioos-cursor-anim')) {
      const s = document.createElement('style');
      s.id = 'cioos-cursor-anim';
      s.textContent = `
        @keyframes cioos-cursor-blink {
          0%,100% { opacity:1; } 50% { opacity:0; }
        }
        @keyframes cioos-shimmer {
          0% { background-position:200% 0; }
          100% { background-position:-200% 0; }
        }
      `;
      document.head.appendChild(s);
    }

    return wrapper;
  }

  // ── Message utilisateur ───────────────────────────────────
  function appendUserMsg(text) {
    const container = document.getElementById('cioos-messages');
    if (!container) return;
    const div = document.createElement('div');
    div.style.cssText = 'display:flex;justify-content:flex-end;';
    div.innerHTML = `
      <span style="
        background:#152F37; color:white;
        padding:0.5rem 0.8rem;
        border-radius:10px 10px 2px 10px;
        max-width:85%; font-size:0.85rem;
        line-height:1.4; font-family:inherit;
      ">${esc(text)}</span>
    `;
    container.appendChild(div);
    scrollChatToBottom();
  }

  // ── Message de bienvenue ──────────────────────────────────
  function appendWelcome() {
    const ctx  = detectContext();
    const isFr = (document.documentElement.lang || 'fr') === 'fr';
    let   text = '';

    if (ctx.type === 'dataset' && ctx.dataset_title) {
      text = isFr
        ? `Je vois que vous consultez **${ctx.dataset_title}**. Je peux le décrire, vous dire la période couverte, ou trouver des données similaires.`
        : `I see you're viewing **${ctx.dataset_title}**. I can describe it, tell you the period covered, or find similar data.`;
    } else if (ctx.type === 'search' && (ctx.eov_filter || ctx.search_query)) {
      const f = ctx.eov_filter || ctx.search_query;
      text = isFr
        ? `Vous consultez des résultats filtrés (${f}). Posez-moi une question ou affinez votre recherche.`
        : `You're viewing filtered results (${f}). Ask me a question or refine your search.`;
    } else {
      text = isFr
        ? `Bonjour ! Je suis l'assistant IA du catalogue CIOOS. Posez-moi une question sur les **3 336 datasets** océanographiques.`
        : `Hello! I'm the CIOOS AI assistant. Ask me about our **3,336 oceanographic datasets**.`;
    }

    const container = document.getElementById('cioos-messages');
    if (!container) return;
    const div = document.createElement('div');
    div.style.cssText = 'display:flex;flex-direction:column;align-items:flex-start;';
    div.innerHTML = `
      <div style="
        background:#EBF8F4; color:#1A2E35;
        padding:0.55rem 0.8rem;
        border-radius:10px 10px 10px 2px;
        max-width:94%; font-size:0.85rem;
        line-height:1.5; font-family:inherit;
      ">${parseMarkdown(text)}</div>
    `;
    container.appendChild(div);
    scrollChatToBottom();
  }

  // ── Suggestions contextuelles ─────────────────────────────
  function getSuggestions() {
    const ctx  = detectContext();
    const isFr = (document.documentElement.lang || 'fr') === 'fr';
    if (ctx.type === 'dataset') {
      return isFr
        ? ['Décris ce dataset','Quelle période couvre-t-il ?',
           'Qui a collecté ces données ?','Données similaires ?']
        : ['Describe this dataset','What period does it cover?',
           'Who collected this data?','Similar datasets?'];
    }
    if (ctx.type === 'search') {
      return isFr
        ? ['Combien de résultats ?','Décris le premier dataset',
           'Affine par organisation','Affine par période']
        : ['How many results?','Describe the first dataset',
           'Filter by organization','Filter by period'];
    }
    return isFr
      ? ['Données de température','Données du CIOOS Pacifique',
         'Combien de datasets ?','Données en format ERDDAP']
      : ['Temperature data','CIOOS Pacific datasets',
         'How many datasets?','Data in ERDDAP format'];
  }

  function renderSuggestions() {
    const container = document.getElementById('cioos-suggestions');
    if (!container) return;
    container.innerHTML = '';
    getSuggestions().forEach(s => {
      const btn = document.createElement('button');
      btn.textContent = s;
      btn.style.cssText = `
        padding:0.25rem 0.6rem;
        background:#EBF8F4; color:#0F6E56;
        border:1px solid #C6E3DF; border-radius:14px;
        font-size:0.75rem; cursor:pointer;
        font-family:inherit;
        transition:background 0.15s;
      `;
      btn.onmouseover = () => btn.style.background = '#C6E3DF';
      btn.onmouseout  = () => btn.style.background = '#EBF8F4';
      btn.onclick = () => {
        handleSend(s);
        const si = document.getElementById('cioos-search-input');
        if (si) { si.value = s; handleSearch(); }
      };
      container.appendChild(btn);
    });
  }

  // ── État loading / stop ───────────────────────────────────
  function setLoadingState(loading) {
    const input   = document.getElementById('cioos-chat-input');
    const sendBtn = document.getElementById('cioos-send-btn');
    if (!input || !sendBtn) return;
    if (loading) {
      input.disabled        = true;
      input.style.opacity   = '0.5';
      sendBtn.textContent   = '⏹';
      sendBtn.title         = 'Annuler';
      sendBtn.style.background = '#C0392B';
      sendBtn.onclick = () => {
        if (currentAbort) currentAbort.abort();
      };
    } else {
      input.disabled        = false;
      input.style.opacity   = '1';
      sendBtn.textContent   = '→';
      sendBtn.title         = '';
      sendBtn.style.background = '#52A79B';
      sendBtn.onclick       = () => handleSend();
      input.focus();
    }
  }

  // ── Ouvrir / fermer ───────────────────────────────────────
  function togglePanel() {
    const panel = document.getElementById('cioos-chat-panel');
    const btn   = document.getElementById('cioos-chat-btn');
    if (!panel) return;

    panelOpen = !panelOpen;

    if (panelOpen) {
      panel.style.right = '0';
      if (btn) {
        btn.style.transform = 'scale(0)';
        btn.style.opacity   = '0';
        setTimeout(() => btn.style.display = 'none', 200);
      }
      document.body.style.marginRight = 'min(840px, 100vw)';

      const container = document.getElementById('cioos-messages');
      if (container && container.children.length === 0) {
        const stored = getSavedMessages();
        if (stored.length > 0) {
          const sep = document.createElement('div');
          sep.style.cssText =
            'text-align:center;font-size:0.72rem;color:#aaa;margin:0.4rem 0;';
          sep.textContent = '— conversation précédente —';
          container.appendChild(sep);
          stored.forEach(m => {
            if (m.role === 'user') appendUserMsg(m.text);
            else {
              const b = createBotBubble();
              const t = b.querySelector('.cioos-bubble-text');
              const c = b.querySelector('.cioos-cursor');
              if (t) t.innerHTML = parseMarkdown(m.text);
              if (c) c.remove();
              container.appendChild(b);
            }
          });
        }
        appendWelcome();
        renderSuggestions();
        startSession();
      }

    } else {
      panel.style.right = '-860px';
      if (btn) {
        btn.style.display = 'flex';
        btn.offsetHeight;
        btn.style.transform = 'scale(1)';
        btn.style.opacity   = '1';
      }
      document.body.style.marginRight = '0';
    }
  }

  // ── Utilitaires ───────────────────────────────────────────
  function scrollChatToBottom() {
    const c = document.getElementById('cioos-messages');
    if (c) c.scrollTop = c.scrollHeight;
  }

  function esc(str) {
    return String(str || '')
      .replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function parseMarkdown(text) {
    return String(text || '')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*\n]+?)\*/g, '<em>$1</em>')
      .replace(/^[•\-]\s+(.+)$/gm, '<li>$1</li>')
      .replace(/(<li>.*<\/li>\n?)+/g,
        m => `<ul style="margin:0.3rem 0 0.3rem 1.1rem;padding:0;">${m}</ul>`)
      .replace(/\n/g, '<br>');
  }

  function executeAction(action, n) {
    if (!action || action.type === 'none') return;
    const lang = document.documentElement.lang || 'fr';
    const isFr = lang === 'fr';
    if (action.ckan_url && action.type !== 'none') {
      const existing = document.getElementById('cioos-redirect-btn');
      if (existing) existing.remove();
      const a = document.createElement('a');
      a.id = 'cioos-redirect-btn';
      a.href = action.ckan_url;
      a.textContent = isFr
        ? `🔍 Voir dans le catalogue →`
        : `🔍 View in catalogue →`;
      a.style.cssText = `
        display:block; margin:0.4rem 0.6rem;
        padding:0.5rem 0.8rem;
        background:#52A79B; color:white;
        text-decoration:none; border-radius:6px;
        font-size:0.82rem; font-weight:600;
        text-align:center; font-family:inherit;
      `;
      const sugg = document.getElementById('cioos-suggestions');
      if (sugg) sugg.insertBefore(a, sugg.firstChild);
    }
  }

  // ── Initialisation ────────────────────────────────────────
  function init() {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => {
        buildPanel();
      });
    } else {
      buildPanel();
    }
  }

  return { init, togglePanel, send: handleSend, search: handleSearch };

})();

CIOOS_AI.init();
