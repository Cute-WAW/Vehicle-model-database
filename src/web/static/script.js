// 车型库匹配调试工具 - 前端脚本

// 页面加载时检查服务状态
document.addEventListener('DOMContentLoaded', () => {
    checkHealth();
    
    // 回车键触发匹配
    document.getElementById('queryInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            doMatch();
        }
    });
});

// 检查服务健康状态
async function checkHealth() {
    try {
        const response = await fetch('/api/health');
        const data = await response.json();
        document.getElementById('statusIndicator').textContent = '🟢 就绪';
        document.getElementById('indexSize').textContent = data.index_size.toLocaleString() + ' 条';
    } catch (error) {
        document.getElementById('statusIndicator').textContent = '🔴 离线';
        console.error('Health check failed:', error);
    }
}

// 填充示例
function fillExample(text) {
    document.getElementById('queryInput').value = text;
    doMatch();
}

// 执行匹配
async function doMatch() {
    const query = document.getElementById('queryInput').value.trim();
    if (!query) {
        alert('请输入车辆名称');
        return;
    }
    
    const topK = parseInt(document.getElementById('topK').value) || 5;
    const minScore = parseFloat(document.getElementById('minScore').value) || 150;
    
    // 显示加载状态
    document.getElementById('matchBtn').innerHTML = '<span class="loading"></span>';
    document.getElementById('entitiesResult').innerHTML = '<p class="placeholder">识别中...</p>';
    document.getElementById('processResult').innerHTML = '<p class="placeholder">处理中...</p>';
    document.getElementById('matchesResult').innerHTML = '<p class="placeholder">匹配中...</p>';
    
    try {
        const response = await fetch('/api/match', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, top_k: topK, min_score: minScore })
        });
        
        const result = await response.json();
        displayResult(result);
        
    } catch (error) {
        console.error('Match failed:', error);
        document.getElementById('matchesResult').innerHTML = 
            '<p style="color: var(--error);">匹配失败: ' + error.message + '</p>';
    } finally {
        document.getElementById('matchBtn').textContent = '匹配';
    }
}

// 显示结果
function displayResult(result) {
    // 显示实体识别结果
    displayEntities(result.extracted_entities);
    
    // 显示匹配过程
    displayProcess(result.debug);
    
    // 显示匹配结果
    displayMatches(result.matches);
    
    // 更新处理时间
    document.getElementById('processTime').textContent = 
        result.debug.processing_time_ms.toFixed(2) + ' ms';
}

// 显示实体识别结果
function displayEntities(entities) {
    const container = document.getElementById('entitiesResult');
    
    const entityDefs = [
        { key: 'brand', label: '品牌', icon: '🏷️' },
        { key: 'series', label: '车系', icon: '🚗' },
        { key: 'year', label: '年款', icon: '📅' },
        { key: 'displacement', label: '排量', icon: '⛽' },
        { key: 'range_km', label: '续航', icon: '🔋' },
        { key: 'transmission', label: '档位', icon: '⚙️' },
        { key: 'drive', label: '驱动', icon: '🛞' },
        { key: 'trim', label: '版式', icon: '✨' },
        { key: 'vehicle_type', label: '类型', icon: '🔌' }
    ];
    
    let html = '<div class="entities-list">';
    
    for (const def of entityDefs) {
        const value = entities[def.key];
        const isMatched = value !== null && value !== undefined && value !== '未知';
        
        html += `
            <span class="entity-tag ${isMatched ? 'matched' : 'unmatched'}">
                ${def.icon}
                <span class="entity-name">${def.label}:</span>
                <span class="entity-value">${isMatched ? value : '-'}</span>
            </span>
        `;
    }
    
    html += '</div>';
    html += `<p style="margin-top: 15px; font-size: 13px; color: var(--text-secondary);">
        置信度: <strong style="color: var(--accent)">${(entities.confidence * 100).toFixed(0)}%</strong>
    </p>`;
    
    container.innerHTML = html;
}

// 显示匹配过程
function displayProcess(debug) {
    const container = document.getElementById('processResult');
    
    const steps = [
        { label: '品牌过滤后', value: debug.candidates_after_brand },
        { label: '车系过滤后', value: debug.candidates_after_series },
        { label: '年款过滤后', value: debug.candidates_after_year || '-' },
        { label: '最终结果', value: debug.final_candidates }
    ];
    
    let html = '';
    for (const step of steps) {
        html += `
            <div class="process-step">
                <span class="process-label">${step.label}</span>
                <span class="process-value">${typeof step.value === 'number' ? step.value.toLocaleString() : step.value}</span>
            </div>
        `;
    }
    
    html += `
        <div class="process-step" style="margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border);">
            <span class="process-label">处理时间</span>
            <span class="process-value">${debug.processing_time_ms.toFixed(2)} ms</span>
        </div>
    `;
    
    container.innerHTML = html;
}

// 显示匹配结果
function displayMatches(matches) {
    const container = document.getElementById('matchesResult');
    const countSpan = document.getElementById('matchCount');
    
    countSpan.textContent = `(${matches.length} 个)`;
    
    if (matches.length === 0) {
        container.innerHTML = '<p class="placeholder">未找到匹配结果，请尝试调整阈值或输入更多信息</p>';
        return;
    }
    
    let html = '';
    matches.forEach((match, index) => {
        const confidencePercent = (match.confidence * 100).toFixed(0);
        
        html += `
            <div class="match-item">
                <div class="match-header">
                    <span class="match-rank">#${index + 1}</span>
                    <div class="match-score">
                        <span class="score-badge score">分数: ${match.score}</span>
                        <span class="score-badge confidence">置信度: ${confidencePercent}%</span>
                    </div>
                </div>
                <div class="match-info">
                    <div class="match-level-id">${match.level_id}</div>
                    <div class="match-name">
                        ${match.vehicle_info.brand} ${match.vehicle_info.series} 
                        ${match.vehicle_info.year}款 ${match.vehicle_info.sales_name}
                    </div>
                </div>
                <div class="match-entities">
                    ${match.matched_entities.map(e => `<span class="matched-entity">✓ ${e}</span>`).join('')}
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

// 应用配置
async function applyConfig() {
    const minScore = parseFloat(document.getElementById('minScore').value);
    const topK = parseInt(document.getElementById('topK').value);
    
    try {
        await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ min_score: minScore })
        });
        
        alert('配置已应用');
        
        // 重新匹配
        const query = document.getElementById('queryInput').value.trim();
        if (query) {
            doMatch();
        }
    } catch (error) {
        alert('配置更新失败: ' + error.message);
    }
}
