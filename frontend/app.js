document.addEventListener('DOMContentLoaded', () => {
    const generateBtn = document.getElementById('generateBtn');
    const promptInput = document.getElementById('prompt');
    const reportContainer = document.getElementById('reportContainer');
    const btnText = document.querySelector('.btn-text');
    const spinner = document.querySelector('.spinner');
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');

    let isGenerating = false;

    // Fast API Backend Endpoint
    const API_URL = "http://127.0.0.1:8000/api/report";

    generateBtn.addEventListener('click', async () => {
        const prompt = promptInput.value.trim();
        if (!prompt || isGenerating) return;

        // Set Loading State
        isGenerating = true;
        generateBtn.disabled = true;
        btnText.textContent = "Synthesizing...";
        spinner.classList.remove('hidden');
        
        statusDot.classList.add('active');
        statusText.textContent = "Agent Working (Calling MCP & Vector DB)...";
        statusText.style.color = "var(--accent)";
        
        const trustBadge = document.getElementById('trustBadge');
        if (trustBadge) trustBadge.classList.add('hidden');

        // Show skeleton
        reportContainer.innerHTML = `
            <div class="loading-skeleton">
                <div class="shimmer-line"></div>
                <div class="shimmer-line"></div>
                <div class="shimmer-line w-75"></div>
                <br>
                <div class="shimmer-line"></div>
                <div class="shimmer-line w-50"></div>
            </div>
        `;

        try {
            const response = await fetch(API_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ prompt })
            });

            if (!response.ok) throw new Error("API request failed");
            
            const data = await response.json();
            
            // Success State
            statusText.textContent = "Report Completed";
            statusText.style.color = "#4ADE80"; // Match success color
            statusDot.classList.remove('active');
            statusDot.style.background = "#4ADE80";

            // Render Markdown directly with a fade-in to avoid breaking HTML tags during typing
            reportContainer.innerHTML = '<div class="markdown-body" style="animation: fadeIn 0.5s ease-out; line-height: 1.6;">' + marked.parse(data.report) + '</div>';

            if (data.trust_score) {
                const trustBadge = document.getElementById('trustBadge');
                const trustScoreText = document.getElementById('trustScoreText');
                if (trustBadge && trustScoreText) {
                    trustBadge.classList.remove('hidden');
                    trustScoreText.textContent = `Factuality: ${data.trust_score}%`;
                    trustBadge.title = data.auditor_note || "Verified by LLM-as-a-Judge";
                }
            }

        } catch (error) {
            console.error(error);
            reportContainer.innerHTML = `<div style="color: #ff6b6b; text-align: center; padding: 2rem;">Error connecting to API. Is the FastAPI server running on port 8000?</div>`;
            statusText.textContent = "System Offline";
            statusText.style.color = "#ff6b6b";
            statusDot.classList.remove('active');
            statusDot.style.background = "#ff6b6b";
        } finally {
            isGenerating = false;
            generateBtn.disabled = false;
            btnText.textContent = "Generate Report";
            spinner.classList.add('hidden');
        }
    });

    function typeText(text, element) {
        let i = 0;
        element.textContent = '';
        
        function type() {
            if (i < text.length) {
                element.textContent += text.charAt(i);
                i++;
                setTimeout(type, Math.random() * 15 + 5);
            } else {
                element.classList.remove('typing-text');
            }
        }
        type();
    }

    // Tabs Logic
    const tabBtns = document.querySelectorAll('.tab-btn');
    const views = {
        'reportView': document.getElementById('reportView'),
        'hotStoriesView': document.getElementById('hotStoriesView')
    };

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            Object.values(views).forEach(v => v.classList.add('hidden'));
            const targetViewId = btn.getAttribute('data-target');
            if(views[targetViewId]) {
                views[targetViewId].classList.remove('hidden');
            }
        });
    });

    // Hot Stories Feature
    const refreshFeedBtn = document.getElementById('refreshFeedBtn');
    const hotStoriesContainer = document.getElementById('hotStoriesContainer');
    let isFetchingStories = false;

    if (refreshFeedBtn && hotStoriesContainer) {
        refreshFeedBtn.addEventListener('click', async () => {
            if (isFetchingStories) return;
            isFetchingStories = true;
            refreshFeedBtn.textContent = "Fetching...";
            
            hotStoriesContainer.innerHTML = `
                <div class="loading-skeleton">
                    <div class="shimmer-line"></div>
                    <div class="shimmer-line"></div>
                    <div class="shimmer-line w-75"></div>
                    <br>
                    <div class="shimmer-line"></div>
                    <div class="shimmer-line w-50"></div>
                </div>
            `;

            try {
                const res = await fetch("http://127.0.0.1:8000/api/hot-stories");
                if (!res.ok) throw new Error("API failed");
                const data = await res.json();
                hotStoriesContainer.innerHTML = '<div class="markdown-body" style="animation: fadeIn 0.5s ease-out; line-height: 1.6;">' + marked.parse(data.feed) + '</div>';
            } catch (e) {
                console.error(e);
                hotStoriesContainer.innerHTML = `<div style="color: #ff6b6b; text-align: center; padding: 2rem;">Error fetching Hot Stories.</div>`;
            } finally {
                isFetchingStories = false;
                refreshFeedBtn.textContent = "Refresh Feed";
            }
        });
    }

});
