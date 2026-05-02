import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { Header } from './Header';

describe('Header Component', () => {
  const defaultProps = {
    loadingTree: false,
    setShowPrivacy: vi.fn(),
    handleCleanup: vi.fn(),
    fetchRepoTree: vi.fn(),
  };

  it('renders the header title', () => {
    render(<Header {...defaultProps} />);
    expect(screen.getByText('SOVEREIGN')).toBeInTheDocument();
    expect(screen.getByText('_STUDIO')).toBeInTheDocument();
  });

  it('renders buttons correctly', () => {
    render(<Header {...defaultProps} />);
    expect(screen.getByText('DATENSCHUTZ')).toBeInTheDocument();
    expect(screen.getByText('CLEANUP')).toBeInTheDocument();
    expect(screen.getByText('REFRESH')).toBeInTheDocument();
  });

  it('calls setShowPrivacy when privacy button is clicked', () => {
    render(<Header {...defaultProps} />);
    fireEvent.click(screen.getByText('DATENSCHUTZ'));
    expect(defaultProps.setShowPrivacy).toHaveBeenCalledWith(true);
  });

  it('calls handleCleanup when cleanup button is clicked', () => {
    render(<Header {...defaultProps} />);
    fireEvent.click(screen.getByText('CLEANUP'));
    expect(defaultProps.handleCleanup).toHaveBeenCalled();
  });

  it('calls fetchRepoTree when refresh button is clicked', () => {
    render(<Header {...defaultProps} />);
    fireEvent.click(screen.getByText('REFRESH'));
    expect(defaultProps.fetchRepoTree).toHaveBeenCalled();
  });

  it('displays loading state and disables refresh button when loadingTree is true', () => {
    render(<Header {...defaultProps} loadingTree={true} />);
    const refreshButton = screen.getByRole('button', { name: /laden/i });
    expect(refreshButton).toBeInTheDocument();
    expect(refreshButton).toBeDisabled();
  });
});
