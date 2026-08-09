import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./App', () => ({
  default: () => <div data-testid="user-app-surface">User application</div>,
}));

vi.mock('./features/admin/AdminPanel', () => ({
  AdminPanel: () => <div data-testid="admin-panel-surface">Admin panel</div>,
}));

import SovereignAppWrapper from './SovereignAppWrapper';

describe('SovereignAppWrapper browser entry boundary', () => {
  afterEach(() => {
    window.history.replaceState({}, '', '/');
  });

  it('mounts the user application at the browser APK mirror path', () => {
    window.history.replaceState({}, '', '/app/');
    render(<SovereignAppWrapper />);

    expect(screen.getByTestId('user-app-surface')).toBeDefined();
    expect(screen.queryByTestId('admin-panel-surface')).toBeNull();
  });

  it('keeps the admin panel isolated to /admin/', () => {
    window.history.replaceState({}, '', '/admin/');
    render(<SovereignAppWrapper />);

    expect(screen.getByTestId('admin-panel-surface')).toBeDefined();
    expect(screen.queryByTestId('user-app-surface')).toBeNull();
  });
});
