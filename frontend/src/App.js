import React, { useState, useEffect, useRef } from 'react';
import './App.css';

const API_BASE = process.env.REACT_APP_BACKEND_URL || '';

function App() {
  const [prompt, setPrompt] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [step, setStep] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const videoRef = useRef(null);

  // Poll job status
  const pollJob = async (jobId) => {
    const maxAttempts = 180; // 3 minutes max
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
          setError(data.step || 'Generation failed');
          setIsGenerating(false);
          return;
        }

        attempts++;
        if (attempts < maxAttempts) {
          setTimeout(poll, 1000);
        } else {
          setError('Generation timed out');
          setIsGenerating(false);
        }
      } catch (e) {
        setError('Connection error');
        setIsGenerating(false);
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
        setError(data.detail || 'Failed to start generation');
        setIsGenerating(false);
      }
    } catch (e) {
      setError('Connection failed');
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

  // Reset to start over
  const handleReset = () => {
    setPrompt('');
    setResult(null);
    setError('');
    setProgress(0);
    setStep('');
  };

  return (
    <div className="app" data-testid="app">
      {/* Background gradient */}
      <div className="bg-gradient" />

      {/* Main container */}
      <div className="container">
        {/* Header */}
        <header className="header">
          <div className="logo" data-testid="logo">
            <span className="logo-icon">⚡</span>
            <span className="logo-text">ViralForge</span>
          </div>
        </header>

        {/* Content */}
        <main className="main">
          {!result ? (
            /* Input Section */
            <div className="input-section" data-testid="input-section">
              <h1 className="title">Turn ideas into viral videos</h1>
              <p className="subtitle">
                Type what you want, we'll create everything — idea, script, voice & video
              </p>

              <div className="input-wrapper">
                <textarea
                  className="main-input"
                  placeholder="Create a viral video about fitness motivation..."
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  onKeyPress={handleKeyPress}
                  disabled={isGenerating}
                  rows={3}
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
                      <span className="spinner" />
                      Generating...
                    </>
                  ) : (
                    <>
                      <span className="btn-icon">✦</span>
                      Generate
                    </>
                  )}
                </button>
              </div>

              {/* Progress Section */}
              {isGenerating && (
                <div className="progress-section" data-testid="progress-section">
                  <div className="progress-bar">
                    <div 
                      className="progress-fill" 
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                  <div className="progress-info">
                    <span className="progress-step">{step}</span>
                    <span className="progress-percent">{progress}%</span>
                  </div>
                </div>
              )}

              {/* Error */}
              {error && (
                <div className="error-message" data-testid="error-message">
                  {error}
                </div>
              )}

              {/* Example prompts */}
              <div className="examples">
                <span className="examples-label">Try:</span>
                <button onClick={() => setPrompt('Create a viral video about making money online')}>
                  💰 Money tips
                </button>
                <button onClick={() => setPrompt('Give me a trending TikTok idea about fitness')}>
                  💪 Fitness
                </button>
                <button onClick={() => setPrompt('Make a viral short about productivity hacks')}>
                  🚀 Productivity
                </button>
              </div>
            </div>
          ) : (
            /* Result Section */
            <div className="result-section" data-testid="result-section">
              {/* Video Preview */}
              {result.video?.ready && (
                <div className="video-container">
                  <video
                    ref={videoRef}
                    className="video-player"
                    controls
                    autoPlay
                    playsInline
                    src={`${API_BASE}${result.video.url}`}
                    data-testid="video-player"
                  />
                </div>
              )}

              {/* Content Cards */}
              <div className="result-content">
                {/* Idea */}
                <div className="result-card" data-testid="idea-card">
                  <div className="card-header">
                    <span className="card-icon">💡</span>
                    <span className="card-title">Viral Idea</span>
                    <span className="card-badge">{result.idea?.niche}</span>
                  </div>
                  <h2 className="idea-title">{result.idea?.title}</h2>
                  <p className="idea-concept">{result.idea?.concept}</p>
                  {result.idea?.why_viral && (
                    <p className="why-viral">
                      <strong>Why it works:</strong> {result.idea.why_viral}
                    </p>
                  )}
                </div>

                {/* Hook */}
                <div className="result-card hook-card" data-testid="hook-card">
                  <div className="card-header">
                    <span className="card-icon">🎯</span>
                    <span className="card-title">Opening Hook</span>
                    <span className="card-badge highlight">{result.idea?.hook_type?.replace('_', ' ')}</span>
                  </div>
                  <blockquote className="hook-text">
                    "{result.idea?.hook || result.script?.hook}"
                  </blockquote>
                  <p className="hook-note">First 3 seconds — stops the scroll</p>
                </div>

                {/* Script */}
                <div className="result-card script-card" data-testid="script-card">
                  <div className="card-header">
                    <span className="card-icon">📝</span>
                    <span className="card-title">Full Script</span>
                    <span className="card-badge">{result.script?.duration}s</span>
                  </div>
                  <div className="scenes-list">
                    {result.script?.scenes?.map((scene, i) => (
                      <div key={i} className={`scene-item phase-${scene.phase}`}>
                        <div className="scene-header">
                          <span className="scene-phase">{scene.phase?.toUpperCase()}</span>
                          <span className="scene-duration">{scene.duration}s</span>
                        </div>
                        <div className="scene-spoken">{scene.spoken_text}</div>
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
                      className="download-btn"
                      data-testid="download-btn"
                    >
                      <span>⬇️</span> Download Video
                    </a>
                  )}
                  <button 
                    className="new-btn" 
                    onClick={handleReset}
                    data-testid="new-btn"
                  >
                    <span>✨</span> Create Another
                  </button>
                </div>
              </div>
            </div>
          )}
        </main>

        {/* Footer */}
        <footer className="footer">
          <span>Powered by AI</span>
        </footer>
      </div>
    </div>
  );
}

export default App;
