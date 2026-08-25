import App from './App';
import { AdminPanel } from './features/admin/AdminPanel';
import type { LauncherToolProps } from './features/launcher/launcherRegistry';

const CANONICAL_ADMIN_PRODUCER = 'CANONICAL_REACT_ADMIN';

function isAdminPath(): boolean {
  if (typeof window === 'undefined') return false;
  return window.location.pathname === '/admin' || window.location.pathname.startsWith('/admin/');
}

export default function SovereignAppWrapper() {
  if (!isAdminPath()) return <App />;

  const revision = (import.meta.env.VITE_SOVEREIGN_SOURCE_REVISION as string | undefined)?.trim() || 'unverified';

  const toolProps: LauncherToolProps = {
    onClose: () => { window.location.href = '/'; },
    onMinimize: () => { window.location.href = '/'; },
  };

  return (
    <div
      data-sovereign-admin-producer={CANONICAL_ADMIN_PRODUCER}
      data-sovereign-source-revision={revision}
      data-sovereign-free-revolver="enabled"
    >
      <AdminPanel {...toolProps} />
    </div>
  );
}
