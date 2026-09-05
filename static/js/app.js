// StockSage AI — Client JavaScript Controller (Phase 7 & 9)

document.addEventListener('DOMContentLoaded', () => {

  // Global Evidence Inspector Modal Listener (Event Delegation)
  document.body.addEventListener('click', (e) => {
    const btn = e.target.closest('.btn-evidence');
    if (!btn) return;

    const rawData = btn.getAttribute('data-evidence');
    if (!rawData) return;

    try {
      const data = JSON.parse(rawData);
      openEvidenceModal(data);
    } catch (err) {
      console.error("Failed to parse evidence JSON:", err);
    }
  });

  function openEvidenceModal(data) {
    const modalOverlay = document.getElementById('evidence-modal-overlay');
    if (!modalOverlay) return;

    // Header Info
    const prName = document.getElementById('modal-product-name');
    const stName = document.getElementById('modal-store-name');
    const issueLabel = document.getElementById('modal-issue-label');
    const prioScore = document.getElementById('modal-priority-score');
    const recText = document.getElementById('modal-recommendation-text');

    if (prName) prName.textContent = data.product_name || 'Product Evidence';
    if (stName) stName.textContent = `${data.store_name || ''} (${data.category || ''})`;
    if (issueLabel) {
      issueLabel.textContent = data.issue_label || data.issue_type || 'Risk Issue';
      const badgeCls = data.issue_type === 'stockout_risk' ? 'badge-critical' : (data.issue_type === 'overstock' ? 'badge-high' : 'badge-warning');
      issueLabel.className = `badge ${badgeCls}`;
    }
    if (prioScore) prioScore.textContent = `${data.priority_score !== undefined ? data.priority_score : 0}/100`;
    if (recText) recText.textContent = data.recommendation || 'Operational review recommended.';

    // Metrics List
    const metricsContainer = document.getElementById('modal-metrics-container');
    if (metricsContainer) {
      metricsContainer.innerHTML = '';
      const ev = data.evidence || {};
      const metrics = ev.metrics || [];

      metrics.forEach(m => {
        const valStr = typeof m.value === 'number' ? m.value.toLocaleString() : (m.value !== null ? m.value : 'N/A');
        const unitStr = m.unit ? ` ${m.unit}` : '';
        const item = document.createElement('div');
        item.className = 'metric-row';
        item.innerHTML = `
          <span class="metric-label">${escapeHtml(m.label)}:</span>
          <strong class="metric-val">${escapeHtml(String(valStr))}${escapeHtml(unitStr)}</strong>
        `;
        metricsContainer.appendChild(item);
      });
    }

    // Formula & Calculation
    const formulaContainer = document.getElementById('modal-formula-container');
    if (formulaContainer) {
      const calc = (data.evidence && data.evidence.calculation) || {};
      formulaContainer.innerHTML = `
        <div style="font-size: 13px; color: var(--text-secondary);">
          <strong>Formula:</strong> <code>${escapeHtml(calc.formula || 'N/A')}</code><br>
          <span style="font-size: 12px; color: var(--text-muted);">${escapeHtml(calc.label || '')}</span>
        </div>
      `;
    }

    // Financial Impact
    const impactContainer = document.getElementById('modal-impact-container');
    if (impactContainer) {
      const imp = data.impact || {};
      const val = imp.value !== undefined ? imp.value : 0;
      const valFormatted = val ? `₹${val.toLocaleString('en-IN', {minimumFractionDigits: 2})}` : '₹0.00';
      impactContainer.innerHTML = `
        <div style="font-size: 14px; font-weight: 600; color: var(--accent-light);">
          ${escapeHtml(imp.label || 'Financial Impact')}: ${valFormatted}
        </div>
      `;
    }

    // Priority Score Breakdown
    const prioContainer = document.getElementById('modal-priority-container');
    if (prioContainer) {
      const prio = data.priority || {};
      const drivers = prio.drivers || [];
      if (drivers.length > 0) {
        prioContainer.innerHTML = `
          <div style="font-size: 12.5px; color: var(--text-muted);">
            <strong>Drivers:</strong> ${drivers.map(d => `<span class="chip-sm">${escapeHtml(d.factor)} (${d.impact})</span>`).join(' ')}
          </div>
        `;
      } else {
        prioContainer.innerHTML = `<div style="font-size: 12.5px; color: var(--text-muted);">Priority Score: ${data.priority_score || 0}/100 (${data.priority_label || 'Calculated'})</div>`;
      }
    }

    // Assumptions & Confidence
    const assumpContainer = document.getElementById('modal-assumptions-container');
    if (assumpContainer) {
      const assump = data.assumptions || (data.evidence && data.evidence.assumptions) || [];
      const conf = (data.evidence && data.evidence.confidence) || 'Medium';

      let assumpHtml = assump.map(a => `<li>${escapeHtml(a)}</li>`).join('');
      assumpContainer.innerHTML = `
        <div style="font-size: 12px; color: var(--text-muted);">
          <strong>Confidence Level:</strong> <span class="badge badge-info">${escapeHtml(conf)}</span>
          ${assump.length > 0 ? `<ul style="margin-top: 6px; padding-left: 18px;">${assumpHtml}</ul>` : ''}
        </div>
      `;
    }

    modalOverlay.classList.add('active');
  }

  // Modal Close Listeners
  const modalClose = document.getElementById('modal-close-btn');
  const modalOverlay = document.getElementById('evidence-modal-overlay');

  if (modalClose && modalOverlay) {
    modalClose.addEventListener('click', () => {
      modalOverlay.classList.remove('active');
    });

    modalOverlay.addEventListener('click', (e) => {
      if (e.target === modalOverlay) {
        modalOverlay.classList.remove('active');
      }
    });
  }

  // Phase 10 What-If Simulator Interactive Handler
  const runSimBtn = document.getElementById('run-sim-btn');
  const simResults = document.getElementById('sim-results');
  const simSlider = document.getElementById('sim-demand-slider');
  const simValDisplay = document.getElementById('sim-demand-val');
  const simPresetBtns = document.querySelectorAll('.sim-preset-btn');
  const simProductSelect = document.getElementById('sim-product-select');
  const simStoreSelect = document.getElementById('sim-store-select');
  const simStockInput = document.getElementById('sim-stock-input');

  if (simSlider && simValDisplay) {
    simSlider.addEventListener('input', () => {
      const val = parseFloat(simSlider.value);
      simValDisplay.textContent = `${val >= 0 ? '+' : ''}${val}%`;
    });
  }

  if (simPresetBtns && simSlider && simValDisplay) {
    simPresetBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        const val = btn.getAttribute('data-demand');
        if (val !== null) {
          simSlider.value = val;
          simValDisplay.textContent = `${parseFloat(val) >= 0 ? '+' : ''}${val}%`;
        }
      });
    });
  }

  if (runSimBtn && simResults) {
    runSimBtn.addEventListener('click', async () => {
      const productId = simProductSelect ? simProductSelect.value : null;
      const storeId = simStoreSelect ? simStoreSelect.value : null;
      const demandPct = simSlider ? parseFloat(simSlider.value) : 0.0;
      const stockAdj = simStockInput ? parseInt(simStockInput.value || 0, 10) : 0;

      if (!productId) {
        alert("Please select a target product to simulate.");
        if (simProductSelect) simProductSelect.focus();
        return;
      }

      runSimBtn.disabled = true;
      runSimBtn.textContent = '⏳ Simulating...';

      try {
        const response = await fetch('/api/simulate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            product_id: productId,
            store_id: storeId,
            demand_change_percent: demandPct,
            stock_change_units: stockAdj
          })
        });

        const data = await response.json();
        if (!data.success) {
          alert(`Simulation error: ${data.message || 'Failed'}`);
          return;
        }

        const sim = data.simulation || {};
        const b = sim.before || {};
        const a = sim.after || {};
        const c = sim.change || {};

        // Update UI elements
        const titleElem = document.getElementById('sim-res-product-title');
        const subElem = document.getElementById('sim-res-subtitle');
        const stBadge = document.getElementById('sim-res-store-badge');

        if (titleElem) titleElem.textContent = `Simulation: ${sim.product_name || 'Product'}`;
        if (subElem) subElem.textContent = `Demand Change: ${sim.demand_change_percent >= 0 ? '+' : ''}${sim.demand_change_percent}% | Stock Adj: ${sim.stock_change_units >= 0 ? '+' : ''}${sim.stock_change_units} units`;
        if (stBadge) stBadge.textContent = sim.store_name || 'All Stores';

        // Stock KPI
        const kpiStock = document.getElementById('sim-kpi-stock');
        const kpiStockDiff = document.getElementById('sim-kpi-stock-diff');
        if (kpiStock) kpiStock.textContent = `${b.stock} → ${a.stock} units`;
        if (kpiStockDiff) kpiStockDiff.textContent = `Stock Change: ${c.stock_change >= 0 ? '+' : ''}${c.stock_change} units`;

        // ADS KPI
        const kpiAds = document.getElementById('sim-kpi-ads');
        const kpiAdsDiff = document.getElementById('sim-kpi-ads-diff');
        if (kpiAds) kpiAds.textContent = `${b.daily_sales_velocity} → ${a.daily_sales_velocity} /day`;
        if (kpiAdsDiff) kpiAdsDiff.textContent = `Velocity Change: ${c.velocity_change >= 0 ? '+' : ''}${c.velocity_change} units/day`;

        // Days KPI
        const kpiDays = document.getElementById('sim-kpi-days');
        const bDaysStr = b.days_remaining !== null ? `${b.days_remaining} days` : 'N/A';
        const aDaysStr = a.days_remaining !== null ? `${a.days_remaining} days` : 'N/A';
        if (kpiDays) kpiDays.textContent = `${bDaysStr} → ${aDaysStr}`;

        // Risk Classification Badges
        const riskBeforeBadge = document.getElementById('sim-risk-before-badge');
        const riskAfterBadge = document.getElementById('sim-risk-after-badge');

        const getBadgeCls = (st) => st === 'critical' || st === 'stockout_risk' ? 'badge-critical' : (st === 'overstock' ? 'badge-high' : 'badge-healthy');

        if (riskBeforeBadge) {
          riskBeforeBadge.textContent = (b.risk_status || 'normal').toUpperCase();
          riskBeforeBadge.className = `badge ${getBadgeCls(b.risk_status)}`;
        }
        if (riskAfterBadge) {
          riskAfterBadge.textContent = (a.risk_status || 'normal').toUpperCase();
          riskAfterBadge.className = `badge ${getBadgeCls(a.risk_status)}`;
        }

        // Revenue at Risk
        const revRiskText = document.getElementById('sim-rev-risk-text');
        const revRiskDiff = document.getElementById('sim-rev-risk-diff');
        if (revRiskText) {
          revRiskText.textContent = `₹${(b.revenue_at_risk || 0).toLocaleString('en-IN', {minimumFractionDigits: 2})} → ₹${(a.revenue_at_risk || 0).toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
        }
        if (revRiskDiff) {
          const revDiffVal = c.revenue_at_risk_change || 0;
          revRiskDiff.textContent = `Change: ${revDiffVal >= 0 ? '+' : ''}₹${Math.abs(revDiffVal).toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
          revRiskDiff.style.color = revDiffVal > 0 ? 'var(--critical)' : (revDiffVal < 0 ? 'var(--healthy)' : 'var(--text-secondary)');
        }

        // Disclaimer
        const discText = document.getElementById('sim-disclaimer-text');
        if (discText) discText.textContent = sim.disclaimer || 'Scenario simulation only — not a forecast.';

        simResults.style.display = 'block';
        simResults.scrollIntoView({ behavior: 'smooth' });

      } catch (err) {
        console.error("Simulation request error:", err);
        alert("Failed to connect to simulation server.");
      } finally {
        runSimBtn.disabled = false;
        runSimBtn.textContent = '⚡ Run What-If Simulation';
      }
    });
  }

  // Copilot Interactive Chips & Real API Endpoint Handler
  const promptChips = document.querySelectorAll('.chip');
  const copilotInput = document.getElementById('copilot-input');
  const sendCopilotBtn = document.getElementById('send-copilot-btn');
  const chatHistory = document.getElementById('chat-history');

  if (promptChips && copilotInput) {
    promptChips.forEach(chip => {
      chip.addEventListener('click', () => {
        copilotInput.value = chip.textContent.trim();
        copilotInput.focus();
      });
    });
  }

  if (sendCopilotBtn && copilotInput && chatHistory) {
    const handleCopilotSend = async () => {
      const userText = copilotInput.value.trim();
      if (!userText) return;

      // 1. Append User Message
      const userMsgDiv = document.createElement('div');
      userMsgDiv.className = 'chat-message user';
      userMsgDiv.innerHTML = `
        <div class="chat-avatar user-av">M</div>
        <div class="chat-bubble">
          <p>${escapeHtml(userText)}</p>
        </div>
      `;
      chatHistory.appendChild(userMsgDiv);
      copilotInput.value = '';
      chatHistory.scrollTop = chatHistory.scrollHeight;

      // 2. Append Loading Placeholder
      const loadingDiv = document.createElement('div');
      loadingDiv.className = 'chat-message ai';
      loadingDiv.id = 'copilot-loading';
      loadingDiv.innerHTML = `
        <div class="chat-avatar ai-av">⚡</div>
        <div class="chat-bubble" style="color: var(--text-muted); font-style: italic;">
          <p>Evaluating retail grounding policies...</p>
        </div>
      `;
      chatHistory.appendChild(loadingDiv);
      chatHistory.scrollTop = chatHistory.scrollHeight;

      sendCopilotBtn.disabled = true;
      copilotInput.disabled = true;

      try {
        const response = await fetch('/api/copilot', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question: userText })
        });
        const resData = await response.json();

        const loadingElem = document.getElementById('copilot-loading');
        if (loadingElem) loadingElem.remove();

        // 3. Render Assistant Response
        const aiMsgDiv = document.createElement('div');
        aiMsgDiv.className = 'chat-message ai';

        // Check for Cannot-Answer / Grounding Refusal
        if (resData.success === false || resData.response_source === 'grounding_policy') {
          const statusBadgeText = resData.status === 'missing_data' ? '🚫 Data Unavailable' : (
            resData.status === 'missing_entity' ? '❓ Entity Needed' : (
              resData.status === 'ambiguous' ? '🔍 Ambiguous Match' : '🛡️ Grounding Refusal'
            )
          );

          let missingFieldsHtml = '';
          if (resData.missing_fields && Array.isArray(resData.missing_fields) && resData.missing_fields.length > 0) {
            missingFieldsHtml = `
              <div style="margin-top: 8px; font-size: 12px; color: var(--text-muted);">
                <strong>Unavailable Database Fields:</strong>
                <ul style="margin: 4px 0 0 16px; padding: 0;">
                  ${resData.missing_fields.map(f => `<li><code>${escapeHtml(f)}</code></li>`).join('')}
                </ul>
              </div>
            `;
          }

          let altChipsHtml = '';
          if (resData.available_alternatives && Array.isArray(resData.available_alternatives) && resData.available_alternatives.length > 0) {
            altChipsHtml = `
              <div style="margin-top: 12px; font-size: 12px; color: var(--text-secondary);">
                <strong>Suggested Alternatives:</strong>
                <div class="prompt-chips" style="margin-top: 6px;">
                  ${resData.available_alternatives.map(alt => `<div class="chip alt-chip">${escapeHtml(alt)}</div>`).join('')}
                </div>
              </div>
            `;
          }

          const answerTextFormatted = escapeHtml(resData.answer || 'Question cannot be answered.').replace(/\n/g, '<br>');

          aiMsgDiv.innerHTML = `
            <div class="chat-avatar ai-av" style="background: var(--warning);">🛡️</div>
            <div class="chat-bubble" style="max-width: 620px; border-left: 3px solid var(--warning);">
              <span class="badge badge-warning" style="font-size: 10px; float: right;">${statusBadgeText}</span>
              <div style="clear: both;"></div>
              <p style="margin-top: 4px; line-height: 1.5; font-weight: 500;">${answerTextFormatted}</p>
              ${missingFieldsHtml}
              ${altChipsHtml}
            </div>
          `;

          chatHistory.appendChild(aiMsgDiv);

          // Add click listeners to new alternative chips
          const newAltChips = aiMsgDiv.querySelectorAll('.alt-chip');
          newAltChips.forEach(chip => {
            chip.addEventListener('click', () => {
              copilotInput.value = chip.textContent.trim();
              copilotInput.focus();
            });
          });

        } else {
          // Standard Grounded Success Response
          let evidenceHtml = '';
          if (resData.evidence && Array.isArray(resData.evidence) && resData.evidence.length > 0) {
            evidenceHtml = resData.evidence.map(item => {
              const pr = item.product_name || 'Product';
              const cat = item.category ? `(${item.category})` : '';
              const st = item.store_name || '';
              const issueLabel = item.issue_label || item.issue_type || 'Issue';
              const badgeCls = item.issue_type === 'stockout_risk' ? 'badge-critical' : (item.issue_type === 'overstock' ? 'badge-high' : 'badge-warning');
              const score = item.priority_score !== undefined ? item.priority_score : 0;
              const recText = item.recommendation || '';
              const evidenceJsonAttr = escapeHtml(JSON.stringify(item));

              return `
                <div class="insight-card-mini" style="margin-top: 12px; background: rgba(0,0,0,0.25); border: 1px solid var(--border); padding: 12px; border-radius: 8px;">
                  <div class="insight-card-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <div>
                      <strong style="font-size: 14px; color: var(--text-primary);">${escapeHtml(pr)}</strong>
                      <span style="font-size: 11.5px; color: var(--text-muted); margin-left: 4px;">${escapeHtml(st)} ${escapeHtml(cat)}</span>
                    </div>
                    <span class="badge ${badgeCls}">${escapeHtml(issueLabel)}</span>
                  </div>
                  <div style="font-size: 12px; margin-bottom: 6px; color: var(--text-secondary);">
                    Priority: <strong style="color: var(--critical);">${score}/100</strong>
                  </div>
                  <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px;">${escapeHtml(recText)}</p>
                  <button class="btn btn-secondary btn-sm btn-evidence" data-evidence="${evidenceJsonAttr}">
                    Why this recommendation?
                  </button>
                </div>
              `;
            }).join('');
          }

          const sourceBadge = resData.generated_by_ai
            ? '<span class="badge badge-ai" style="font-size: 10px; float: right;">⚡ Grounded Gemini AI</span>'
            : '<span class="badge badge-info" style="font-size: 10px; float: right;">🛡️ Grounded Analytics</span>';

          const answerTextFormatted = escapeHtml(resData.answer || 'No answer generated.').replace(/\n/g, '<br>');

          aiMsgDiv.innerHTML = `
            <div class="chat-avatar ai-av">⚡</div>
            <div class="chat-bubble" style="max-width: 620px;">
              ${sourceBadge}
              <div style="clear: both;"></div>
              <p style="margin-top: 4px; line-height: 1.5;">${answerTextFormatted}</p>
              ${evidenceHtml}
            </div>
          `;
          chatHistory.appendChild(aiMsgDiv);
        }

        chatHistory.scrollTop = chatHistory.scrollHeight;

      } catch (err) {
        console.error("Copilot API Error:", err);
        const loadingElem = document.getElementById('copilot-loading');
        if (loadingElem) loadingElem.remove();

        const errDiv = document.createElement('div');
        errDiv.className = 'chat-message ai';
        errDiv.innerHTML = `
          <div class="chat-avatar ai-av">⚡</div>
          <div class="chat-bubble">
            <p style="color: var(--critical);">Error connecting to StockSage Copilot service. Please try again.</p>
          </div>
        `;
        chatHistory.appendChild(errDiv);
        chatHistory.scrollTop = chatHistory.scrollHeight;
      } finally {
        sendCopilotBtn.disabled = false;
        copilotInput.disabled = false;
        copilotInput.focus();
      }
    };

    sendCopilotBtn.addEventListener('click', handleCopilotSend);

    copilotInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleCopilotSend();
      }
    });
  }

  // Table Search Filter (Client Side)
  const searchInput = document.getElementById('table-search-input');
  if (searchInput) {
    searchInput.addEventListener('keyup', () => {
      const filter = searchInput.value.toLowerCase();
      const rows = document.querySelectorAll('.filterable-table tbody tr');
      rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(filter) ? '' : 'none';
      });
    });
  }
});

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
