/**
 * AdminGate — Zeigt Admin-UI nur für Nutzer mit role === 'admin' | 'superadmin'.
 *
 * Issue #460
 */

import React from 'react';
import { ShieldOff } from 'lucide-react';
import { useUserStore } from '../user/useUserStore';

interface AdminGateProps {
  children: React.ReactNode;
}

export function AdminGate({ children }: AdminGateProps) {
  const user = useUserStore(s => s.user);

  if (!user || (user.role !== 'admin' && user.role !== 'superadmin')) {
    return (
      <div
        style={{
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 12,
          background: '#0e1116',
        }}
      >
        <ShieldOff size={32} style={{ opacity: 0.2, color: '#cdd9e5' }} />
        <p style={{ fontSize: 13, color: '#768390', textAlign: 'center' }}>
          Kein Admin-Zugang.
        </p>
        <p style={{ fontSize: 11, color: '#768390', opacity: 0.6, textAlign: 'center' }}>
          Nur Nutzer mit der Rolle <strong>admin</strong> können diesen Bereich öffnen.
        </p>
      </div>
    );
  }

  return <>{children}</>;
}
