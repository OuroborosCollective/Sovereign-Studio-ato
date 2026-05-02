import { render, screen, fireEvent } from '@testing-library/react';
import { ConfigBar } from './ConfigBar';
import { expect, describe, it, beforeEach, afterEach, vi } from 'vitest';

describe('ConfigBar', () => {
  beforeEach(() => {
    vi.spyOn(console, 'log').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const openConfigBar = () => {
    const openBtn = screen.getByLabelText('Open Configuration');
    fireEvent.click(openBtn);
  };

  it('renders correctly', () => {
    render(<ConfigBar />);
    expect(screen.getByLabelText('Open Configuration')).toBeInTheDocument();
  });

  it('handles state changes correctly', () => {
    render(<ConfigBar />);
    openConfigBar();

    const applyButton = screen.getByText('Apply Changes');
    expect(applyButton).toBeDisabled(); // Initially disabled because isDirty is false

    // Change API Endpoint
    const apiEndpointInput = screen.getByLabelText('API Endpoint');
    fireEvent.change(apiEndpointInput, { target: { value: 'https://newapi.example.com' } });

    // isDirty should now be true, so apply changes should be enabled
    expect(applyButton).not.toBeDisabled();
    expect(apiEndpointInput).toHaveValue('https://newapi.example.com');

    // Test Theme select
    const themeSelect = screen.getByLabelText('Theme');
    fireEvent.change(themeSelect, { target: { value: 'dark' } });
    expect(themeSelect).toHaveValue('dark');

    // Test Range
    const retriesInput = screen.getByRole('slider');
    fireEvent.change(retriesInput, { target: { value: '5' } });
    // Value of input type range is a string and needs special assertion for some reason or just standard toHaveValue
    expect(retriesInput).toHaveValue('5');

    // Click Apply Changes
    fireEvent.click(applyButton);
    // After apply, it logs and isDirty becomes false
    expect(applyButton).toBeDisabled();

    // Check if it was saved (console.log was called)
    expect(console.log).toHaveBeenCalledWith('Saving configuration:', expect.objectContaining({
      apiEndpoint: 'https://newapi.example.com',
      theme: 'dark',
      maxRetries: 5
    }));
  });

  it('handles reset correctly', () => {
    render(<ConfigBar />);
    openConfigBar();

    const apiEndpointInput = screen.getByLabelText('API Endpoint');
    fireEvent.change(apiEndpointInput, { target: { value: 'https://newapi.example.com' } });

    const applyButton = screen.getByText('Apply Changes');
    expect(applyButton).not.toBeDisabled();

    const resetButton = screen.getByText('Reset Defaults');
    fireEvent.click(resetButton);

    // After reset, value should be default
    expect(apiEndpointInput).toHaveValue('https://api.example.com/v1');

    // Resetting sets isDirty to true
    expect(applyButton).not.toBeDisabled();
  });

  it('handles toggle buttons (autoSave, debugMode)', () => {
    render(<ConfigBar />);
    openConfigBar();

    const applyButton = screen.getByText('Apply Changes');

    const autoSaveText = screen.getByText('Auto Save Changes');
    const autoSaveButton = autoSaveText.nextElementSibling as HTMLButtonElement;

    expect(autoSaveButton).toHaveClass('bg-indigo-600'); // default is true
    fireEvent.click(autoSaveButton);
    expect(autoSaveButton).toHaveClass('bg-slate-200'); // toggled to false

    const debugModeText = screen.getByText('Debug Mode');
    const debugModeDiv = debugModeText.parentElement?.parentElement;
    const debugModeButton = debugModeDiv?.querySelector('button') as HTMLButtonElement;

    expect(debugModeButton).toHaveClass('bg-slate-300'); // default is false
    fireEvent.click(debugModeButton);
    expect(debugModeButton).toHaveClass('bg-amber-500'); // toggled to true

    expect(applyButton).not.toBeDisabled();
  });
});
