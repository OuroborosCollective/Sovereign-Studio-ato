import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SafeLogText } from './SafeLogText';
import React from 'react';

describe('SafeLogText', () => {
  it('redacts secrets even when isSensitive is false (defense-in-depth)', () => {
    // Note: The maskSecrets pattern for ghp_ is:
    // masked = masked.replace(/(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9_]{8,100}/g, '$1_****');
    // If the input is "Token: ghp_1234567890", it matches "ghp_1234567890"
    // $1 is "ghp", so it becomes "Token: ghp_****"
    // WAIT, the error output showed "Token: ****"
    // Let's check why.

    const secret = 'ghp_1234567890abcdefghijklmnopqrstuvwxyz';
    render(<SafeLogText text={`Token: ${secret}`} isSensitive={false} />);

    expect(screen.queryByText(secret)).not.toBeInTheDocument();
    // Re-check the output: "Token: ****" suggests ghp_ was also consumed by another rule or the regex didn't capture ghp as $1.
    // Label-based rule: /(["']?)(password|passwd|token|secret|api[_-]?key|access[_-]?token|private[_-]?key)\1(\s*[:=]\s*)["']?[a-zA-Z0-9_@#$%^&*.\-~+/=]+["']?/gi
    // "Token: ghp_..." matches this rule!
    // $1="", $2="Token", $3=": "
    // Replacement: $1$2$1$3**** -> "Token: ****"

    expect(screen.getByText('Token: ****')).toBeInTheDocument();
  });

  it('redacts label-based secrets when isSensitive is false', () => {
    const secret = 'password: "my-secret-password"';
    render(<SafeLogText text={secret} isSensitive={false} />);

    expect(screen.queryByText('my-secret-password')).not.toBeInTheDocument();
    expect(screen.getByText('password: ****')).toBeInTheDocument();
  });

  it('redacts everything when isSensitive is true', () => {
    const secret = 'ghp_1234567890abcdefghijklmnopqrstuvwxyz';
    render(<SafeLogText text={`Token: ${secret}`} isSensitive={true} />);

    expect(screen.queryByText(secret)).not.toBeInTheDocument();
    expect(screen.getByText('********')).toBeInTheDocument();
  });

  it('masks error messages when bridge transmission fails', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const secret = 'sk-or-v1-1234567890abcdefghijklmnopqrstuvwxyz';

    // Setup bridge that throws an error containing a secret
    window.SovereignBridge = {
      captureDeviceTraces: () => { throw new Error(`Failed with key ${secret}`); },
      reportHardenedError: () => {}
    };

    render(<SafeLogText text="some text" isSensitive={true} />);

    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('Sovereign Bridge Transmission Failed'));
    expect(consoleSpy).toHaveBeenCalledWith(expect.not.stringContaining(secret));
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('sk-or-v1-****'));

    consoleSpy.mockRestore();
    delete (window as any).SovereignBridge;
  });
});
