/**
 * UserProfile — Profil-Sheet mit Credits, Abo-Status und Logout.
 * Issue #459
 */

import React from 'react';
import { useUserStore } from '../useUserStore';

const C = {
  bg:      '#0e1116',
  surface: '#161c25',
  surface2:'#1c2333',
  border:  '#263042',
  accent:  '#58a6ff',
  green:   '#3fb950',
  amber:   '#d29922',
  danger:  '#f85149',
  text:    '#e6edf3',
  sub:     '#8b949e',
};

const SUB_LABEL: Record<string, { label: string; color: string }> = {
  active:   { label: 'Pro aktiv',    color: C.green },
  trialing: { label: 'Testphase',    color: C.amber },
  canceled: { label: 'Gekündigt',    color: C.sub   },
  past_due: { label: 'Zahlung offen',color: C.danger },
  free:     { label: 'Free',         color: C.sub   },
};

interface Props {
  onClose: () => void;
  onBuyCredits?: () => void;
}

export function UserProfile({ onClose, onBuyCredits }: Props) {
  const { user, logout } = useUserStore();
  if (!user) return null;

  const sub = SUB_LABEL[user.subscriptionStatus] ?? SUB_LABEL.free;
  const initials = (user.displayName || user.email)
    .split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2);

  async function handleLogout() {
    await logout();
    onClose();
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 9000,
        background: 'rgba(0,0,0,.6)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'flex-end',
        padding: '60px 12px 0',
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        background: C.surface, border: `1px solid ${C.border}`,
        borderRadius: 14, padding: 24, width: 300,
        boxShadow: '0 16px 48px rgba(0,0,0,.5)',
      }}>
        {/* Avatar + Name */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 20 }}>
          {user.avatarUrl
            ? <img src={user.avatarUrl} alt="" style={{ width: 48, height: 48, borderRadius: '50%', objectFit: 'cover' }} />
            : (
              <div style={{
                width: 48, height: 48, borderRadius: '50%',
                background: `${C.accent}22`, border: `2px solid ${C.accent}55`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontWeight: 700, fontSize: 16, color: C.accent,
              }}>
                {initials}
              </div>
            )
          }
          <div>
            <div style={{ fontWeight: 600, fontSize: 15, color: C.text }}>{user.displayName || 'Nutzer'}</div>
            <div style={{ fontSize: 12, color: C.sub, marginTop: 2 }}>{user.email}</div>
          </div>
        </div>

        {/* Stats */}
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr 1fr',
          gap: 10, marginBottom: 20,
        }}>
          <StatBox label="Credits" value={user.credits.toLocaleString('de-DE')} color={C.accent} />
          <StatBox label="Status" value={sub.label} color={sub.color} />
        </div>

        {/* Role badge */}
        {(user.role === 'admin' || user.role === 'superadmin') && (
          <div style={{
            background: `${C.amber}18`, border: `1px solid ${C.amber}44`,
            borderRadius: 7, padding: '6px 12px', fontSize: 12,
            color: C.amber, textAlign: 'center', marginBottom: 16,
          }}>
            ⚙️ {user.role === 'superadmin' ? 'Super-Admin' : 'Admin'}
          </div>
        )}

        {/* Actions */}
        {onBuyCredits && (
          <button
            onClick={onBuyCredits}
            style={{
              width: '100%', background: C.accent, border: 'none',
              borderRadius: 7, color: '#0d1117', fontWeight: 600,
              fontSize: 14, padding: '9px 0', cursor: 'pointer',
              marginBottom: 10, fontFamily: 'inherit',
            }}
          >
            Credits kaufen
          </button>
        )}

        <button
          onClick={handleLogout}
          style={{
            width: '100%', background: 'transparent',
            border: `1px solid ${C.border}`, borderRadius: 7,
            color: C.sub, fontSize: 13, padding: '8px 0',
            cursor: 'pointer', fontFamily: 'inherit',
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = C.danger; (e.currentTarget as HTMLButtonElement).style.color = C.danger; }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = C.border; (e.currentTarget as HTMLButtonElement).style.color = C.sub; }}
        >
          Abmelden
        </button>
      </div>
    </div>
  );
}

function StatBox({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{
      background: '#0e1116', border: '1px solid #263042',
      borderRadius: 8, padding: '10px 12px',
    }}>
      <div style={{ fontSize: 11, color: C.sub, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.5px' }}>{label}</div>
      <div style={{ fontSize: 15, fontWeight: 700, color }}>{value}</div>
    </div>
  );
}
