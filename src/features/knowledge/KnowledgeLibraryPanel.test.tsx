import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { KnowledgeLibraryPanel } from './KnowledgeLibraryPanel';

const api = vi.hoisted(() => ({
  deleteKnowledgeSource: vi.fn(),
  importKnowledgeUrl: vi.fn(),
  listKnowledgeSources: vi.fn(),
  searchKnowledge: vi.fn(),
  uploadKnowledgeFile: vi.fn(),
  repairMissingKnowledgeEmbeddings: vi.fn(),
}));

vi.mock('./knowledgeApi', () => ({
  deleteKnowledgeSource: api.deleteKnowledgeSource,
  importKnowledgeUrl: api.importKnowledgeUrl,
  listKnowledgeSources: api.listKnowledgeSources,
  searchKnowledge: api.searchKnowledge,
  uploadKnowledgeFile: api.uploadKnowledgeFile,
}));

vi.mock('../inference/areInferenceApi', () => ({
  repairMissingKnowledgeEmbeddings: api.repairMissingKnowledgeEmbeddings,
}));

describe('KnowledgeLibraryPanel Markdown upload', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listKnowledgeSources.mockResolvedValue([]);
    api.uploadKnowledgeFile.mockResolvedValue({
      duplicate: false,
      blocker: null,
      source: {
        id: 'source-markdown',
        title: 'runtime.markdown',
        sourceType: 'markdown',
        sourceUrl: null,
        status: 'ready',
        blocker: null,
        chunkCount: 2,
        metadata: { extension: '.markdown', format: 'markdown' },
        createdAt: '2026-07-12T00:00:00Z',
        updatedAt: '2026-07-12T00:00:00Z',
      },
    });
  });

  it('offers all supported Markdown extensions in the real file input', async () => {
    const { container } = render(<KnowledgeLibraryPanel onClose={vi.fn()} />);

    expect(await screen.findByText('PDF, Markdown, Text oder Code hochladen')).toBeInTheDocument();
    const input = container.querySelector('input[type="file"]') as HTMLInputElement | null;

    expect(input).not.toBeNull();
    expect(input?.accept.split(',')).toEqual(expect.arrayContaining(['.md', '.markdown', '.mdx']));
  });

  it('delegates a selected Markdown file to the existing backend upload API', async () => {
    const { container } = render(<KnowledgeLibraryPanel onClose={vi.fn()} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['# Runtime Truth\n\nNever fake success.'], 'runtime.markdown', {
      type: 'text/markdown',
    });

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(api.uploadKnowledgeFile).toHaveBeenCalledWith(file, expect.any(Function)));
    expect(await screen.findByText('Gespeichert: runtime.markdown')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Gespeichert: runtime.markdown');
  });

  it('renders a correlated import failure as an alert without collapsing its evidence', async () => {
    api.importKnowledgeUrl.mockRejectedValueOnce(new Error(
      'Der serverseitige GitHub-Zugang wurde abgelehnt · GitHub HTTP 403.\n'
      + 'Fehler-ID: 3b4cd00e-506b-41ce-8d95-1d0f18a1416b · Audit: gespeichert',
    ));
    render(<KnowledgeLibraryPanel onClose={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText('GitHub- oder Wikipedia-URL'), {
      target: { value: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Importieren' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('serverseitige GitHub-Zugang wurde abgelehnt');
    expect(alert).toHaveTextContent('GitHub HTTP 403');
    expect(alert).toHaveTextContent('Fehler-ID: 3b4cd00e-506b-41ce-8d95-1d0f18a1416b');
    expect(alert).toHaveTextContent('Audit: gespeichert');
  });
});
