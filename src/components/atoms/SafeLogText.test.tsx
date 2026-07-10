import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { SafeLogText } from './SafeLogText';

describe('SafeLogText', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete (window as any).SovereignBridge;
  });

  it('renders masked text when isSensitive is true', () => {
    const { container } = render(<SafeLogText text="my-secret-password" isSensitive={true} />);
    expect(container.textContent).toBe('********');
  });

  it('redacts secrets even when isSensitive is false (defense-in-depth)', () => {
    const githubToken = 'ghp_1234567890abcdefghijklmnopqrstuvwxyz';
    // Use a string that triggers both specific and label-based masking
    const { container } = render(<SafeLogText text={`Token: ${githubToken}`} isSensitive={false} />);
    // Label-based masking (Token: ****) is prioritized/applied
    expect(container.textContent).toBe('Token: ****');
    expect(container.textContent).not.toContain(githubToken);
  });

  it('redacts multiple secrets in one string', () => {
    // String that only triggers specific patterns, not label-based (no colons/equals)
    const text = 'key is ghp_1111111111 and also sk-22222222222222222222';
    const { container } = render(<SafeLogText text={text} isSensitive={false} />);
    expect(container.textContent).toContain('ghp_****');
    expect(container.textContent).toContain('sk-****');
  });

  it('transmits masked data to SovereignBridge when hardening is enabled', () => {
    const reportMock = vi.fn();
    (window as any).SovereignBridge = {
      captureDeviceTraces: () => 'test-trace',
      reportHardenedError: reportMock,
    };

    const sensitiveText = 'Secret ghp_1234567890';
    render(<SafeLogText text={sensitiveText} isSensitive={true} enableHardening={true} />);

    expect(reportMock).toHaveBeenCalled();
    const payload = JSON.parse(reportMock.mock.calls[0][0]);
    expect(payload.data).toBe('Secret ghp_****');
    expect(payload.data).not.toContain('ghp_1234567890');
  });

  it('masks errors during bridge transmission', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    (window as any).SovereignBridge = {
      captureDeviceTraces: () => {
        throw new Error('Bridge failed with secret sk-12345678901234567890');
      },
      reportHardenedError: vi.fn(),
    };

    render(<SafeLogText text="some text" isSensitive={true} enableHardening={true} />);

    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining('Sovereign Bridge Transmission Failed: Bridge failed with secret sk-****')
    );
    expect(consoleSpy).not.toHaveBeenCalledWith(
      expect.stringContaining('sk-12345678901234567890')
    );

    consoleSpy.mockRestore();
  });
});
