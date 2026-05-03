import { describe, it, expect } from 'vitest';
import { GeminiService } from './gemini';

describe('GeminiService', () => {
  it('should be defined', () => {
    expect(GeminiService).toBeDefined();
  });

  it('should generate content using string arguments for instructions and config', async () => {
    const service = new GeminiService('test-api-key');
    
    // Passing string arguments instead of objects for system instructions and configuration
    const response = await service.generateContent(
      'Explain quantum computing',
      'You are a physics professor',
      'gemini-1.5-pro'
    );

    expect(response).toBeDefined();
  });
});