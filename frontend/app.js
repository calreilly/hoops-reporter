document.addEventListener('DOMContentLoaded', () => {
    const API_BASE = "http://127.0.0.1:8000";

    // ==========================================
    // NAVIGATION
    // ==========================================
    const navBtns = document.querySelectorAll('.nav-btn');
    const viewPanels = document.querySelectorAll('.view-panel');

    navBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            navBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            viewPanels.forEach(v => v.classList.add('hidden'));
            const targetId = btn.getAttribute('data-view');
            const target = document.getElementById(targetId);
            if (target) target.classList.remove('hidden');
        });
    });

    // ==========================================
    // FEATURE 1: Live Scoreboard Ticker
    // ==========================================
    async function fetchScores() {
        const track = document.getElementById('tickerTrack');
        try {
            const res = await fetch(`${API_BASE}/api/scores`);
            const data = await res.json();
            if (data.games && data.games.length > 0) {
                track.innerHTML = data.games.map(g => 
                    `<div class="ticker-game">
                        <span class="league-tag">${g.league}</span>
                        <span>${g.away}</span>
                        <span class="score">${g.away_score}</span>
                        <span class="at-sign">@</span>
                        <span>${g.home}</span>
                        <span class="score">${g.home_score}</span>
                        <span class="status">${g.status}</span>
                    </div>`
                ).join('');
            } else {
                track.innerHTML = '<span class="ticker-placeholder">No games scheduled right now</span>';
            }
        } catch (e) {
            track.innerHTML = '<span class="ticker-placeholder">Scores unavailable</span>';
        }
    }
    fetchScores();
    setInterval(fetchScores, 60000);

    // ==========================================
    // HOT STORIES (existing, with cache badge)
    // ==========================================
    const refreshFeedBtn = document.getElementById('refreshFeedBtn');
    const hotStoriesContainer = document.getElementById('hotStoriesContainer');
    let isFetchingStories = false;

    if (refreshFeedBtn && hotStoriesContainer) {
        refreshFeedBtn.addEventListener('click', async () => {
            if (isFetchingStories) return;
            isFetchingStories = true;
            refreshFeedBtn.textContent = "Agent Researching...";
            
            const feedTrustBadge = document.getElementById('feedTrustBadge');
            const cacheBadge = document.getElementById('cacheBadge');
            if (feedTrustBadge) feedTrustBadge.classList.add('hidden');
            if (cacheBadge) cacheBadge.classList.add('hidden');
            
            hotStoriesContainer.innerHTML = `
                <div class="loading-skeleton">
                    <div class="shimmer-line"></div><div class="shimmer-line w-75"></div><div class="shimmer-line"></div><br>
                    <div class="shimmer-line w-50"></div><div class="shimmer-line"></div><div class="shimmer-line w-75"></div><br>
                    <p style="text-align: center; color: var(--text-muted); font-size: 0.9rem; margin-top: 1rem;">
                        🔍 Agent is searching the web, consulting ESPN via MCP, and querying our RAG archive...
                    </p>
                </div>`;

            try {
                const res = await fetch(`${API_BASE}/api/hot-stories`);
                if (!res.ok) throw new Error("API failed");
                const data = await res.json();
                hotStoriesContainer.innerHTML = '<div class="markdown-body" style="animation: fadeIn 0.5s ease-out;">' + marked.parse(data.feed) + '</div>';
                
                if (data.trust_score && feedTrustBadge) {
                    const feedTrustText = document.getElementById('feedTrustText');
                    feedTrustBadge.classList.remove('hidden');
                    feedTrustText.textContent = `Verified: ${data.trust_score}%`;
                }
                if (data.cached && cacheBadge) {
                    cacheBadge.classList.remove('hidden');
                }
            } catch (e) {
                console.error(e);
                hotStoriesContainer.innerHTML = `<div style="color: #ff6b6b; text-align: center; padding: 2rem;">Error fetching Hot Stories.</div>`;
            } finally {
                isFetchingStories = false;
                refreshFeedBtn.textContent = "Refresh Feed";
            }
        });
        setTimeout(() => refreshFeedBtn.click(), 500);
    }

    // ==========================================
    // REPORT GENERATION (with pipeline viz)
    // ==========================================
    const generateBtn = document.getElementById('generateBtn');
    const promptInput = document.getElementById('prompt');
    const reportContainer = document.getElementById('reportContainer');
    const btnText = document.querySelector('.btn-text');
    const spinner = document.querySelector('.spinner');
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');

    let isGenerating = false;

    if (generateBtn) {
        generateBtn.addEventListener('click', async () => {
            const prompt = promptInput.value.trim();
            if (!prompt || isGenerating) return;

            isGenerating = true;
            generateBtn.disabled = true;
            btnText.textContent = "Synthesizing...";
            spinner.classList.remove('hidden');
            statusDot.classList.add('active');
            statusText.textContent = "Agent Working (Calling MCP & Vector DB)...";
            statusText.style.color = "var(--accent)";
            
            const trustBadge = document.getElementById('trustBadge');
            if (trustBadge) trustBadge.classList.add('hidden');
            
            const pipelineViz = document.getElementById('pipelineViz');
            if (pipelineViz) pipelineViz.classList.add('hidden');

            reportContainer.innerHTML = `<div class="loading-skeleton"><div class="shimmer-line"></div><div class="shimmer-line"></div><div class="shimmer-line w-75"></div><br><div class="shimmer-line"></div><div class="shimmer-line w-50"></div></div>`;

            try {
                const response = await fetch(`${API_BASE}/api/report`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ prompt })
                });

                if (!response.ok) throw new Error("API request failed");
                const data = await response.json();
                
                statusText.textContent = "Report Completed";
                statusText.style.color = "#4ADE80";
                statusDot.classList.remove('active');
                statusDot.style.background = "#4ADE80";

                reportContainer.innerHTML = '<div class="markdown-body" style="animation: fadeIn 0.5s ease-out;">' + marked.parse(data.report) + '</div>';

                if (data.trust_score && trustBadge) {
                    const trustScoreText = document.getElementById('trustScoreText');
                    trustBadge.classList.remove('hidden');
                    trustScoreText.textContent = `Factuality: ${data.trust_score}%`;
                    trustBadge.title = data.auditor_note || "Verified by LLM-as-a-Judge";
                }

                // FEATURE 4: Pipeline Visualization
                if (data.tool_trace && data.tool_trace.length > 0 && pipelineViz) {
                    pipelineViz.classList.remove('hidden');
                    const pipelineContent = document.getElementById('pipelineContent');
                    pipelineContent.innerHTML = data.tool_trace.map((t, i) => `
                        <div class="pipeline-step">
                            <div class="pipeline-icon">${i + 1}</div>
                            <div>
                                <span class="pipeline-tool">${t.tool}</span>
                                <span class="pipeline-args">${t.args}</span>
                            </div>
                        </div>
                    `).join('');
                }
            } catch (error) {
                console.error(error);
                reportContainer.innerHTML = `<div style="color: #ff6b6b; text-align: center; padding: 2rem;">Error connecting to API.</div>`;
                statusText.textContent = "System Offline";
                statusText.style.color = "#ff6b6b";
            } finally {
                isGenerating = false;
                generateBtn.disabled = false;
                btnText.textContent = "Generate Report";
                spinner.classList.add('hidden');
            }
        });
    }

    // Pipeline toggle
    const pipelineToggle = document.getElementById('pipelineToggle');
    if (pipelineToggle) {
        pipelineToggle.addEventListener('click', () => {
            const content = document.getElementById('pipelineContent');
            content.classList.toggle('hidden');
            pipelineToggle.textContent = content.classList.contains('hidden') ? '🔧 Show Agent Pipeline' : '🔧 Hide Agent Pipeline';
        });
    }

    // ==========================================
    // FEATURE 2: Ask the Reporter Chat
    // ==========================================
    const chatInput = document.getElementById('chatInput');
    const chatSendBtn = document.getElementById('chatSendBtn');
    const chatMessages = document.getElementById('chatMessages');

    async function sendChat() {
        const message = chatInput.value.trim();
        if (!message) return;

        // User bubble
        const userBubble = document.createElement('div');
        userBubble.className = 'chat-bubble user';
        userBubble.innerHTML = `<strong>You:</strong> ${message}`;
        chatMessages.appendChild(userBubble);
        chatInput.value = '';
        chatMessages.scrollTop = chatMessages.scrollHeight;

        // Loading bubble
        const loadingBubble = document.createElement('div');
        loadingBubble.className = 'chat-bubble oracle';
        loadingBubble.innerHTML = '<em>Reporter is thinking...</em>';
        chatMessages.appendChild(loadingBubble);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        try {
            const res = await fetch(`${API_BASE}/api/chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message })
            });
            const data = await res.json();
            loadingBubble.innerHTML = `<strong>Reporter:</strong> ${marked.parse(data.reply)}`;
            
            // Show tool trace inline if tools were used
            if (data.tool_trace && data.tool_trace.length > 0) {
                const traceHtml = data.tool_trace.map(t => 
                    `<span style="font-size:0.75rem; color: var(--accent);">🔧 ${t.tool}(${t.args})</span>`
                ).join(' → ');
                loadingBubble.innerHTML += `<div style="margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px solid rgba(255,255,255,0.05);">${traceHtml}</div>`;
            }

            // Show RAG sources inline
            if (data.rag_sources && data.rag_sources.length > 0) {
                const uniqueId = 'sources_' + Math.random().toString(36).substr(2, 9);
                const sourcesHtml = data.rag_sources.map(s => `
                    <div class="rag-source-item" style="background: rgba(0,0,0,0.2); padding: 0.5rem; border-radius: 6px; font-size: 0.8rem; margin-top: 0.5rem; border-left: 2px solid var(--primary);">
                        <strong style="color: var(--primary);">📄 ${s.source}</strong><br>
                        <span style="color: rgba(255,255,255,0.7);">${s.content}</span>
                    </div>
                `).join('');
                
                loadingBubble.innerHTML += `
                    <div style="margin-top: 0.75rem;">
                        <button onclick="document.getElementById('${uniqueId}').classList.toggle('hidden')" style="background:none; border:1px solid rgba(255,255,255,0.1); padding:0.25rem 0.5rem; border-radius:4px; color:var(--text-light); cursor:pointer; font-size:0.75rem; transition: background 0.2s;">
                            📚 Toggle RAG Sources (${data.rag_sources.length})
                        </button>
                        <div id="${uniqueId}" class="hidden" style="margin-top: 0.5rem;">
                            ${sourcesHtml}
                        </div>
                    </div>
                `;
            }
        } catch (e) {
            loadingBubble.innerHTML = '<strong>Reporter:</strong> <span style="color: #ff6b6b;">Connection error. Is the backend running?</span>';
        }
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    if (chatSendBtn) chatSendBtn.addEventListener('click', sendChat);
    if (chatInput) chatInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendChat(); });

    // ==========================================
    // FEATURE 3: Player Spotlight
    // ==========================================
    const playerSearchBtn = document.getElementById('playerSearchBtn');
    const playerSearchInput = document.getElementById('playerSearchInput');
    const spotlightContainer = document.getElementById('spotlightContainer');

    async function searchPlayer() {
        const name = playerSearchInput.value.trim();
        if (!name) return;

        spotlightContainer.innerHTML = `<div class="loading-skeleton"><div class="shimmer-line"></div><div class="shimmer-line w-75"></div><div class="shimmer-line"></div><br><div class="shimmer-line w-50"></div><div class="shimmer-line"></div><p style="text-align: center; color: var(--text-muted); margin-top: 1rem;">🌟 Building profile with ESPN + RAG + Web Search...</p></div>`;
        
        const spotlightTrust = document.getElementById('spotlightTrustBadge');
        if (spotlightTrust) spotlightTrust.classList.add('hidden');

        try {
            const res = await fetch(`${API_BASE}/api/player/${encodeURIComponent(name)}`);
            const data = await res.json();
            // Player Spotlight render
            spotlightContainer.innerHTML = '<div class="markdown-body" style="animation: fadeIn 0.5s ease-out;">' + marked.parse(data.card) + '</div>';
            
            if (data.trust_score && spotlightTrust) {
                spotlightTrust.classList.remove('hidden');
                document.getElementById('spotlightTrustText').textContent = `Trust: ${data.trust_score}%`;
            }

            // RAG Sources render
            const sourcesPanel = document.getElementById('spotlightSourcesPanel');
            const sourcesList = document.getElementById('spotlightSourcesList');
            const sourcesToggle = document.getElementById('spotlightSourcesToggle');
            if (data.rag_sources && data.rag_sources.length > 0) {
                sourcesPanel.classList.remove('hidden');
                sourcesToggle.textContent = `📚 View RAG Sources (${data.rag_sources.length})`;
                sourcesList.innerHTML = data.rag_sources.map(s => `
                    <div class="rag-source-item" style="background: rgba(0,0,0,0.2); padding: 0.75rem; border-radius: 8px; font-size: 0.85rem; border-left: 3px solid var(--primary);">
                        <div style="color: var(--primary); font-weight: 600; margin-bottom: 0.25rem;">📄 ${s.source}</div>
                        <div style="color: var(--text-muted); line-height: 1.4;">${s.content}</div>
                    </div>
                `).join('');
                
                const newToggle = sourcesToggle.cloneNode(true);
                sourcesToggle.parentNode.replaceChild(newToggle, sourcesToggle);
                newToggle.addEventListener('click', () => {
                    sourcesList.classList.toggle('hidden');
                    newToggle.textContent = sourcesList.classList.contains('hidden') ? 
                        `📚 View RAG Sources (${data.rag_sources.length})` : 
                        `📚 Hide RAG Sources`;
                });
            } else {
                if (sourcesPanel) sourcesPanel.classList.add('hidden');
            }
        } catch (e) {
            spotlightContainer.innerHTML = `<div style="color: #ff6b6b; text-align: center; padding: 2rem;">Error fetching player data.</div>`;
        }
    }

    if (playerSearchBtn) playerSearchBtn.addEventListener('click', searchPlayer);
    if (playerSearchInput) playerSearchInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') searchPlayer(); });

    // ==========================================
    // FEATURE 6: Evaluation Dashboard
    // ==========================================
    const refreshAnalyticsBtn = document.getElementById('refreshAnalyticsBtn');

    async function fetchAnalytics() {
        try {
            const res = await fetch(`${API_BASE}/api/eval-history`);
            const data = await res.json();

            document.getElementById('avgScoreStat').textContent = data.avg_score || '--';
            document.getElementById('totalEvalsStat').textContent = data.total_evals || '0';

            // Render bar chart
            const chartEl = document.getElementById('evalChart');
            const entries = data.entries || [];
            if (entries.length > 0) {
                chartEl.innerHTML = entries.slice(-30).map(e => {
                    const h = Math.max(5, e.score);
                    const color = e.score >= 80 ? 'var(--accent)' : e.score >= 60 ? 'var(--primary)' : '#ff6b6b';
                    return `<div class="eval-bar" style="height: ${h}%; background: ${color};" data-score="${e.score} — ${e.type}" title="${e.type}: ${e.score}%"></div>`;
                }).join('');
            } else {
                chartEl.innerHTML = '<p style="color: var(--text-muted); font-size: 0.85rem; width: 100%; text-align: center;">No data yet</p>';
            }

            // Render log
            const logEl = document.getElementById('evalLog');
            if (entries.length > 0) {
                logEl.innerHTML = entries.slice().reverse().slice(0, 20).map(e => `
                    <div class="eval-entry">
                        <span class="type-tag">${e.type}</span>
                        <span style="color: var(--text-muted); font-size: 0.8rem;">${new Date(e.timestamp).toLocaleString()}</span>
                        <span class="eval-score-pill">${e.score}%</span>
                    </div>
                `).join('');
            }
        } catch (e) {
            console.error('Analytics fetch failed:', e);
        }
    }

    if (refreshAnalyticsBtn) refreshAnalyticsBtn.addEventListener('click', fetchAnalytics);
    // Auto-fetch analytics when that tab is clicked
    navBtns.forEach(btn => {
        if (btn.dataset.view === 'analyticsView') {
            btn.addEventListener('click', fetchAnalytics);
        }
    });

    // ==========================================
    // FEATURE 18: Ragas-Style Evaluation Suite
    // ==========================================
    const runRagEvalBtn = document.getElementById('runRagEvalBtn');
    if (runRagEvalBtn) {
        runRagEvalBtn.addEventListener('click', async () => {
            const statusEl = document.getElementById('ragEvalStatus');
            const summary1 = document.getElementById('ragEvalSummary');
            const summary2 = document.getElementById('ragEvalSummary2');
            const logEl = document.getElementById('ragEvalLog');
            
            runRagEvalBtn.disabled = true;
            statusEl.classList.remove('hidden');
            summary1.classList.add('hidden');
            summary2.classList.add('hidden');
            logEl.classList.add('hidden');
            
            try {
                const res = await fetch(`${API_BASE}/api/eval-rag`, { method: "POST" });
                const data = await res.json();
                
                document.getElementById('ragPrecisionStat').textContent = data.metrics.context_precision;
                document.getElementById('ragRecallStat').textContent = data.metrics.context_recall;
                document.getElementById('ragFaithfulnessStat').textContent = data.metrics.faithfulness;
                document.getElementById('ragRelevanceStat').textContent = data.metrics.answer_relevance;
                
                logEl.innerHTML = data.details.map(d => `
                    <div style="background: rgba(0,0,0,0.2); padding: 1rem; border-radius: 8px; margin-top: 0.5rem; text-align: left;">
                        <strong style="color: var(--primary);">Query:</strong> ${d.query}<br>
                        <div style="font-size: 0.85rem; color: var(--text-muted); margin: 0.5rem 0;">${d.answer}</div>
                        <div style="display: flex; gap: 1rem; font-size: 0.8rem; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 0.5rem;">
                            <span title="Context Precision">🎯 P: ${d.scores.context_precision}</span>
                            <span title="Context Recall">🔍 R: ${d.scores.context_recall}</span>
                            <span title="Faithfulness">✅ F: ${d.scores.faithfulness}</span>
                            <span title="Answer Relevance">📈 A: ${d.scores.answer_relevance}</span>
                        </div>
                    </div>
                `).join('');
                
                summary1.classList.remove('hidden');
                summary2.classList.remove('hidden');
                logEl.classList.remove('hidden');
                
            } catch (e) {
                console.error("RAG Eval failed", e);
                logEl.innerHTML = `<div style="color: #ff6b6b; padding: 1rem; text-align: center;">Evaluation failed. Is the server running?</div>`;
                logEl.classList.remove('hidden');
            } finally {
                runRagEvalBtn.disabled = false;
                statusEl.classList.add('hidden');
            }
        });
    }

    // ==========================================
    // FEATURE 19: Dynamic Knowledge Base Manager
    // ==========================================
    const refreshKbBtn = document.getElementById('refreshKbBtn');
    const kbIngestBtn = document.getElementById('kbIngestBtn');
    
    async function fetchKnowledgeBase() {
        const listEl = document.getElementById('kbDocumentList');
        if (!listEl) return;
        
        try {
            const res = await fetch(`${API_BASE}/api/knowledge`);
            const data = await res.json();
            
            if (data.sources && data.sources.length > 0) {
                listEl.innerHTML = data.sources.map(s => `
                    <div style="background: rgba(0,0,0,0.2); padding: 0.75rem 1rem; border-radius: 8px; margin-bottom: 0.5rem; display: flex; align-items: center; border-left: 3px solid var(--primary);">
                        <span style="font-size: 1.2rem; margin-right: 1rem;">📄</span>
                        <span style="font-weight: 500;">${s}</span>
                    </div>
                `).join('');
            } else {
                listEl.innerHTML = '<p style="color: var(--text-muted); text-align: center;">No documents found.</p>';
            }
        } catch (e) {
            console.error("Failed to fetch knowledge base", e);
            listEl.innerHTML = '<p style="color: #ff6b6b; text-align: center;">Error loading documents.</p>';
        }
    }
    
    if (refreshKbBtn) refreshKbBtn.addEventListener('click', fetchKnowledgeBase);
    
    if (kbIngestBtn) {
        kbIngestBtn.addEventListener('click', async () => {
            const sourceInput = document.getElementById('kbSourceName');
            const contentInput = document.getElementById('kbContent');
            const statusEl = document.getElementById('kbStatus');
            const isUrlInput = document.getElementById('kbIsUrl');
            const spinner = kbIngestBtn.querySelector('.spinner');
            const btnText = kbIngestBtn.querySelector('.btn-text');
            
            const source_name = sourceInput.value.trim();
            const content = contentInput.value.trim();
            const is_url = isUrlInput ? isUrlInput.checked : false;
            
            if (!content || (!is_url && !source_name)) {
                statusEl.textContent = "Please provide content. Source Name is required unless 'Content is a URL' is checked.";
                statusEl.style.color = "#ff6b6b";
                statusEl.classList.remove('hidden');
                return;
            }
            
            kbIngestBtn.disabled = true;
            spinner.classList.remove('hidden');
            btnText.textContent = is_url ? "Scraping & Embedding..." : "Processing & Embedding...";
            statusEl.classList.add('hidden');
            
            try {
                const res = await fetch(`${API_BASE}/api/knowledge`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ source_name, content, is_url })
                });
                const data = await res.json();
                
                statusEl.classList.remove('hidden');
                if (data.success) {
                    statusEl.textContent = data.message;
                    statusEl.style.color = "#4ADE80";
                    sourceInput.value = '';
                    contentInput.value = '';
                    fetchKnowledgeBase(); // refresh
                } else {
                    statusEl.textContent = data.message || "Failed to ingest document.";
                    statusEl.style.color = "#ff6b6b";
                }
            } catch (e) {
                statusEl.textContent = "Connection error.";
                statusEl.style.color = "#ff6b6b";
                statusEl.classList.remove('hidden');
            } finally {
                kbIngestBtn.disabled = false;
                spinner.classList.add('hidden');
                btnText.textContent = "Ingest & Embed";
            }
        });
    }
    
    // Auto-fetch knowledge base when tab is clicked
    navBtns.forEach(btn => {
        if (btn.dataset.view === 'knowledgeView') {
            btn.addEventListener('click', fetchKnowledgeBase);
        }
    });

});
