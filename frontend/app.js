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
            spotlightContainer.innerHTML = '<div class="markdown-body" style="animation: fadeIn 0.5s ease-out;">' + marked.parse(data.card) + '</div>';
            
            if (data.trust_score && spotlightTrust) {
                spotlightTrust.classList.remove('hidden');
                document.getElementById('spotlightTrustText').textContent = `Trust: ${data.trust_score}%`;
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
    // FEATURE 7: Player Stock Market (Sentiment)
    // ==========================================
    const stockSearchBtn = document.getElementById('stockSearchBtn');
    const stockSearchInput = document.getElementById('stockSearchInput');
    const stockCard = document.getElementById('stockCard');
    const sentimentList = document.getElementById('sentimentList');
    const stockChartWrapper = document.getElementById('stockChartWrapper');

    async function fetchStock() {
        const name = stockSearchInput.value.trim();
        if (!name) return;

        stockCard.classList.add('hidden');
        stockChartWrapper.classList.add('hidden');
        sentimentList.innerHTML = `
            <div class="loading-skeleton">
                <div class="shimmer-line"></div><div class="shimmer-line w-75"></div><div class="shimmer-line"></div><br>
                <p style="text-align: center; color: var(--text-muted); margin-top: 1rem;">📈 Scraping news, running LLM sentiment analysis...</p>
            </div>`;

        try {
            const res = await fetch(`${API_BASE}/api/stock/${encodeURIComponent(name)}`);
            const data = await res.json();

            // Populate stock card
            document.getElementById('stockPlayerName').textContent = data.player;
            document.getElementById('stockPriceValue').textContent = data.stock_price.toFixed(1);
            document.getElementById('trendArrow').textContent = data.trend_direction;
            document.getElementById('trendPct').textContent = `${data.trend_pct > 0 ? '+' : ''}${data.trend_pct}%`;
            document.getElementById('stockSnippetCount').textContent = `${data.snippets.length} snippets analyzed`;
            document.getElementById('stockAvgSentiment').textContent = `Avg: ${data.avg_sentiment.toFixed(3)}`;

            // Sentiment tag
            const tag = document.getElementById('stockSentimentTag');
            tag.className = 'stock-sentiment-tag';
            if (data.avg_sentiment > 0.15) { tag.textContent = '🟢 BULLISH'; tag.classList.add('bullish'); }
            else if (data.avg_sentiment < -0.15) { tag.textContent = '🔴 BEARISH'; tag.classList.add('bearish'); }
            else { tag.textContent = '⚪ NEUTRAL'; tag.classList.add('neutral'); }

            // Trend color
            const trendEl = document.getElementById('stockTrend');
            trendEl.className = 'stock-trend';
            if (data.trend_pct > 0) trendEl.classList.add('positive');
            else if (data.trend_pct < 0) trendEl.classList.add('negative');
            else trendEl.classList.add('flat');

            stockCard.classList.remove('hidden');

            // Draw chart
            if (data.history && data.history.length > 1) {
                stockChartWrapper.classList.remove('hidden');
                drawStockChart(data.history);
            }

            // Render sentiment snippets
            if (data.snippets && data.snippets.length > 0) {
                sentimentList.innerHTML = data.snippets.map(s => {
                    const cls = s.score > 0.1 ? 'pos' : s.score < -0.1 ? 'neg' : 'neu';
                    const scoreDisplay = s.score > 0 ? `+${s.score.toFixed(1)}` : s.score.toFixed(1);
                    return `
                        <div class="sentiment-item ${cls}">
                            <div class="sentiment-score-pip ${cls}">${scoreDisplay}</div>
                            <div>
                                <div class="sentiment-text">${s.snippet || ''}</div>
                                <div class="sentiment-rationale">${s.rationale || ''}</div>
                            </div>
                        </div>`;
                }).join('');
            } else {
                sentimentList.innerHTML = '<p style="color: var(--text-muted); text-align: center;">No sentiment data returned.</p>';
            }
        } catch (e) {
            sentimentList.innerHTML = `<div style="color: #ff6b6b; text-align: center; padding: 2rem;">Error fetching stock data.</div>`;
        }
    }

    function drawStockChart(history) {
        const canvas = document.getElementById('stockCanvas');
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        canvas.width = rect.width * dpr;
        canvas.height = 200 * dpr;
        ctx.scale(dpr, dpr);
        const W = rect.width;
        const H = 200;

        ctx.clearRect(0, 0, W, H);

        const prices = history.map(h => h.stock_price);
        const minP = Math.min(...prices) - 5;
        const maxP = Math.max(...prices) + 5;
        const range = maxP - minP || 1;
        const pad = { top: 15, bottom: 25, left: 5, right: 5 };
        const chartW = W - pad.left - pad.right;
        const chartH = H - pad.top - pad.bottom;

        const points = prices.map((p, i) => ({
            x: pad.left + (i / Math.max(prices.length - 1, 1)) * chartW,
            y: pad.top + (1 - (p - minP) / range) * chartH
        }));

        // Gradient fill
        const lastPrice = prices[prices.length - 1];
        const firstPrice = prices[0];
        const isUp = lastPrice >= firstPrice;
        const fillGrad = ctx.createLinearGradient(0, pad.top, 0, H);
        fillGrad.addColorStop(0, isUp ? 'rgba(76,175,80,0.25)' : 'rgba(244,67,54,0.25)');
        fillGrad.addColorStop(1, 'rgba(0,0,0,0)');

        ctx.beginPath();
        ctx.moveTo(points[0].x, points[0].y);
        for (let i = 1; i < points.length; i++) {
            ctx.lineTo(points[i].x, points[i].y);
        }
        ctx.lineTo(points[points.length - 1].x, H - pad.bottom);
        ctx.lineTo(points[0].x, H - pad.bottom);
        ctx.closePath();
        ctx.fillStyle = fillGrad;
        ctx.fill();

        // Line
        ctx.beginPath();
        ctx.moveTo(points[0].x, points[0].y);
        for (let i = 1; i < points.length; i++) {
            ctx.lineTo(points[i].x, points[i].y);
        }
        ctx.strokeStyle = isUp ? '#4CAF50' : '#F44336';
        ctx.lineWidth = 2.5;
        ctx.lineJoin = 'round';
        ctx.stroke();

        // Data points
        points.forEach((pt, i) => {
            ctx.beginPath();
            ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
            ctx.fillStyle = isUp ? '#4CAF50' : '#F44336';
            ctx.fill();
            ctx.strokeStyle = 'rgba(0,0,0,0.5)';
            ctx.lineWidth = 1;
            ctx.stroke();
        });

        // Labels
        ctx.fillStyle = 'rgba(255,255,255,0.4)';
        ctx.font = '11px Inter, sans-serif';
        ctx.textAlign = 'center';
        const labelInterval = Math.max(1, Math.floor(points.length / 6));
        points.forEach((pt, i) => {
            if (i % labelInterval === 0 || i === points.length - 1) {
                ctx.fillText(prices[i].toFixed(0), pt.x, H - 5);
            }
        });
    }

    if (stockSearchBtn) stockSearchBtn.addEventListener('click', fetchStock);
    if (stockSearchInput) stockSearchInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') fetchStock(); });

});
