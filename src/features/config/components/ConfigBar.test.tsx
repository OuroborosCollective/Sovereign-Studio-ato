import { render, screen, fireEvent, act } from '@testing-library/react';
import { ConfigBar } from './ConfigBar';
import { expect, describe, it, beforeEach, afterEach, vi } from 'vitest';
import { useConfig } from '../../../hooks/useConfig';

vi.mock('../../../hooks/useConfig');

describe('ConfigBar', () => {
  const mockUpdateConfig = vi.fn();
  const mockResetToDefaults = vi.fn();

  beforeEach(() => {
    vi.mocked(useConfig).mockReturnValue({
      config: {
        canvas: {
          resolutionScale: 1,
          fpsLimit: 60,
          showStats: false,
          bloomEnabled: true,
        },
        gemini: {
          temperature: 0.7,
          topP: 1,
          maxTokens: 2000,
          model: 'gemini-2.0-flash',
        },
      },
      updateConfig: mockUpdateConfig,
      resetToDefaults: mockResetToDefaults,
      isLoaded: true,
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  const openConfigBar = () => {
    const openBtn = screen.getByLabelText('Open Configuration');
    fireEvent.click(openBtn);
  };

  it('renders correctly', () => {
    render(<ConfigBar />);
    expect(screen.getByLabelText('Open Configuration')).toBeInTheDocument();
  });

  it('does not render if config is not loaded', () => {
    vi.mocked(useConfig).mockReturnValueOnce({
      config: {} as any,
      updateConfig: mockUpdateConfig,
      resetToDefaults: mockResetToDefaults,
      isLoaded: false,
    });
    const { container } = render(<ConfigBar />);
    expect(container.firstChild).toBeNull();
  });

  it('handles canvas state changes correctly', () => {
    render(<ConfigBar />);
    openConfigBar();

    // Test Resolution Scale
    const resolutionInput = screen.getAllByRole('slider')[0];
    fireEvent.change(resolutionInput, { target: { value: '1.5' } });

    expect(mockUpdateConfig).toHaveBeenCalledWith({
      canvas: expect.objectContaining({ resolutionScale: 1.5 })
    });

    // Test Performance Stats Toggle
    const statsButton = screen.getByText('Performance Stats').nextElementSibling as HTMLButtonElement;
    fireEvent.click(statsButton);

    expect(mockUpdateConfig).toHaveBeenCalledWith({
      canvas: expect.objectContaining({ showStats: true })
    });
  });

  it('handles gemini state changes correctly', () => {
    render(<ConfigBar />);
    openConfigBar();

    // Test Model Selection
    const modelSelect = screen.getByRole('combobox');
    fireEvent.change(modelSelect, { target: { value: 'gemini-1.5-pro' } });

    expect(mockUpdateConfig).toHaveBeenCalledWith({
      gemini: expect.objectContaining({ model: 'gemini-1.5-pro' })
    });

    // Test Temperature Slider
    const tempInput = screen.getAllByRole('slider')[1];
    fireEvent.change(tempInput, { target: { value: '0.9' } });

    expect(mockUpdateConfig).toHaveBeenCalledWith({
      gemini: expect.objectContaining({ temperature: 0.9 })
    });
  });

  it('handles reset correctly', () => {
    render(<ConfigBar />);
    openConfigBar();

    const resetButton = screen.getByText('Reset Engine Defaults');
    fireEvent.click(resetButton);

    expect(mockResetToDefaults).toHaveBeenCalled();
  });
});
