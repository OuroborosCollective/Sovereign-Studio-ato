import { Device } from '@capacitor/device';

/**
 * Interface for the sanitized feedback payload sent to the Signal-Hub.
 */
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

/**
 * Interface for raw user input before processing.
 */
export interface RawFeedbackInput {
  userId?: string;
  rating: number;
  comment: string;
  category: BetaFeedbackPayload['category'];
}

/**
 * BetaFeedbackService
 * Handles the collection, sanitization, and transmission of beta tester feedback.
 * Integrates with Capacitor 6 Device plugin for environment context.
 */
export class BetaFeedbackService {
  private static readonly ENDPOINT = '/api/v1/internal/beta/feedback';
  private static readonly APP_VERSION = '3.0.0-beta-sovereign';

  /**
   * Processes raw input, aggregates device metadata, and submits to the hub.
   * Resolves potential TS2307 issues by ensuring proper Capacitor plugin interaction.
   */
  public async processAndSubmit(input: RawFeedbackInput): Promise<{ success: boolean; id?: string }> {
    try {
      // Fetching device information via Capacitor 6 API
      const deviceInfo = await Device.getInfo();
      const deviceIdResult = await Device.getId();

      const sanitizedComment = this.sanitizeString(input.comment);
      
      const payload: BetaFeedbackPayload = {
        // Fallback to device identifier if userId is not provided
        userId: input.userId || deviceIdResult.identifier || 'anonymous-beta-user',
        rating: Math.min(Math.max(input.rating, 1), 5),
        comment: sanitizedComment,
        category: input.category,
        metadata: {
          platform: deviceInfo.platform,
          osVersion: deviceInfo.osVersion,
          appVersion: BetaFeedbackService.APP_VERSION,
          model: deviceInfo.model,
          timestamp: Date.now(),
        },
      };

      return await this.transmit(payload);
    } catch (error) {
      console.error('[BetaFeedbackService] Error during feedback processing:', error);
      return { success: false };
    }
  }

  /**
   * Sanitizes strings to mitigate injection risks without using forbidden regex patterns.
   * Employs split/join for safe global character replacement.
   */
  private sanitizeString(str: string): string {
    if (!str) return '';
    
    let sanitized = str.trim();
    
    // Character map for basic HTML entity encoding
    const unsafeChars: Record<string, string> = {
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
      '/': '&#x2F;'
    };

    // Iterate through unsafe characters and replace them
    for (const [char, replacement] of Object.entries(unsafeChars)) {
      sanitized = sanitized.split(char).join(replacement);
    }

    return sanitized;
  }

  /**
   * Transmits the feedback payload to the Signal-Hub backend.
   */
  private async transmit(payload: BetaFeedbackPayload): Promise<{ success: boolean; id?: string }> {
    try {
      const response = await fetch(BetaFeedbackService.ENDPOINT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Sovereign-Source': 'Studio-Beta-Feedback',
          'X-Sovereign-Timestamp': Date.now().toString()
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Signal-Hub rejected transmission (${response.status}): ${errorText}`);
      }

      const result = await response.json();
      return { 
        success: true, 
        id: result.id || `feedback-${Date.now()}` 
      };
    } catch (error) {
      console.error('[BetaFeedbackService] Transmission failure:', error);
      // We do not re-throw here to allow the UI to handle the boolean result gracefully
      return { success: false };
    }
  }
}

// Export as a singleton instance for global use within the Studio environment
export const betaFeedbackService = new BetaFeedbackService();