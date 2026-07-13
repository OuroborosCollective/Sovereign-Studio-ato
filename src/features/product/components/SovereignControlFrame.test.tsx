import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SovereignControlFrame } from './SovereignControlFrame';
import type { SovereignControlFrameState } from '../runtime/sovereignControlFrameRuntime';

const state: SovereignControlFrameState = {
  activeModuleId: 'orchestr',
  signalSummary: '1 processing · 0 warning · 0 error',
  sessionSummary: 'step=package-build · package=no · diff=no',
  activePatternCount: 0,
  confidence: 0.5,
  overrideActive: false,
  logs: [{ level: 'signal', moduleId: 'orchestr', message: 'Step: package-build' }],
  modules: [
    { id: 'init', signal: 'active', phase: 'done', detail: 'Repo ready.', conditions: [{ label: 'Repo snapshot ready', status: 'pass' }] },
    { id: 'router', signal: 'active', phase: 'done', detail: 'Router clear.', conditions: [{ label: 'No passive hijack', status: 'pass' }] },
    { id: 'pattern', signal: 'idle', phase: 'idle', detail: '0 patterns.', conditions: [{ label: 'Pattern store readable', status: 'pass' }] },
    { id: 'sync', signal: 'idle', phase: 'idle', detail: 'Sync idle.', conditions: [{ label: 'Sync idle', status: 'pass' }] },
    { id: 'orchestr', signal: 'processing', phase: 'working', detail: 'Step: package-build', conditions: [{ label: 'Sequential runtime present', status: 'pass' }] },
    { id: 'session', signal: 'idle', phase: 'idle', detail: 'No session.', conditions: [{ label: 'Session memory API present', status: 'pass' }] },
    { id: 'logger', signal: 'idle', phase: 'idle', detail: '0 telemetry.', conditions: [{ label: 'Telemetry counter available', status: 'pass' }] },
    { id: 'restore', signal: 'idle', phase: 'idle', detail: 'Restore explicit.', conditions: [{ label: 'Restore explicit only', status: 'pass' }] },
  ],
};

describe('SovereignControlFrame', () => {
  it('renders children in the fixed center chat workbench slot', () => {
    render(
      <SovereignControlFrame state={state}>
        <div data-testid="chat-workbench-child">Chat Workbench</div>
      </SovereignControlFrame>,
    );

    expect(screen.getByTestId('sovereign-control-frame')).toHaveAttribute('data-layout', 'control-frame-around-chat-workbench');
    expect(screen.getByTestId('control-frame-center-chat-workbench')).toContainElement(screen.getByTestId('chat-workbench-child'));
    expect(screen.getByTestId('control-frame-bottom-nav')).toBeDefined();
    expect(screen.getByText('Sovereign Control')).toBeDefined();
  });

  describe('Palette Accessibility Enhancements', () => {
    it('Runtime panel toggle button has title and aria-label', () => {
      render(
        <SovereignControlFrame state={state}>
          <div>Content</div>
        </SovereignControlFrame>
      );

      // Default state: open
      const toggleButton = screen.getByRole('button', { name: /Close runtime panel/i });
      expect(toggleButton).toHaveAttribute('aria-label', 'Close runtime panel');
      expect(toggleButton).toHaveAttribute('title', 'Close runtime panel');

      fireEvent.click(toggleButton);
      expect(toggleButton).toHaveAttribute('aria-label', 'Open runtime panel');
      expect(toggleButton).toHaveAttribute('title', 'Open runtime panel');
    });

    it('Module navigation buttons have title and aria-label', () => {
      render(
        <SovereignControlFrame state={state}>
          <div>Content</div>
        </SovereignControlFrame>
      );

      state.modules.forEach(module => {
        const moduleButton = screen.getByRole('button', { name: module.id.toUpperCase() });
        expect(moduleButton).toHaveAttribute('aria-label', module.id.toUpperCase());
        expect(moduleButton).toHaveAttribute('title', module.id.toUpperCase());
      });
    });
  });
});
