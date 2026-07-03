import { describe, it, expect, vi, beforeAll, afterAll } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { ThoughtBubble } from './ThoughtBubble';

describe('ThoughtBubble Palette Enhancements', () => {
  const longText = 'This is a very long text that should definitely be truncated when the thought bubble is closed because it exceeds ninety-six characters.';

  beforeAll(() => {
    vi.useFakeTimers();
  });

  afterAll(() => {
    vi.useRealTimers();
  });

  it('renders with correct initial accessibility attributes', () => {
    render(<ThoughtBubble text={longText} />);
    const button = screen.getByRole('button');
    // aria-expanded should be false initially
    expect(button).toHaveAttribute('aria-expanded', 'false');
    // title should be "Gedanken ausklappen"
    expect(button).toHaveAttribute('title', 'Gedanken ausklappen');
  });

  it('toggles accessibility attributes when clicked', () => {
    render(<ThoughtBubble text={longText} />);
    const button = screen.getByRole('button');

    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'true');
    expect(button).toHaveAttribute('title', 'Gedanken einklappen');

    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(button).toHaveAttribute('title', 'Gedanken ausklappen');
  });

  it('toggles between truncated and full text', () => {
    render(<ThoughtBubble text={longText} />);

    // Fast-forward timers to complete the initial "typing" animation
    act(() => {
      vi.advanceTimersByTime(5000);
    });

    // Initial state (truncated)
    // We check for the ellipsis character "…"
    expect(screen.getByText(/…/)).toBeTruthy();

    const button = screen.getByRole('button');
    fireEvent.click(button);

    // Expanded state
    expect(screen.queryByText(/…/)).toBeNull();
    expect(screen.getByText(longText)).toBeTruthy();
  });

  it('ensures decorative icon is hidden from screen readers', () => {
    render(<ThoughtBubble text={longText} />);
    const icon = screen.getByText('✦');
    expect(icon).toHaveAttribute('aria-hidden', 'true');
  });
});
