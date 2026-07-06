/**
 * OpenHands Tool — User-spezifische AI-Coding-Jobs.
 *
 * Integriert mit OpenHands Enterprise via Backend API.
 * Issue #529
 */

import React, { useState, useEffect, useCallback } from 'react';
import type { LauncherToolProps } from '../../launcherRegistry';
import { Bot, Plus, Clock, CheckCircle, XCircle, ExternalLink, RefreshCw } from 'lucide-react';

const C = {
  bg:      '#0e1116',
  surface: '#161c24',
  border:  '#232d3a',
  accent:  '#00d9b1',
  text:    '#cdd9e5',
  textSub: '#768390',
  success: '#3fb950',
  error:   '#f85149',
  warning: '#d29922',
} as const;

interface OpenHandsJob {
  job_id: string;
  external_conv_id: string | null;
  repo_url: string | null;
  branch: string | null;
  mission: string;
  status: 'pending' | 'queued' | 'running' | 'completed' | 'failed' | 'blocked' | 'waiting-for-user';
  draft_pr_url: string | null;
  last_error: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

interface CreateJobRequest {
  repoUrl: string;
  branch: string;
  mission: string;
}

export function OpenHandsTool({ onClose, onMinimize }: LauncherToolProps) {
  const [jobs, setJobs] = useState<OpenHandsJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  
  // Form state
  const [repoUrl, setRepoUrl] = useState('');
  const [branch, setBranch] = useState('main');
  const [mission, setMission] = useState('');

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch('/api/user/openhands/jobs');
      if (!resp.ok) {
        if (resp.status === 401) {
          setError('Nicht autorisiert. Bitte einloggen.');
        } else {
          setError(`Fehler: ${resp.status}`);
        }
        return;
      }
      const data = await resp.json();
      setJobs(data.jobs || []);
    } catch (e) {
      setError('Netzwerkfehler beim Laden der Jobs');
    } finally {
      setLoading(false);
    }
  }, []);

  const createJob = async () => {
    if (!repoUrl || !mission) {
      setError('Repository URL und Mission sind erforderlich');
      return;
    }
    
    setLoading(true);
    setError(null);
    try {
      const body: CreateJobRequest = { repoUrl, branch: branch || 'main', mission };
      const resp = await fetch('/api/user/openhands/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      
      if (!resp.ok) {
        const errData = await resp.json();
        setError(errData.error || `Fehler: ${resp.status}`);
        return;
      }
      
      // Reset form and refresh jobs
      setRepoUrl('');
      setBranch('main');
      setMission('');
      setShowCreateForm(false);
      fetchJobs();
    } catch (e) {
      setError('Netzwerkfehler beim Erstellen des Jobs');
    } finally {
      setLoading(false);
    }
  };

  const cancelJob = async (jobId: string) => {
    setLoading(true);
    try {
      const resp = await fetch(`/api/user/openhands/jobs/${jobId}/cancel`, {
        method: 'POST',
      });
      
      if (resp.ok) {
        fetchJobs(); // Refresh list
      } else {
        const errData = await resp.json();
        setError(errData.error || 'Cancel fehlgeschlagen');
      }
    } catch (e) {
      setError('Netzwerkfehler beim Canceln');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircle size={16} color={C.success} />;
      case 'failed': return <XCircle size={16} color={C.error} />;
      case 'running':
      case 'queued': return <Clock size={16} color={C.warning} />;
      default: return <Clock size={16} color={C.textSub} />;
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleString('de-DE');
  };

  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        overflowY: 'auto',
        background: C.bg,
      }}
    >
      {/* Header */}
      <div style={{
        padding: '16px 20px',
        borderBottom: `1px solid ${C.border}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: C.surface,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Bot size={20} color={C.accent} />
          <span style={{ fontWeight: 700, color: C.text }}>OpenHands Jobs</span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={fetchJobs}
            style={{
              padding: '6px 10px',
              borderRadius: 6,
              border: `1px solid ${C.border}`,
              background: 'transparent',
              color: C.textSub,
              cursor: 'pointer',
              fontSize: 11,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <RefreshCw size={12} /> Refresh
          </button>
          <button
            onClick={() => setShowCreateForm(!showCreateForm)}
            style={{
              padding: '6px 12px',
              borderRadius: 6,
              border: 'none',
              background: C.accent,
              color: '#000',
              cursor: 'pointer',
              fontWeight: 700,
              fontSize: 11,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <Plus size={14} /> Neuer Job
          </button>
        </div>
      </div>

      {/* Create Form */}
      {showCreateForm && (
        <div style={{
          padding: 16,
          borderBottom: `1px solid ${C.border}`,
          background: C.surface,
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}>
          <h4 style={{ margin: 0, color: C.text, fontSize: 13 }}>Neuen OpenHands Job erstellen</h4>
          
          <input
            type="text"
            placeholder="Repository URL (z.B. https://github.com/user/repo)"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            style={{
              padding: '8px 12px',
              borderRadius: 6,
              border: `1px solid ${C.border}`,
              background: C.bg,
              color: C.text,
              fontSize: 12,
              width: '100%',
              boxSizing: 'border-box',
            }}
          />
          
          <input
            type="text"
            placeholder="Branch (Standard: main)"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
            style={{
              padding: '8px 12px',
              borderRadius: 6,
              border: `1px solid ${C.border}`,
              background: C.bg,
              color: C.text,
              fontSize: 12,
              width: '100%',
              boxSizing: 'border-box',
            }}
          />
          
          <textarea
            placeholder="Mission beschreiben (was soll OpenHands tun?)"
            value={mission}
            onChange={(e) => setMission(e.target.value)}
            rows={3}
            style={{
              padding: '8px 12px',
              borderRadius: 6,
              border: `1px solid ${C.border}`,
              background: C.bg,
              color: C.text,
              fontSize: 12,
              width: '100%',
              boxSizing: 'border-box',
              resize: 'vertical',
              fontFamily: 'inherit',
            }}
          />
          
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button
              onClick={() => setShowCreateForm(false)}
              style={{
                padding: '8px 16px',
                borderRadius: 6,
                border: `1px solid ${C.border}`,
                background: 'transparent',
                color: C.textSub,
                cursor: 'pointer',
                fontSize: 12,
              }}
            >
              Abbrechen
            </button>
            <button
              onClick={createJob}
              disabled={loading}
              style={{
                padding: '8px 16px',
                borderRadius: 6,
                border: 'none',
                background: C.accent,
                color: '#000',
                cursor: loading ? 'not-allowed' : 'pointer',
                fontWeight: 700,
                fontSize: 12,
                opacity: loading ? 0.7 : 1,
              }}
            >
              {loading ? 'Erstelle...' : 'Job starten'}
            </button>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{
          padding: '12px 16px',
          background: `${C.error}20`,
          borderBottom: `1px solid ${C.error}`,
          color: C.error,
          fontSize: 12,
        }}>
          {error}
          <button
            onClick={() => setError(null)}
            style={{
              marginLeft: 12,
              padding: '2px 8px',
              borderRadius: 4,
              border: `1px solid ${C.error}`,
              background: 'transparent',
              color: C.error,
              cursor: 'pointer',
              fontSize: 10,
            }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Job List */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
        {loading && jobs.length === 0 ? (
          <div style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 40,
            color: C.textSub,
          }}>
            Lade Jobs...
          </div>
        ) : jobs.length === 0 ? (
          <div style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 40,
            gap: 8,
          }}>
            <Bot size={32} color={C.textSub} style={{ opacity: 0.3 }} />
            <p style={{ color: C.textSub, fontSize: 12, textAlign: 'center' }}>
              Noch keine OpenHands Jobs.<br />
              Erstelle deinen ersten Job!
            </p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {jobs.map((job) => (
              <div
                key={job.job_id}
                style={{
                  padding: 12,
                  borderRadius: 8,
                  border: `1px solid ${C.border}`,
                  background: C.surface,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                }}
              >
                {/* Status Row */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {getStatusIcon(job.status)}
                    <span style={{
                      fontSize: 12,
                      fontWeight: 600,
                      color: C.text,
                      textTransform: 'capitalize',
                    }}>
                      {job.status.replace('-', ' ')}
                    </span>
                  </div>
                  {job.status === 'running' && (
                    <button
                      onClick={() => cancelJob(job.job_id)}
                      style={{
                        padding: '4px 8px',
                        borderRadius: 4,
                        border: `1px solid ${C.error}`,
                        background: 'transparent',
                        color: C.error,
                        cursor: 'pointer',
                        fontSize: 10,
                      }}
                    >
                      Cancel
                    </button>
                  )}
                </div>

                {/* Mission */}
                <p style={{
                  margin: 0,
                  fontSize: 12,
                  color: C.text,
                  lineHeight: 1.4,
                }}>
                  {job.mission}
                </p>

                {/* Repo Info */}
                {job.repo_url && (
                  <div style={{ fontSize: 10, color: C.textSub }}>
                    <span style={{ opacity: 0.7 }}>Repo:</span> {job.repo_url}
                    {job.branch && <span> ({job.branch})</span>}
                  </div>
                )}

                {/* Times */}
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: 10,
                  color: C.textSub,
                  opacity: 0.7,
                }}>
                  <span>Erstellt: {formatDate(job.created_at)}</span>
                  {job.completed_at && <span>Fertig: {formatDate(job.completed_at)}</span>}
                </div>

                {/* Draft PR Link */}
                {job.draft_pr_url && (
                  <a
                    href={job.draft_pr_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '6px 10px',
                      borderRadius: 4,
                      background: `${C.success}20`,
                      color: C.success,
                      fontSize: 11,
                      textDecoration: 'none',
                      marginTop: 4,
                    }}
                  >
                    <ExternalLink size={12} />
                    Draft PR anzeigen
                  </a>
                )}

                {/* Error */}
                {job.last_error && job.status === 'failed' && (
                  <div style={{
                    padding: '6px 8px',
                    borderRadius: 4,
                    background: `${C.error}15`,
                    color: C.error,
                    fontSize: 10,
                  }}>
                    Fehler: {job.last_error}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
