import React, { useState, useEffect, useRef } from 'react';
import './App.css';

const API_BASE = process.env.REACT_APP_BACKEND_URL || '';

// Progress steps
const STEPS = [
  { key: 'analyze', label: 'Analyzing request', icon: '🔍' },
  { key: 'trends', label: 'Fetching trends', icon: '📈' },
  { key: 'idea', label: 'Creating idea', icon: '💡' },
  { key: 'script', label: 'Writing script', icon: '📝' },
  { key: 'video', label: 'Building video', icon: '🎬' },
  { key: 'voice', label: 'Generating voice', icon: '🎙️' },
  { key: 'final', label: 'Finalizing', icon: '✨' },
];

function App() {
  const [prompt, setPrompt] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [step, setStep] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState([]);
  const videoRef = useRef(null);
  const inputRef = useRef(null);

  // Get current step index
  const getCurrentStepIndex = () => {
    const stepLower = step.toLowerCase();
    if (stepLower.includes('analyz')) return 0;
    if (stepLower.includes('trend')) return 1;
    if (stepLower.includes('idea') || stepLower.includes('creat')) return 2;
    if (stepLower.includes('script') || stepLower.includes('writ')) return 3;
    if (stepLower.includes('video') || stepLower.includes('render') || stepLower.includes('build')) return 4;
    if (stepLower.includes('voice') || stepLower.includes('audio')) return 5;
    if (stepLower.includes('final') || stepLower.includes('done')) return 6;
    return Math.floor(progress / 15);
  };

  // Poll job status
  const pollJob = async (jobId) => {
    const maxAttempts = 200;
    let attempts = 0;

    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/job/${jobId}`);
        const data = await res.json();

        setProgress(data.progress || 0);
        setStep(data.step || '');

        if (data.status === 'complete' && data.result) {
          setResult(data.result);
          setIsGenerating(false);
          return;
        }

        if (data.status === 'error') {
          setError(data.step || 'Generation failed. Please try again.');
          setIsGenerating(false);
          return;
        }

        attempts++;
        if (attempts < maxAttempts) {
          setTimeout(poll, 1000);
        } else {
          setError('Generation timed out. Please try again.');
          setIsGenerating(false);
        }
      } catch (e) {
        if (attempts < 3) {
          attempts++;
          setTimeout(poll, 2000);
        } else {
          setError('Connection error. Please check your internet.');
          setIsGenerating(false);
        }
      }
    };

    poll();
  };

  // Handle generate
  const handleGenerate = async () => {
    if (!prompt.trim() || isGenerating) return;

    setIsGenerating(true);
    setProgress(0);
    setStep('Starting...');
    setResult(null);
    setError('');

    try {
      const res = await fetch(`${API_BASE}/api/generate-all`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: prompt.trim() }),
      });

      const data = await res.json();

      if (data.job_id) {
        pollJob(data.job_id);
      } else {
        setError(data.detail || 'Failed to start. Please try again.');
        setIsGenerating(false);
      }
    } catch (e) {
      setError('Connection failed. Please try again.');
      setIsGenerating(false);
    }
  };

  // Handle enter key
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleGenerate();
    }
  };

  // Reset
  const handleReset = () => {
    setPrompt('');
    setResult(null);
    setError('');
    setProgress(0);
    setStep('');
    inputRef.current?.focus();
  };

  // Load history
  const loadHistory = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/history`);
      const data = await res.json();
      setHistory(data.history || []);
    } catch (e) {}
  };

  // Example prompts
  const examples = [
    { emoji: '💰', text: 'Create a viral video about passive income' },
    { emoji: '💪', text: 'Make a fitness motivation short' },
    { emoji: '🧠', text: 'Create a productivity hack video' },
    { emoji: '❤️', text: 'Make a relationship advice TikTok' },
  ];

  const currentStepIndex = getCurrentStepIndex();

  return (
    <div className="app" data-testid="app">
      {/* Animated background */}
      <div className="bg-gradient">
        <div className="bg-orb bg-orb-1" />
        <div className="bg-orb bg-orb-2" />
        <div className="bg-orb bg-orb-3" />
      </div>

      {/* Container */}
      <div className="container">
        {/* Header */}
        <header className="header">
          <div className="logo" data-testid="logo">
            <div className="logo-icon">⚡</div>
            <span className="logo-text">ViralForge</span>
            <span className="logo-badge">PRO</span>
          </div>
        </header>

        {/* Main */}
        <main className="main">
          {!result ? (
            <div className={`input-section ${isGenerating ? 'generating' : ''}`} data-testid="input-section">
              <h1 className="title">
                Turn ideas into<br />
                <span className="title-accent">viral videos</span>
              </h1>
              <p className="subtitle">
                Type anything — we'll create the idea, script, voice & video automatically
              </p>

              <div className="input-card">
                <textarea
                  ref={inputRef}
                  className="main-input"
                  placeholder="Create a viral video about..."
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  onKeyPress={handleKeyPress}
                  disabled={isGenerating}
                  rows={2}
                  data-testid="main-input"
                />
                
                <button
                  className={`generate-btn ${isGenerating ? 'loading' : ''}`}
                  onClick={handleGenerate}
                  disabled={!prompt.trim() || isGenerating}
                  data-testid="generate-btn"
                >
                  {isGenerating ? (
                    <>
                      <span className="btn-spinner" />
                      <span>Generating...</span>
                    </>
                  ) : (
                    <>
                      <span className="btn-icon">✦</span>
                      <span>Generate Video</span>
                    </>
                  )}
                </button>
              </div>

              {/* Progress */}
              {isGenerating && (
                <div className="progress-section" data-testid="progress-section">
                  <div className="progress-steps">
                    {STEPS.map((s, i) => (
                      <div 
                        key={s.key} 
                        className={`progress-step ${i < currentStepIndex ? 'done' : i === currentStepIndex ? 'active' : ''}`}
                      >
                        <div className="step-icon">{i < currentStepIndex ? '✓' : s.icon}</div>
                        <div className="step-label">{s.label}</div>
                      </div>
                    ))}
                  </div>
                  
                  <div className="progress-bar-container">
                    <div className="progress-bar">
                      <div className="progress-fill" style={{ width: `${progress}%` }} />
                    </div>
                    <div className="progress-text">
                      <span>{step}</span>
                      <span className="progress-percent">{progress}%</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Error */}
              {error && (
                <div className="error-card" data-testid="error-message">
                  <span className="error-icon">⚠️</span>
                  <span>{error}</span>
                  <button className="error-retry" onClick={handleGenerate}>Retry</button>
                </div>
              )}

              {/* Examples */}
              {!isGenerating && (
                <div className="examples">
                  <span className="examples-label">Try these:</span>
                  <div className="examples-list">
                    {examples.map((ex, i) => (
                      <button 
                        key={i} 
                        className="example-btn"
                        onClick={() => setPrompt(ex.text)}
                      >
                        <span>{ex.emoji}</span>
                        <span>{ex.text.replace('Create a viral video about ', '').replace('Make a ', '')}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            /* Result */
            <div className="result-section" data-testid="result-section">
              {/* Video */}
              {result.video?.ready && (
                <div className="video-wrapper">
                  <div className="video-container">
                    <video
                      ref={videoRef}
                      className="video-player"
                      controls
                      autoPlay
                      loop
                      playsInline
                      src={`${API_BASE}${result.video.url}`}
                      data-testid="video-player"
                    />
                  </div>
                  <div className="video-badge">9:16 TikTok Ready</div>
                </div>
              )}

              {/* Content */}
              <div className="result-cards">
                {/* Idea */}
                <div className="result-card" data-testid="idea-card">
                  <div className="card-header">
                    <span className="card-emoji">💡</span>
                    <span className="card-title">Viral Idea</span>
                    <span className="card-tag">{result.idea?.niche}</span>
                  </div>
                  <h2 className="idea-title">{result.idea?.title}</h2>
                  <p className="idea-desc">{result.idea?.concept}</p>
                  {result.idea?.why_viral && (
                    <div className="viral-reason">
                      <strong>Why it works:</strong> {result.idea.why_viral}
                    </div>
                  )}
                </div>

                {/* Hook */}
                <div className="result-card hook-card" data-testid="hook-card">
                  <div className="card-header">
                    <span className="card-emoji">🎯</span>
                    <span className="card-title">Opening Hook</span>
                    <span className="card-tag accent">{result.idea?.hook_type?.replace('_', ' ')}</span>
                  </div>
                  <blockquote className="hook-quote">
                    "{result.idea?.hook || result.script?.hook}"
                  </blockquote>
                  <p className="hook-note">First 3 seconds — stops the scroll instantly</p>
                </div>

                {/* Script */}
                <div className="result-card script-card" data-testid="script-card">
                  <div className="card-header">
                    <span className="card-emoji">📝</span>
                    <span className="card-title">Full Script</span>
                    <span className="card-tag">{result.script?.duration}s</span>
                  </div>
                  <div className="scenes">
                    {result.script?.scenes?.map((scene, i) => (
                      <div key={i} className={`scene phase-${scene.phase}`}>
                        <div className="scene-meta">
                          <span className="scene-phase">{scene.phase}</span>
                          <span className="scene-time">{scene.duration}s</span>
                        </div>
                        <div className="scene-text">{scene.spoken_text}</div>
                        {scene.caption_text && (
                          <div className="scene-caption">📺 {scene.caption_text}</div>
                        )}
                      </div>
                    ))}
                  </div>
                  
                  {result.script?.hashtags?.length > 0 && (
                    <div className="hashtags">
                      {result.script.hashtags.map((tag, i) => (
                        <span key={i} className="hashtag">{tag}</span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="result-actions">
                  {result.video?.ready && (
                    <a
                      href={`${API_BASE}${result.video.url}`}
                      download={`viral_${result.video.id}.mp4`}
                      className="action-btn primary"
                      data-testid="download-btn"
                    >
                      <span>⬇️</span>
                      <span>Download Video</span>
                    </a>
                  )}
                  <button 
                    className="action-btn secondary"
                    onClick={() => {
                      const text = `${result.script?.caption || result.idea?.title}\n\n${result.script?.hashtags?.join(' ') || ''}`;
                      navigator.clipboard.writeText(text);
                    }}
                  >
                    <span>📋</span>
                    <span>Copy Caption</span>
                  </button>
                  <button 
                    className="action-btn ghost"
                    onClick={handleReset}
                    data-testid="new-btn"
                  >
                    <span>✨</span>
                    <span>Create Another</span>
                  </button>
                </div>
              </div>
            </div>
          )}
        </main>

        {/* Footer */}
        <footer className="footer">
          <span>Powered by AI</span>
          <span className="footer-dot">•</span>
          <span>Made for creators</span>
        </footer>
      </div>
    </div>
  );
}

export default App;
