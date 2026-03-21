import React, { useState, useEffect, useCallback, useRef } from 'react';
import './App.css';

const API = process.env.REACT_APP_BACKEND_URL || '';

// API with retry
const api = {
  async get(path, retries = 3) {
    for (let i = 0; i < retries; i++) {
      try {
        const res = await fetch(`${API}${path}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
      } catch (e) {
        if (i === retries - 1) throw e;
        await new Promise(r => setTimeout(r, 1000 * (i + 1)));
      }
    }
  },
  async post(path, body, retries = 3) {
    for (let i = 0; i < retries; i++) {
      try {
        const res = await fetch(`${API}${path}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
      } catch (e) {
        if (i === retries - 1) throw e;
        await new Promise(r => setTimeout(r, 1000 * (i + 1)));
      }
    }
  },
};

// Progress steps
const STEPS = [
  { key: 'init', label: 'Initializing', icon: '🚀' },
  { key: 'trends', label: 'Loading Trends', icon: '📊' },
  { key: 'ideas', label: 'Generating Ideas', icon: '💡' },
  { key: 'scoring', label: 'AI Scoring', icon: '🎯' },
  { key: 'script', label: 'Writing Script', icon: '📝' },
  { key: 'voice', label: 'AI Voice', icon: '🎙️' },
  { key: 'package', label: 'Packaging', icon: '📦' },
  { key: 'done', label: 'Complete', icon: '✅' },
];

function App() {
  // State
  const [view, setView] = useState('dashboard');
  const [systemStatus, setSystemStatus] = useState(null);
  const [trends, setTrends] = useState([]);
  const [trendStats, setTrendStats] = useState(null);
  const [vault, setVault] = useState([]);
  
  // Generation state
  const [prompt, setPrompt] = useState('');
  const [taskId, setTaskId] = useState(null);
  const [taskStatus, setTaskStatus] = useState(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  
  const pollRef = useRef(null);

  // Load initial data
  useEffect(() => {
    loadSystemStatus();
    loadTrends();
    loadVault();
    
    // Poll system status every 30s
    const interval = setInterval(loadSystemStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadSystemStatus = async () => {
    try {
      const data = await api.get('/api/health');
      setSystemStatus(data);
    } catch (e) {
      setSystemStatus({ status: 'offline' });
    }
  };

  const loadTrends = async () => {
    try {
      const data = await api.get('/api/trends');
      setTrends(data.trends || []);
      
      const stats = await api.get('/api/trends/stats');
      if (!stats.error) setTrendStats(stats);
    } catch (e) {}
  };

  const loadVault = async () => {
    try {
      const data = await api.get('/api/vault');
      setVault(data.videos || []);
    } catch (e) {}
  };

  // Fetch live trends
  const fetchTrends = async () => {
    try {
      await api.post('/api/trends/fetch', {});
      // Wait and reload
      setTimeout(loadTrends, 3000);
      setTimeout(loadTrends, 8000);
    } catch (e) {
      setError('Failed to fetch trends');
    }
  };

  // Get step index from status
  const getStepIndex = useCallback((status) => {
    if (!status?.step) return 0;
    const step = status.step.toLowerCase();
    if (step.includes('init')) return 0;
    if (step.includes('trend') || step.includes('load')) return 1;
    if (step.includes('generat') && step.includes('idea')) return 2;
    if (step.includes('scor')) return 3;
    if (step.includes('script') || step.includes('writ')) return 4;
    if (step.includes('voice') || step.includes('audio')) return 5;
    if (step.includes('packag') || step.includes('creat')) return 6;
    if (step.includes('complete') || step.includes('final')) return 7;
    return Math.floor((status.progress || 0) / 12.5);
  }, []);

  // Poll task status
  const pollTask = useCallback(async (id) => {
    try {
      const data = await api.get(`/api/task/${id}`);
      setTaskStatus(data);
      
      if (data.status === 'complete' && data.result) {
        setResult(data.result);
        setIsGenerating(false);
        setView('result');
        loadVault(); // Refresh vault
        if (pollRef.current) clearInterval(pollRef.current);
        return;
      }
      
      if (data.status === 'error') {
        setError(data.step || 'Generation failed');
        setIsGenerating(false);
        if (pollRef.current) clearInterval(pollRef.current);
        return;
      }
    } catch (e) {
      // Keep polling on error
    }
  }, []);

  // Start generation
  const startGeneration = async () => {
    if (isGenerating) return;
    
    setIsGenerating(true);
    setTaskStatus({ status: 'processing', progress: 0, step: 'Starting...' });
    setResult(null);
    setError('');
    setView('generate');

    try {
      const data = await api.post('/api/generate', { 
        prompt: prompt || 'viral trending content' 
      });
      
      if (data.task_id) {
        setTaskId(data.task_id);
        
        // Start polling every 1.5 seconds
        pollRef.current = setInterval(() => pollTask(data.task_id), 1500);
        
        // Initial poll
        setTimeout(() => pollTask(data.task_id), 500);
      } else {
        setError('Failed to start generation');
        setIsGenerating(false);
      }
    } catch (e) {
      setError('Connection failed. Please try again.');
      setIsGenerating(false);
    }
  };

  // Reset
  const reset = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    setView('dashboard');
    setResult(null);
    setTaskStatus(null);
    setTaskId(null);
    setError('');
    setPrompt('');
  };

  const stepIndex = taskStatus ? getStepIndex(taskStatus) : 0;

  return (
    <div className="factory" data-testid="app">
      {/* Header */}
      <header className="header">
        <div className="logo">
          <span className="logo-icon">⚡</span>
          <span className="logo-text">ViralForge</span>
          <span className="logo-badge">v3 CLOUD</span>
        </div>
        <div className="status-bar">
          <div className={`status-item ${systemStatus?.status === 'operational' ? 'online' : 'offline'}`}>
            <span className="status-dot" />
            <span>{systemStatus?.status === 'operational' ? 'ONLINE' : 'CONNECTING'}</span>
          </div>
          <div className="status-item">
            <span>☁️</span>
            <span>{systemStatus?.database || 'cloud'}</span>
          </div>
          <div className="status-item">
            <span>📊</span>
            <span>{trends.length} Trends</span>
          </div>
          <div className="status-item">
            <span>🎬</span>
            <span>{vault.length} Videos</span>
          </div>
        </div>
      </header>

      <div className="body">
        {/* Sidebar */}
        <nav className="sidebar">
          <button className={`nav-btn ${view === 'dashboard' ? 'active' : ''}`} onClick={() => setView('dashboard')}>
            <span>📊</span> Dashboard
          </button>
          <button className={`nav-btn ${view === 'generate' || view === 'result' ? 'active' : ''}`} onClick={() => result ? setView('result') : setView('generate')}>
            <span>🚀</span> Generate
          </button>
          <button className={`nav-btn ${view === 'vault' ? 'active' : ''}`} onClick={() => { setView('vault'); loadVault(); }}>
            <span>📦</span> Video Vault
          </button>
          
          <div className="nav-divider" />
          <div className="nav-label">CLOUD ENGINE</div>
          <div className="engine-stat">
            <span>AI</span>
            <span className="val">Gemini 2.0</span>
          </div>
          <div className="engine-stat">
            <span>Voice</span>
            <span className="val">OpenAI TTS</span>
          </div>
          <div className="engine-stat">
            <span>Storage</span>
            <span className="val">MongoDB</span>
          </div>
        </nav>

        {/* Main */}
        <main className="main">
          {/* Dashboard */}
          {view === 'dashboard' && (
            <div className="dashboard">
              <div className="page-header">
                <h1>🏭 Control Room</h1>
                <button className="btn-primary" onClick={fetchTrends}>
                  🔄 Fetch Live Trends
                </button>
              </div>

              {/* Stats */}
              {trendStats && (
                <div className="stats-grid">
                  <div className="stat-card">
                    <div className="stat-label">Total Trends</div>
                    <div className="stat-value">{trendStats.total_trends || 0}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Avg Score</div>
                    <div className="stat-value">{trendStats.avg_score || 0}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Top Hook</div>
                    <div className="stat-value accent">{trendStats.top_hook?.replace('_', ' ') || '—'}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Videos Created</div>
                    <div className="stat-value">{vault.length}</div>
                  </div>
                </div>
              )}

              {/* Quick Generate */}
              <div className="quick-gen">
                <h2>⚡ Magic Generation</h2>
                <p>One click: Trend Intelligence → AI Ideas → Script → Voice → Video Package</p>
                <div className="gen-row">
                  <input
                    type="text"
                    placeholder="Enter niche (or leave empty for auto)"
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    className="gen-input"
                  />
                  <button className="btn-magic" onClick={startGeneration} disabled={isGenerating}>
                    ✨ GENERATE
                  </button>
                </div>
              </div>

              {/* Trends */}
              <div className="trends-section">
                <h2>📈 Trend Intelligence ({trends.length})</h2>
                {trends.length > 0 ? (
                  <div className="trends-table">
                    <div className="table-head">
                      <span className="col-rank">#</span>
                      <span className="col-title">Title</span>
                      <span className="col-hook">Hook Type</span>
                      <span className="col-score">Score</span>
                    </div>
                    {trends.slice(0, 12).map((t, i) => (
                      <div key={t.id} className="table-row">
                        <span className="col-rank">{i + 1}</span>
                        <span className="col-title">{t.title}</span>
                        <span className="col-hook">
                          <span className={`badge ${t.analysis?.hook_type || 'neutral'}`}>
                            {t.analysis?.hook_type?.replace('_', ' ') || 'neutral'}
                          </span>
                        </span>
                        <span className="col-score">
                          <span className={`score ${t.viral_score >= 60 ? 'high' : t.viral_score >= 40 ? 'mid' : 'low'}`}>
                            {t.viral_score}
                          </span>
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty">
                    <span>📊</span>
                    <p>No trends loaded. Click "Fetch Live Trends" to start.</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Generate View */}
          {view === 'generate' && (
            <div className="generate-view">
              <h1>🎬 Video Factory</h1>
              <p className="subtitle">Cloud-powered pipeline: Trends → Ideas → Script → Voice → Package</p>

              {/* Progress */}
              {(isGenerating || taskStatus) && (
                <div className="progress-panel">
                  <div className="progress-steps">
                    {STEPS.map((s, i) => (
                      <div key={s.key} className={`step ${i < stepIndex ? 'done' : i === stepIndex ? 'active' : ''}`}>
                        <div className="step-icon">{i < stepIndex ? '✓' : s.icon}</div>
                        <div className="step-label">{s.label}</div>
                      </div>
                    ))}
                  </div>
                  
                  <div className="progress-wrap">
                    <div className="progress-bar">
                      <div className="progress-fill" style={{ width: `${taskStatus?.progress || 0}%` }} />
                    </div>
                    <div className="progress-info">
                      <span>{taskStatus?.step || 'Starting...'}</span>
                      <span className="pct">{taskStatus?.progress || 0}%</span>
                    </div>
                  </div>
                  
                  {taskId && (
                    <div className="task-id">
                      Task ID: <code>{taskId}</code>
                      <span className="hint">(You can close this page - processing continues in cloud)</span>
                    </div>
                  )}
                </div>
              )}

              {/* Error */}
              {error && (
                <div className="error-panel">
                  <span>⚠️ {error}</span>
                  <button onClick={startGeneration}>Retry</button>
                </div>
              )}

              {/* Start Panel */}
              {!isGenerating && !taskStatus && (
                <div className="start-panel">
                  <div className="input-group">
                    <label>Niche / Topic</label>
                    <input
                      type="text"
                      placeholder="e.g., fitness motivation, passive income..."
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                      onKeyPress={(e) => e.key === 'Enter' && startGeneration()}
                    />
                  </div>
                  <button className="btn-generate" onClick={startGeneration}>
                    🚀 Start Generation
                  </button>
                  <p className="hint">Leave empty for auto-selection based on trending topics</p>
                </div>
              )}
            </div>
          )}

          {/* Result View */}
          {view === 'result' && result && (
            <div className="result-view">
              <div className="result-header">
                <h1>✅ Generation Complete!</h1>
                <button className="btn-new" onClick={reset}>+ New Video</button>
              </div>

              <div className="result-grid">
                {/* Winner Card */}
                <div className="winner-card">
                  <div className="card-head">
                    <span>🏆</span>
                    <span>Selected Idea</span>
                    <span className="score-badge">{result.winner?.final_score}/100</span>
                  </div>
                  <h2>{result.winner?.title}</h2>
                  <p className="hook">"{result.winner?.hook}"</p>
                  <p className="concept">{result.winner?.concept}</p>
                  
                  <div className="scores">
                    {Object.entries(result.winner?.scores || {}).map(([key, val]) => (
                      <div key={key} className="score-item">
                        <span>{key.replace('_', ' ')}</span>
                        <span>{val}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Script Card */}
                <div className="script-card">
                  <div className="card-head">
                    <span>📝</span>
                    <span>Script</span>
                    <span>{result.script?.duration || 30}s</span>
                  </div>
                  <div className="scenes">
                    {result.script?.scenes?.map((scene, i) => (
                      <div key={i} className={`scene phase-${scene.phase}`}>
                        <div className="scene-head">
                          <span className="phase">{scene.phase}</span>
                          <span className="time">{scene.end - scene.start}s</span>
                        </div>
                        <p className="spoken">{scene.spoken}</p>
                        <p className="caption">📺 {scene.caption}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Metadata Card */}
                <div className="meta-card">
                  <div className="card-head">
                    <span>📦</span>
                    <span>Export Package</span>
                  </div>
                  
                  <div className="meta-field">
                    <label>Title</label>
                    <input value={result.metadata?.title || ''} readOnly />
                  </div>
                  
                  <div className="meta-field">
                    <label>Description</label>
                    <textarea value={result.metadata?.description || ''} readOnly rows={3} />
                  </div>
                  
                  <div className="meta-field">
                    <label>Hashtags</label>
                    <div className="tags">
                      {(result.metadata?.hashtags || []).map((tag, i) => (
                        <span key={i} className="tag">{tag}</span>
                      ))}
                    </div>
                  </div>
                  
                  <button 
                    className="btn-copy"
                    onClick={() => {
                      const text = `${result.metadata?.title || ''}\n\n${result.metadata?.description || ''}\n\n${(result.metadata?.hashtags || []).join(' ')}`;
                      navigator.clipboard.writeText(text);
                    }}
                  >
                    📋 Copy All
                  </button>
                </div>
              </div>

              {/* All Ideas */}
              {result.all_ideas?.length > 1 && (
                <div className="all-ideas">
                  <h2>All 10 Ideas (Ranked)</h2>
                  <div className="ideas-grid">
                    {result.all_ideas.map((idea, i) => (
                      <div key={i} className={`idea-card ${i === 0 ? 'winner' : ''}`}>
                        <div className="idea-rank">#{i + 1}</div>
                        <div className="idea-score">{idea.final_score}</div>
                        <h4>{idea.title}</h4>
                        <p>"{idea.hook}"</p>
                        <span className={`badge ${idea.hook_type}`}>{idea.hook_type?.replace('_', ' ')}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Video Vault */}
          {view === 'vault' && (
            <div className="vault-view">
              <div className="page-header">
                <h1>📦 Video Vault</h1>
                <button className="btn-secondary" onClick={loadVault}>🔄 Refresh</button>
              </div>

              {vault.length > 0 ? (
                <div className="vault-grid">
                  {vault.map((v, i) => (
                    <div key={v.task_id} className="vault-card">
                      <div className="vault-header">
                        <span className="vault-num">#{i + 1}</span>
                        <span className="vault-score">{v.score}</span>
                      </div>
                      <h3>{v.title}</h3>
                      <p className="vault-hook">"{v.hook}"</p>
                      <div className="vault-meta">
                        <span>⏱️ {v.duration}s</span>
                        <span>📅 {new Date(v.created_at).toLocaleDateString()}</span>
                      </div>
                      <div className="vault-tags">
                        {(v.hashtags || []).slice(0, 4).map((tag, j) => (
                          <span key={j} className="tag">{tag}</span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty">
                  <span>📦</span>
                  <p>No videos generated yet. Click "Generate" to create your first video!</p>
                </div>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

export default App;
