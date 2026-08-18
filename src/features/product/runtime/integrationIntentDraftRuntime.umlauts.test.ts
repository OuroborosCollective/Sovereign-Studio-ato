import { describe, expect, it } from 'vitest';
import {
  createIntegrationIntentDraft,
  buildDraftConfirmedEvent,
} from './integrationIntentDraftRuntime';

describe('German umlaut handling (mojibake regression)', () => {
  it('classifies "ändern" missions with the change goal', () => {
    // Arrange / Act
    const draft = createIntegrationIntentDraft('Ändere den Button in der Oberfläche auf cyan');

    // Assert
    if (!draft) throw new Error('Draft should not be null');
    expect(draft.goal).toBe('Bestehende Funktionalität ändern');
    expect(draft.scope).toContain('UI/Komponenten');
  });

  it('strips polite prefixes with umlauts from the title', () => {
    // Arrange / Act
    const draft = createIntegrationIntentDraft('Könntest du die README aktualisieren');

    // Assert
    if (!draft) throw new Error('Draft should not be null');
    expect(draft.title).toBe('Die README aktualisieren');
  });

  it('classifies "löschen" missions with the removal goal', () => {
    // Arrange / Act
    const draft = createIntegrationIntentDraft('Lösche den ungenutzten Onboarding-Dialog aus der App');

    // Assert
    if (!draft) throw new Error('Draft should not be null');
    expect(draft.goal).toBe('Funktionalität entfernen');
  });

  it('emits a correctly encoded confirm label', () => {
    // Arrange
    const draft = createIntegrationIntentDraft('Baue einen Draft PR für die README', undefined, { now: 1700000000000, idSeed: 'enc-1' });
    if (!draft) throw new Error('Draft should not be null');

    // Act
    const event = buildDraftConfirmedEvent(draft);

    // Assert
    expect(event.label).toBe('Integrationsauftrag bestätigt');
    expect(event.label).not.toContain('Г');
  });
});
