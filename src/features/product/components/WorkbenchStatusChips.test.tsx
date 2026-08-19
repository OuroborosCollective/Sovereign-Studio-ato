/**
 * WorkbenchStatusChips accessibility tests (Issue #1567, findings E4/B3)
 * - Essential status text must be at least 12px (mobile readability)
 * - State must never be conveyed by color alone: icon with role="img" + aria-label
 * - Red is reserved exclusively for error/failure/critical tones
 */

import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import { WorkbenchStatusChips } from './WorkbenchStatusChips';
import type { WorkbenchStatusSlot } from '../runtime/builderWorkbenchStatus';
import { C } from './builderConstants';

function makeSlot(overrides: Partial<WorkbenchStatusSlot>): WorkbenchStatusSlot {
  return {
    id: 'logs',
    label: 'LOGGER',
    value: 'aktiv',
    tone: 'neutral',
    items: [],
    emptyLabel: 'leer',
    ...overrides,
  };
}

describe('WorkbenchStatusChips accessibility', () => {
  it('renders status text at least 12px', () => {
    const { getByRole } = render(
      <WorkbenchStatusChips slots={[makeSlot({})]} onSlotClick={() => {}} />,
    );
    const chip = getByRole('button', { name: /LOGGER/ });
    const fontSize = parseFloat(chip.style.fontSize);
    expect(fontSize).toBeGreaterThanOrEqual(12);
  });

  it('exposes the tone as an accessible icon label, not color alone', () => {
    const { getByRole } = render(
      <WorkbenchStatusChips slots={[makeSlot({ tone: 'error', id: 'errors', label: 'FEHLER', value: '2' })]} onSlotClick={() => {}} />,
    );
    const icon = getByRole('img', { name: /fehler|error|kritisch/i });
    expect(icon).toBeTruthy();
  });

  it('does not use red for non-error tones', () => {
    const tones: Array<WorkbenchStatusSlot['tone']> = ['neutral', 'positive', 'warning'];
    for (const tone of tones) {
      const { getByRole, unmount } = render(
        <WorkbenchStatusChips slots={[makeSlot({ tone })]} onSlotClick={() => {}} />,
      );
      const chip = getByRole('button', { name: /LOGGER/ });
      expect(chip.style.color.toLowerCase()).not.toBe(C.rose.toLowerCase());
      unmount();
    }
  });

  it('keeps click behaviour intact', () => {
    const onSlotClick = vi.fn();
    const { getByRole } = render(
      <WorkbenchStatusChips slots={[makeSlot({})]} onSlotClick={onSlotClick} />,
    );
    getByRole('button', { name: /LOGGER/ }).click();
    expect(onSlotClick).toHaveBeenCalledWith('logs');
  });
});
