import { Device } from '@capacitor/device';

export interface BetaFeedbackPayload {
  userId: string;
  rating: number;
  comment: string;
  category: 'bug' | 'feature' | 'ux' | 'other';
  metadata: {
    platform: string;
    osVersion: string;
    appVersion: string;
    model: string;
    timestamp: number;
  };
}

export interface RawFeedbackInput {
  userId: string;
  rating: number;
  comment: string;
  category: BetaFeedbackPayload['category'];
}

export class BetaFeedbackService {
  private static readonly ENDPOINT = '/api/v1/internal/beta/feedback';

  /**
   * Aggregates user feedback with device context and sanitizes the input.
   */
  public async processAndSubmit(input: RawFeedbackInput): Promise<{ success: boolean; id?: string }> {
    try {
      const deviceInfo = await Device.getInfo();
      const deviceId = await Device.getId();

      const sanitizedComment = this.sanitizeString(input.comment);
      
      const payload: BetaFeedbackPayload = {
        userId: input.userId || deviceId.identifier,
        rating: Math.min(Math.max(input.rating, 1), 5),
        comment: sanitizedComment,
        category: input.category,
        metadata: {
          platform: deviceInfo.platform,
          osVersion: deviceInfo.osVersion,
          appVersion: '3.0.0-beta', // Sovereign Studio V3 Baseline
          model: deviceInfo.model,
          timestamp: Date.now(),
        },
      };

      return await this.transmit(payload);
    } catch (error) {
      console.error('[BetaFeedbackService] Failed to process feedback:', error);
      return { success: false };
    }
  }

  /**
   * Sanitizes input strings to prevent XSS or injection without using forbidden regex patterns.
   * Utilizes split/join for global replacement to comply with architectural constraints.
   */
  private sanitizeString(str: string): string {
    if (!str) return '';
    
    let sanitized = str.trim();
    
    // Replace potentially dangerous characters using split/join instead of replace(//g)
    const unsafeChars = {
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
      '/': '&#x2F;'
    };

    Object.entries(unsafeChars).forEach(([char, replacement]) => {
      sanitized = sanitized.split(char).join(replacement);
    });

    return sanitized;
  }

  /**
   * Transmits the sanitized data to the Signal-Hub aggregation endpoint.
   */
  private async transmit(payload: BetaFeedbackPayload): Promise<{ success: boolean; id?: string }> {
    const response = await fetch(BetaFeedbackService.ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Sovereign-Source': 'Beta-Tester-V3'
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`Signal-Hub rejection: ${response.statusText}`);
    }

    const result = await response.json();
    return { success: true, id: result.id };
  }
}

export const betaFeedbackService = new BetaFeedbackService();