import { geminiService } from './geminiService';

describe('geminiService', () => {
  const mockApiKey = 'test-api-key';
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv, NEXT_PUBLIC_GEMINI_API_KEY: mockApiKey };
    global.fetch = jest.fn();
  });

  afterEach(() => {
    process.env = originalEnv;
    jest.clearAllMocks();
  });

  it('sollte eine erfolgreiche Antwort vom Gemini Service verarbeiten', async () => {
    const mockResponse = {
      candidates: [
        {
          content: {
            parts: [{ text: 'Dies ist eine KI-Antwort.' }],
          },
        },
      ],
    };

    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => mockResponse,
    });

    const result = await geminiService.generateContent('Hallo Welt');

    expect(result).toBe('Dies ist eine KI-Antwort.');
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('generativelanguage.googleapis.com'),
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
        }),
      })
    );
  });

  it('sollte einen Fehler werfen, wenn die API-Antwort nicht ok ist', async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
    });

    await expect(geminiService.generateContent('Test')).rejects.toThrow(
      'Gemini API Fehler: 400 Bad Request'
    );
  });

  it('sollte Fehler bei Netzwerkproblemen abfangen', async () => {
    (global.fetch as jest.Mock).mockRejectedValueOnce(new Error('Network Error'));

    await expect(geminiService.generateContent('Test')).rejects.toThrow('Network Error');
  });

  it('sollte mit leeren Kandidaten-Listen in der Antwort umgehen können', async () => {
    const emptyResponse = { candidates: [] };

    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => emptyResponse,
    });

    await expect(geminiService.generateContent('Test')).rejects.toThrow();
  });
});