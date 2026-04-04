// AlphaV-7 Live Dashboard Logic
// Uses 2-second AJAX polling to update the UI without WebSockets.

const formatCurrency = (num) => '₹' + Number(num).toLocaleString('en-IN');

function updateDashboard() {
    // 1. Fetch Status (Header, Screener, Positions)
    fetch('/status')
        .then(res => res.json())
        .then(data => {
            document.getElementById('dash-status').innerText = 'LIVE / ' + data.status.toUpperCase();
            document.getElementById('dash-activity').innerText = data.current_action;
            document.getElementById('dash-capital').innerText = formatCurrency(data.capital);
            
            const pnlColor = data.realized_pnl >= 0 ? 'accent-green' : 'accent-red';
            const pnlEl = document.getElementById('dash-pnl');
            pnlEl.innerText = formatCurrency(data.realized_pnl);
            pnlEl.className = 'val ' + pnlColor;

            // Update Positions
            const posList = document.getElementById('positions-list');
            if(data.open_positions === 0) {
                // If it's 0 length but the state says 0 (Wait, data.open_positions is an integer in /status? No, wait! Let me check app.py)
                // Ah, app.py /status returns open_positions as an INT (len). I need the ACTUAL list for the right panel!
                // So I must fetch /positions too.
            }
            
            // Update Screener List
            const scrList = document.getElementById('screener-list');
            if(data.last_screen_result && data.last_screen_result.top_stocks) {
                scrList.innerHTML = '';
                data.last_screen_result.top_stocks.forEach(stock => {
                    scrList.innerHTML += `
                        <div class="list-item">
                            <div>
                                <div class="list-item-ticker">${stock.ticker}</div>
                                <div class="list-item-reason">${stock.reason}</div>
                            </div>
                            <div class="text-dim">Score: ${stock.score.toFixed(1)}</div>
                        </div>`;
                });
            }
        }).catch(err => console.error(err));

    // 2. Fetch Actual Open Positions List
    fetch('/positions')
        .then(res => res.json())
        .then(data => {
            const posList = document.getElementById('positions-list');
            if(!data.open_positions || data.open_positions.length === 0) {
                posList.innerHTML = '<div class="empty-state">No open positions.</div>';
            } else {
                posList.innerHTML = '';
                data.open_positions.forEach(pos => {
                    const colorClass = pos.action === 'BUY' ? 'green-border' : 'red-border';
                    const colorText = pos.action === 'BUY' ? 'accent-green' : 'accent-red';
                    posList.innerHTML += `
                        <div class="list-item ${colorClass}">
                            <div>
                                <div class="list-item-ticker">${pos.ticker} <span class="${colorText}">[${pos.action}]</span></div>
                                <div class="list-item-reason">Qty: ${pos.quantity} | Entry: ₹${pos.entry_price}</div>
                            </div>
                        </div>`;
                });
            }
        }).catch(e => console.error(e));

    // 3. Fetch Terminal Logs
    fetch('/api/logs')
        .then(res => res.json())
        .then(data => {
            const terminal = document.getElementById('terminal-content');
            if(data.logs && data.logs.length > 0) {
                let html = '';
                data.logs.forEach(line => {
                    // Simple color coding
                    let colorClass = 'text-dim';
                    if (line.includes('[Groq')) colorClass = 'accent-blue';
                    else if (line.includes('[Claude')) colorClass = 'accent-green';
                    else if (line.includes('EXECUTING') || line.includes('Trade executed')) colorClass = 'accent-green';
                    else if (line.includes('error') || line.includes('failed') || line.includes('🛑')) colorClass = 'accent-red';
                    
                    html += `<div class="log-line ${colorClass}">${line}</div>`;
                });
                terminal.innerHTML = html;
                terminal.scrollTop = terminal.scrollHeight; // Auto scroll to bottom
            }
        }).catch(e => console.error(e));

    // 4. Fetch Brain Activity
    fetch('/api/brain')
        .then(res => res.json())
        .then(data => {
            const brainEl = document.getElementById('brain-content');
            if(data.latest_scan && data.latest_scan.length > 0) {
                // Focus on the most recently analyzed stock
                const latest = data.latest_scan[data.latest_scan.length - 1];
                
                let groqSummary = "Waiting for Groq...";
                if(latest.groq_analysis) {
                    groqSummary = JSON.stringify(latest.groq_analysis, null, 2);
                }

                let claudeStrategy = "Waiting for Claude Strategist...";
                if(latest.claude_strategy) {
                    claudeStrategy = `Decision: ${latest.claude_strategy.decision}
Conviction: ${latest.claude_strategy.conviction}/10
Reasoning: ${latest.claude_strategy.reasoning}
Challenges: ${latest.claude_strategy.challenges_to_analyst || 'None'}`;
                }

                let consensus = "Waiting for CIO Consensus...";
                if(latest.consensus) {
                    consensus = `Final: ${latest.consensus.final_decision} (Conviction: ${latest.consensus.final_conviction}/10)
Execute Trade: ${latest.consensus.execute_trade}
Entry: ₹${latest.consensus.entry_price} | SL: ₹${latest.consensus.stop_loss} | Target: ₹${latest.consensus.target}
Rationale: ${latest.consensus.rationale}`;
                }

                brainEl.innerHTML = `
                    <div class="card">
                        <div class="card-title">Currently Analyzing</div>
                        <h2>${latest.ticker}</h2>
                        <div class="text-dim mt-4">Scan Time: ${new Date(latest.timestamp).toLocaleTimeString()}</div>
                    </div>
                    
                    <div class="card">
                        <div class="card-title">Data Analyst (Groq llama-3.3-70b)</div>
                        <div class="json-block">${groqSummary}</div>
                    </div>

                    <div class="card">
                        <div class="card-title">Strategist (Claude 3.5 Haiku)</div>
                        <div class="json-block" style="color:var(--accent-blue)">${claudeStrategy}</div>
                    </div>

                    <div class="card">
                        <div class="card-title">CIO Consensus (Claude 3.5 Haiku)</div>
                        <div class="json-block" style="color:${latest.consensus && latest.consensus.execute_trade ? 'var(--accent-green)' : 'var(--text-dim)'}">${consensus}</div>
                    </div>
                `;
            } else {
                 brainEl.innerHTML = '<div class="empty-state">Waiting for next stock scan payload...</div>';
            }
        }).catch(e => console.error(e));
}

// Initial Call
updateDashboard();

// Poll every 2 seconds
setInterval(updateDashboard, 2000);
