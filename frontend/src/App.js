import React, { useState, useEffect, useCallback } from 'react';
import './App.css';

const API_BASE = process.env.REACT_APP_BACKEND_URL || '';

// API Functions
const api = {
  async get(path) {
    try {
      const res = await fetch(`${API_BASE}${path}`);
      const data = await res.json();
      return { ok: res.ok, data };
    } catch (e) {
      return { ok: false, error: e.message };
    }
  },
  async post(path, body) {
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      return { ok: res.ok, data };
    } catch (e) {
      return { ok: false, error: e.message };
    }
  },
};

// Toast Component
function Toast({ message, type, onClose }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 3500);
    return () => clearTimeout(timer);
  }, [onClose]);

  return (
    <div className={`toast toast-${type}`} data-testid="toast">
      {type === 'success' && '✓ '}
      {type === 'error' && '✗ '}
      {type === 'info' && '→ '}
      {message}
    </div>
  );
}

// Stat Card Component
function StatCard({ label, value, color }) {
  return (
    <div className="stat-card" data-testid={`stat-${label.toLowerCase()}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={{ color }}>{value}</div>
    </div>
  );
}

// Score Ring Component
function ScoreRing({ score, size = 56 }) {
  const radius = (size - 10) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference * (1 - score / 100);
  const color = score >= 75 ? '#3dd68c' : score >= 50 ? '#f5a623' : '#e05c5c';

  return (
    <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="var(--bg-tertiary)"
        strokeWidth="5"
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth="5"
        strokeDasharray={circumference}
        strokeDashoffset={strokeDashoffset}
        strokeLinecap="round"
        style={{ transition: 'stroke-dashoffset 0.8s ease' }}
      />
      <text
        x={size / 2}
        y={size / 2}
        dominantBaseline="middle"
        textAnchor="middle"
        fill={color}
        fontSize={size * 0.22}
        fontWeight="bold"
        fontFamily="var(--font-mono)"
        style={{ transform: `rotate(90deg)`, transformOrigin: `${size / 2}px ${size / 2}px` }}
      >
        {score}
      </text>
    </svg>
  );
}

// Tag Component
function Tag({ label, color = 'var(--accent)' }) {
  return (
    <span className="tag" style={{ color, borderColor: `${color}30`, background: `${color}12` }}>
      {label}
    </span>
  );
}

// Progress Bar Component
function ProgressBar({ progress, message }) {
  return (
    <div className="progress-container" data-testid="progress-bar">
      <div className="progress-message">{message || `${progress}%`}</div>
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>
    </div>
  );
}

// Main App Component
function App() {
  const [page, setPage] = useState('dashboard');
  const [toasts, setToasts] = useState([]);
  const [loading, setLoading] = useState(false);
  
  // Data states
  const [trends, setTrends] = useState([]);
  const [patterns, setPatterns] = useState({});
  const [stats, setStats] = useState({});
  const [fetchStatus, setFetchStatus] = useState('idle');
  const [hookFilter, setHookFilter] = useState('');
  
  // Generation states
  const [niche, setNiche] = useState('general');
  const [ideas, setIdeas] = useState([]);
  const [winner, setWinner] = useState(null);
  const [decision, setDecision] = useState(null);
  const [script, setScript] = useState(null);
  const [scriptId, setScriptId] = useState('');
  const [genTab, setGenTab] = useState('ideas');
  
  // Video states
  const [videos, setVideos] = useState([]);
  const [palette, setPalette] = useState('amber');
  const [videoProgress, setVideoProgress] = useState(null);
  const [buildingVideo, setBuildingVideo] = useState(false);

  // Toast helper
  const showToast = useCallback((message, type = 'info') => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message, type }]);
  }, []);

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  // Load initial data
  useEffect(() => {
    loadStats();
    loadTrends();
    loadVideos();
  }, []);

  const loadStats = async () => {
    const res = await api.get('/api/stats');
    if (res.ok) setStats(res.data);
  };

  const loadTrends = async () => {
    const res = await api.get('/api/trends?limit=60');
    if (res.ok) {
      setTrends(res.data.trends || []);
      setFetchStatus(res.data.status || 'idle');
    }
    const pRes = await api.get('/api/trends/patterns');
    if (pRes.ok && !pRes.data.error) setPatterns(pRes.data);
  };

  const loadVideos = async () => {
    const res = await api.get('/api/videos');
    if (res.ok) setVideos(res.data.videos || []);
  };

  // Fetch live trends
  const fetchTrends = async (force = false) => {
    setLoading(true);
    setFetchStatus('fetching');
    showToast('Fetching live trends from YouTube...', 'info');
    
    const res = await api.post('/api/trends/fetch', { force });
    if (!res.ok) {
      showToast('Fetch failed: ' + res.error, 'error');
      setFetchStatus('error');
      setLoading(false);
      return;
    }
    
    // Poll for completion
    const poll = setInterval(async () => {
      const health = await api.get('/api/health');
      if (health.data?.fetch_status === 'done') {
        clearInterval(poll);
        await loadTrends();
        await loadStats();
        setFetchStatus('done');
        showToast('Trends loaded successfully!', 'success');
        setLoading(false);
      } else if (health.data?.fetch_status?.includes('error')) {
        clearInterval(poll);
        setFetchStatus('error');
        showToast('Fetch failed', 'error');
        setLoading(false);
      }
    }, 2000);
    
    setTimeout(() => clearInterval(poll), 60000);
  };

  // Generate content
  const runGeneration = async () => {
    if (!niche) return;
    
    setLoading(true);
    setIdeas([]);
    setWinner(null);
    setDecision(null);
    setScript(null);
    showToast('Running AI Decision Engine...', 'info');
    
    const res = await api.post('/api/generate', { niche });
    setLoading(false);
    
    if (!res.ok) {
      showToast('Generation failed: ' + (res.data?.detail || res.error), 'error');
      return;
    }
    
    const d = res.data;
    setIdeas(d.options || []);
    setWinner(d.winner);
    setDecision(d.decision);
    setScript(d.script);
    setScriptId(d.script_id || '');
    await loadStats();
    
    showToast(`Generated ${d.options?.length || 0} ideas, winner selected!`, 'success');
    setGenTab('script');
  };

  // Build video
  const buildVideo = async () => {
    if (!script) {
      showToast('Generate a script first', 'error');
      return;
    }
    
    setBuildingVideo(true);
    setVideoProgress({ progress: 0, message: 'Starting...' });
    showToast('Building video with AI voice...', 'info');
    
    const res = await api.post('/api/video/generate', {
      script_id: scriptId,
      script,
      palette,
    });
    
    if (!res.ok) {
      showToast('Video build failed', 'error');
      setBuildingVideo(false);
      setVideoProgress(null);
      return;
    }
    
    const videoId = res.data.video_id;
    
    // Poll progress
    const poll = setInterval(async () => {
      const status = await api.get(`/api/video/status/${videoId}`);
      if (status.ok) {
        const d = status.data;
        setVideoProgress({ progress: d.progress || 0, message: d.message || 'Building...' });
        
        if (d.status === 'done' || d.video_ready) {
          clearInterval(poll);
          setBuildingVideo(false);
          setVideoProgress(null);
          showToast('Video ready! Check the Videos tab', 'success');
          loadVideos();
          loadStats();
        } else if (d.status === 'failed' || d.status === 'error') {
          clearInterval(poll);
          setBuildingVideo(false);
          setVideoProgress(null);
          showToast('Video generation failed: ' + (d.message || ''), 'error');
        }
      }
    }, 2000);
    
    setTimeout(() => clearInterval(poll), 300000);
  };

  // Filter trends
  const filteredTrends = hookFilter
    ? trends.filter(t => t.analysis?.hook_type === hookFilter)
    : trends;

  const hookColors = {
    curiosity_gap: '#f5a623',
    pattern_interrupt: '#ff7043',
    fear_hook: '#ef5350',
    number_hook: '#66bb6a',
    transformation: '#ab47bc',
    question_hook: '#42a5f5',
    list_format: '#ec407a',
    neutral: '#78909c',
  };

  return (
    <div className="app" data-testid="app">
      {/* Toast Container */}
      <div className="toast-container">
        {toasts.map(t => (
          <Toast key={t.id} message={t.message} type={t.type} onClose={() => removeToast(t.id)} />
        ))}
      </div>

      {/* Header */}
      <header className="header" data-testid="header">
        <div className="logo">
          <div className="logo-icon">⚡</div>
          <span>VIRAL<em>FORGE</em></span>
          <span className="version">v3</span>
        </div>
        <div className="header-right">
          <span className={`status-indicator ${fetchStatus}`}>
            <span className="status-dot"></span>
            {fetchStatus === 'fetching' ? 'LOADING' : fetchStatus === 'done' ? 'READY' : 'IDLE'}
          </span>
        </div>
      </header>

      <div className="layout">
        {/* Sidebar */}
        <nav className="sidebar" data-testid="sidebar">
          <div className="nav-section">Main</div>
          <button
            className={`nav-btn ${page === 'dashboard' ? 'active' : ''}`}
            onClick={() => setPage('dashboard')}
            data-testid="nav-dashboard"
          >
            <span className="nav-icon">◈</span> Dashboard
          </button>
          <button
            className={`nav-btn ${page === 'trends' ? 'active' : ''}`}
            onClick={() => setPage('trends')}
            data-testid="nav-trends"
          >
            <span className="nav-icon">↑</span> Trends
          </button>
          <button
            className={`nav-btn ${page === 'generate' ? 'active' : ''}`}
            onClick={() => setPage('generate')}
            data-testid="nav-generate"
          >
            <span className="nav-icon">✦</span> Generate
          </button>
          <button
            className={`nav-btn ${page === 'videos' ? 'active' : ''}`}
            onClick={() => { setPage('videos'); loadVideos(); }}
            data-testid="nav-videos"
          >
            <span className="nav-icon">▶</span> Videos
          </button>
        </nav>

        {/* Main Content */}
        <main className="main">
          {/* Dashboard */}
          {page === 'dashboard' && (
            <div className="page" data-testid="page-dashboard">
              <div className="page-header">
                <div>
                  <h1 className="page-title">Trend Intelligence</h1>
                  <p className="page-subtitle">AI-powered viral content generation · Full video pipeline</p>
                </div>
                <button
                  className="btn btn-primary"
                  onClick={() => fetchTrends()}
                  disabled={loading}
                  data-testid="fetch-trends-btn"
                >
                  {loading ? '⟳ Loading...' : '⚡ Fetch Live Trends'}
                </button>
              </div>

              <div className="stats-grid">
                <StatCard label="Trends" value={stats.trends_count || 0} color="var(--accent)" />
                <StatCard label="Scripts" value={stats.scripts_count || 0} color="#3dd68c" />
                <StatCard label="Videos" value={stats.videos_count || 0} color="#5c9de0" />
                <StatCard label="Avg Score" value={stats.avg_score ? `${stats.avg_score}/100` : '—'} color="var(--accent)" />
              </div>

              <div className="grid-2">
                <div className="card">
                  <div className="card-header">Hook Distribution</div>
                  {patterns.hook_dist ? (
                    <div className="bar-chart">
                      {Object.entries(patterns.hook_dist)
                        .sort((a, b) => b[1] - a[1])
                        .map(([hook, count]) => (
                          <div key={hook} className="bar-row">
                            <div className="bar-meta">
                              <span style={{ color: hookColors[hook] || 'var(--text-secondary)' }}>
                                {hook.replace(/_/g, ' ')}
                              </span>
                              <span className="bar-value">{count}</span>
                            </div>
                            <div className="bar-track">
                              <div
                                className="bar-fill"
                                style={{
                                  width: `${(count / Math.max(...Object.values(patterns.hook_dist))) * 100}%`,
                                  background: hookColors[hook] || 'var(--accent)',
                                }}
                              />
                            </div>
                          </div>
                        ))}
                    </div>
                  ) : (
                    <div className="empty-state">Fetch trends to see distribution</div>
                  )}
                </div>

                <div className="card">
                  <div className="card-header">Top Trends</div>
                  {trends.slice(0, 5).length > 0 ? (
                    <div className="trend-list-compact">
                      {trends.slice(0, 5).map((t, i) => (
                        <div key={t.id} className="trend-row" onClick={() => setPage('generate')}>
                          <span className="trend-rank">{i + 1}</span>
                          <div className="trend-info">
                            <div className="trend-title-sm">{t.title}</div>
                            <Tag
                              label={t.analysis?.hook_type?.replace(/_/g, ' ') || 'neutral'}
                              color={hookColors[t.analysis?.hook_type] || hookColors.neutral}
                            />
                          </div>
                          <ScoreRing score={t.virality_score || 0} size={44} />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="empty-state">
                      <div className="empty-icon">↑</div>
                      <div>No trends yet</div>
                      <div className="empty-hint">Click "Fetch Live Trends"</div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Trends Page */}
          {page === 'trends' && (
            <div className="page" data-testid="page-trends">
              <div className="page-header">
                <div>
                  <h1 className="page-title">Trend Feed</h1>
                  <p className="page-subtitle">{filteredTrends.length} trends · sorted by virality score</p>
                </div>
                <div className="header-actions">
                  <button className="btn btn-ghost" onClick={() => fetchTrends(true)}>
                    ↺ Force Refresh
                  </button>
                  <button
                    className="btn btn-primary"
                    onClick={() => fetchTrends()}
                    disabled={loading}
                    data-testid="fetch-trends-btn-2"
                  >
                    {loading ? '⟳ Loading...' : '⚡ Fetch Trends'}
                  </button>
                </div>
              </div>

              <div className="filter-bar">
                <span className="filter-label">HOOK:</span>
                {['', 'curiosity_gap', 'number_hook', 'pattern_interrupt', 'fear_hook', 'transformation', 'question_hook', 'list_format'].map(h => (
                  <button
                    key={h}
                    className={`filter-pill ${hookFilter === h ? 'active' : ''}`}
                    onClick={() => setHookFilter(h)}
                  >
                    {h ? h.replace(/_/g, ' ') : 'All'}
                  </button>
                ))}
              </div>

              {filteredTrends.length > 0 ? (
                <div className="trends-grid">
                  {filteredTrends.map(t => (
                    <div key={t.id} className="trend-card" data-testid="trend-card">
                      <div className="trend-title">{t.title}</div>
                      <div className="trend-tags">
                        <Tag
                          label={t.analysis?.hook_type?.replace(/_/g, ' ') || 'neutral'}
                          color={hookColors[t.analysis?.hook_type] || hookColors.neutral}
                        />
                        {t.analysis?.triggers?.slice(0, 2).map(tr => (
                          <Tag key={tr} label={tr} color="#9b5ce0" />
                        ))}
                      </div>
                      <div className="trend-footer">
                        <span className="trend-source">{t.source?.replace('yt:', 'YT/')}</span>
                        <div className="trend-score">
                          <span style={{ color: t.virality_score >= 70 ? '#3dd68c' : 'var(--accent)' }}>
                            {t.virality_score}
                          </span>
                          <button className="btn btn-xs btn-primary" onClick={() => setPage('generate')}>
                            Use →
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-state-large">
                  <div className="empty-icon">↑</div>
                  <div className="empty-title">No trends loaded</div>
                  <div className="empty-hint">Click "Fetch Trends" to load live data</div>
                </div>
              )}
            </div>
          )}

          {/* Generate Page */}
          {page === 'generate' && (
            <div className="page" data-testid="page-generate">
              <div className="page-header">
                <div>
                  <h1 className="page-title">AI Decision Engine</h1>
                  <p className="page-subtitle">10 options → 6-dimension scoring → AI selection → script</p>
                </div>
              </div>

              <div className="gen-controls">
                <div className="input-group">
                  <label className="input-label">Niche</label>
                  <select
                    value={niche}
                    onChange={(e) => setNiche(e.target.value)}
                    data-testid="niche-select"
                  >
                    <option value="general">General</option>
                    <option value="finance">Finance & Money</option>
                    <option value="fitness">Fitness & Health</option>
                    <option value="tech">Technology & AI</option>
                    <option value="relationships">Relationships</option>
                    <option value="productivity">Productivity</option>
                    <option value="mindset">Mindset & Psychology</option>
                    <option value="gaming">Gaming</option>
                    <option value="food">Food & Cooking</option>
                    <option value="travel">Travel</option>
                  </select>
                </div>
                <button
                  className="btn btn-primary"
                  onClick={runGeneration}
                  disabled={loading}
                  data-testid="generate-btn"
                >
                  {loading ? '⟳ Generating...' : '✦ Generate'}
                </button>
                <div className="gen-stats">
                  <span>Top hook: <strong style={{ color: 'var(--accent)' }}>{patterns.top_hook || '—'}</strong></span>
                  <span>Avg: <strong style={{ color: '#3dd68c' }}>{patterns.avg_score || '—'}</strong></span>
                </div>
              </div>

              <div className="tab-bar">
                <button
                  className={`tab-btn ${genTab === 'ideas' ? 'active' : ''}`}
                  onClick={() => setGenTab('ideas')}
                >
                  Ideas ({ideas.length})
                </button>
                <button
                  className={`tab-btn ${genTab === 'script' ? 'active' : ''}`}
                  onClick={() => setGenTab('script')}
                >
                  Script
                </button>
                <button
                  className={`tab-btn ${genTab === 'video' ? 'active' : ''}`}
                  onClick={() => setGenTab('video')}
                >
                  Build Video
                </button>
              </div>

              {genTab === 'ideas' && (
                <div className="tab-content">
                  {ideas.length > 0 ? (
                    <div className="ideas-list">
                      {ideas.map((opt, i) => {
                        const isWinner = opt.idx === (winner?.idx ?? 0);
                        return (
                          <div key={i} className={`idea-card ${isWinner ? 'winner' : ''}`} data-testid="idea-card">
                            {isWinner && <div className="winner-badge">🏆 AI SELECTED</div>}
                            <div className="idea-rank">
                              #{i + 1} · Score: <span style={{ color: opt.virality_score >= 70 ? '#3dd68c' : 'var(--accent)' }}>{opt.virality_score}</span>
                            </div>
                            <div className="idea-title">{opt.title}</div>
                            <div className="idea-hook">"{opt.hook}"</div>
                            <div className="idea-tags">
                              <Tag label={opt.hook_type?.replace(/_/g, ' ')} color={hookColors[opt.hook_type]} />
                              <Tag label={opt.primary_trigger} color="#9b5ce0" />
                              <Tag label={opt.structure} color="#5c9de0" />
                            </div>
                            <div className="idea-scores">
                              {opt.scores && Object.entries(opt.scores).map(([dim, val]) => (
                                <div key={dim} className="score-row">
                                  <span className="score-name">{dim.replace(/_/g, ' ')}</span>
                                  <div className="score-track">
                                    <div
                                      className="score-fill"
                                      style={{
                                        width: `${val * 10}%`,
                                        background: val >= 7 ? '#3dd68c' : val >= 5 ? 'var(--accent)' : '#e05c5c',
                                      }}
                                    />
                                  </div>
                                  <span className="score-val">{val}/10</span>
                                </div>
                              ))}
                            </div>
                            {isWinner && decision && (
                              <div className="why-wins">
                                <div className="why-label">WHY THIS WINS</div>
                                <div className="why-text">{decision.why_wins}</div>
                                <div className="why-meta">
                                  <span>🎯 {decision.predicted_views_range}</span>
                                  <span>⚡ {decision.strongest_element}</span>
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="empty-state-large">
                      <div className="empty-icon">✦</div>
                      <div className="empty-title">No ideas generated yet</div>
                      <div className="empty-hint">Select a niche and click Generate</div>
                    </div>
                  )}
                </div>
              )}

              {genTab === 'script' && (
                <div className="tab-content">
                  {script ? (
                    <div className="script-view">
                      <div className="script-header">
                        <div>
                          <div className="script-title">{script.title}</div>
                          <div className="script-hook">"{script.hook}"</div>
                        </div>
                        <div className="script-meta">
                          <div className="meta-item">
                            <span className="meta-label">DURATION</span>
                            <span className="meta-value">{script.total_duration || '?'}s</span>
                          </div>
                          <div className="meta-item">
                            <span className="meta-label">SCENES</span>
                            <span className="meta-value">{script.scenes?.length || 0}</span>
                          </div>
                        </div>
                      </div>

                      <div className="scene-timeline">
                        {script.scenes?.map((sc, i) => (
                          <div key={i} className={`scene-block phase-${sc.phase}`}>
                            <div className="scene-header-row">
                              <span className="scene-phase">{sc.phase?.toUpperCase()}</span>
                              <span className="scene-time">{sc.start_time || 0}s–{sc.end_time || '?'}s</span>
                              <span className="scene-trans">{sc.transition || 'cut'}</span>
                            </div>
                            <div className="scene-spoken">{sc.spoken_text}</div>
                            <div className="scene-caption">📺 "{sc.caption_text}"</div>
                            <div className="scene-visual">📽 {sc.visual_direction}</div>
                          </div>
                        ))}
                      </div>

                      <div className="script-footer">
                        <div className="card">
                          <div className="card-header">MUSIC</div>
                          <div className="card-body">{script.music_direction || '—'}</div>
                        </div>
                        <div className="card">
                          <div className="card-header">THUMBNAIL</div>
                          <div className="card-body">{script.thumbnail_concept || '—'}</div>
                        </div>
                      </div>

                      <div className="hashtag-row">
                        {script.hashtags?.map(h => <Tag key={h} label={h} color="#5c9de0" />)}
                      </div>

                      {decision?.critical_execution_tip && (
                        <div className="execution-tip">
                          <span className="tip-icon">⚡</span>
                          <span><strong>Critical tip:</strong> {decision.critical_execution_tip}</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="empty-state-large">
                      <div className="empty-icon">📝</div>
                      <div className="empty-title">No script yet</div>
                      <div className="empty-hint">Generate content first</div>
                    </div>
                  )}
                </div>
              )}

              {genTab === 'video' && (
                <div className="tab-content">
                  <div className="card video-build-card">
                    <div className="card-header">Video Assembly</div>
                    <div className="input-group">
                      <label className="input-label">Color Palette</label>
                      <select value={palette} onChange={(e) => setPalette(e.target.value)}>
                        <option value="amber">Amber (default)</option>
                        <option value="crimson">Crimson</option>
                        <option value="ice">Ice Blue</option>
                        <option value="void">Void Purple</option>
                        <option value="forest">Forest Green</option>
                        <option value="solar">Solar Orange</option>
                      </select>
                    </div>
                    <div className="build-info">
                      PIL frames + Ken Burns zoom + FFmpeg H.264<br />
                      AI Voice (OpenAI TTS) + 9:16 TikTok-ready MP4
                    </div>
                    
                    {videoProgress && (
                      <ProgressBar progress={videoProgress.progress} message={videoProgress.message} />
                    )}
                    
                    <button
                      className="btn btn-primary btn-lg"
                      onClick={buildVideo}
                      disabled={!script || buildingVideo}
                      data-testid="build-video-btn"
                    >
                      {buildingVideo ? `⟳ ${videoProgress?.progress || 0}%` : '⚡ Build Video'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Videos Page */}
          {page === 'videos' && (
            <div className="page" data-testid="page-videos">
              <div className="page-header">
                <div>
                  <h1 className="page-title">Video Library</h1>
                  <p className="page-subtitle">9:16 TikTok-ready · download MP4 · export package</p>
                </div>
                <button className="btn btn-ghost" onClick={loadVideos}>↺ Refresh</button>
              </div>

              {videos.length > 0 ? (
                <div className="videos-list">
                  {videos.map(v => (
                    <div key={v.id} className="video-card" data-testid="video-card">
                      <div className="video-thumb">
                        {v.has_video ? '🎬' : '⏳'}
                      </div>
                      <div className="video-info">
                        <div className="video-title">{v.title || 'Untitled Video'}</div>
                        <div className="video-badges">
                          <span className={`badge badge-${v.status === 'done' ? 'green' : v.status === 'processing' ? 'amber' : 'red'}`}>
                            {v.status}
                          </span>
                          {v.has_video && <span className="badge badge-blue">9:16 READY</span>}
                          {v.file_size_mb > 0 && <span className="badge badge-dim">{v.file_size_mb}MB</span>}
                        </div>
                        <div className="video-date">{new Date(v.created_at).toLocaleString()}</div>
                        <div className="video-actions">
                          {v.has_video && (
                            <a
                              href={`${API_BASE}/api/video/${v.id}/download`}
                              className="btn btn-primary btn-sm"
                              download
                              data-testid="download-video-btn"
                            >
                              ⬇ Download MP4
                            </a>
                          )}
                          {v.has_export && (
                            <button
                              className="btn btn-ghost btn-sm"
                              onClick={async () => {
                                const res = await api.get(`/api/publish/caption/${v.id}`);
                                if (res.ok) {
                                  await navigator.clipboard.writeText(res.data.caption);
                                  showToast('Caption copied!', 'success');
                                }
                              }}
                            >
                              📋 Copy Caption
                            </button>
                          )}
                        </div>
                      </div>
                      <ScoreRing score={v.virality_score || 0} size={52} />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-state-large">
                  <div className="empty-icon">▶</div>
                  <div className="empty-title">No videos yet</div>
                  <div className="empty-hint">Generate a script then click "Build Video"</div>
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
