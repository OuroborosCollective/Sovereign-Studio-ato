# UI Patterns for Consent Gates

## Component Design Principles

### Clarity Over Convenience

Consent gates must be:
- **Visually prominent** - Can't be accidentally dismissed
- **Clear about consequences** - Explain what enabling means
- **Easy to deny** - No dark patterns to force acceptance
- **Verifiable** - User knows exactly what they're approving

### Anatomy of a Consent Gate

```
┌─────────────────────────────────────────┐
│  ⚠️  Warning Icon (prominent)           │
├─────────────────────────────────────────┤
│  Title (what requires consent)          │
│                                         │
│  Description (what enabling means)       │
│  - What data may be processed           │
│  - Where data may go                    │
│  - What risks exist                     │
│                                         │
│  [Attempt count or context]              │
├─────────────────────────────────────────┤
│  [Approve Button]  [Deny Button]        │
│  (Equally prominent, no dark patterns)   │
└─────────────────────────────────────────┘
```

## Basic Consent Gate Component

```typescript
import React from 'react';

interface ConsentGateProps {
  title: string;
  description: string;
  consequences?: string[];
  attempts?: number;
  onApprove: () => void;
  onDeny: () => void;
  approveLabel?: string;
  denyLabel?: string;
}

export const ConsentGate: React.FC<ConsentGateProps> = ({
  title,
  description,
  consequences = [],
  attempts,
  onApprove,
  onDeny,
  approveLabel = 'Ja, aktivieren',
  denyLabel = 'Nein, danke',
}) => (
  <div role="alertdialog" aria-modal="true" className="consent-gate">
    <div className="consent-icon">⚠️</div>
    
    <h2 className="consent-title">{title}</h2>
    
    <p className="consent-description">{description}</p>
    
    {consequences.length > 0 && (
      <ul className="consent-consequences">
        {consequences.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    )}
    
    {attempts !== undefined && (
      <div className="consent-attempts">
        Versuche: {attempts}
      </div>
    )}
    
    <div className="consent-actions">
      <button
        type="button"
        onClick={onApprove}
        className="consent-approve"
      >
        {approveLabel}
      </button>
      
      <button
        type="button"
        onClick={onDeny}
        className="consent-deny"
      >
        {denyLabel}
      </button>
    </div>
  </div>
);
```

## Styled Consent Gate (Sovereign Theme)

```typescript
const C = {
  bg: '#0e1116',
  surface: '#161c24',
  border: '#232d3a',
  amber: '#fbbf24',
  text: '#cdd9e5',
  textSub: '#768390',
  rose: '#fb7185',
} as const;

export const SovereignConsentGate: React.FC<ConsentGateProps> = (props) => (
  <div style={{
    position: 'fixed',
    inset: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'rgba(0, 0, 0, 0.8)',
    zIndex: 1000,
  }}>
    <div style={{
      background: C.surface,
      border: `1px solid ${C.border}`,
      borderRadius: 16,
      padding: 32,
      maxWidth: 480,
      width: '90%',
      boxShadow: '0 24px 48px rgba(0, 0, 0, 0.5)',
    }}>
      <div style={{
        fontSize: 48,
        textAlign: 'center',
        marginBottom: 16,
      }}>
        ⚠️
      </div>
      
      <h2 style={{
        color: C.amber,
        fontSize: 20,
        fontWeight: 600,
        textAlign: 'center',
        marginBottom: 16,
      }}>
        {props.title}
      </h2>
      
      <p style={{
        color: C.text,
        fontSize: 14,
        lineHeight: 1.6,
        marginBottom: 24,
      }}>
        {props.description}
      </p>
      
      {props.consequences && props.consequences.length > 0 && (
        <ul style={{
          color: C.textSub,
          fontSize: 13,
          marginBottom: 24,
          paddingLeft: 20,
        }}>
          {props.consequences.map((item, i) => (
            <li key={i} style={{ marginBottom: 8 }}>{item}</li>
          ))}
        </ul>
      )}
      
      {props.attempts !== undefined && (
        <div style={{
          background: `${C.rose}20`,
          border: `1px solid ${C.rose}40`,
          borderRadius: 8,
          padding: '8px 12px',
          color: C.rose,
          fontSize: 12,
          textAlign: 'center',
          marginBottom: 24,
        }}>
          Versuche: {props.attempts}
        </div>
      )}
      
      <div style={{
        display: 'flex',
        gap: 12,
      }}>
        <button
          type="button"
          onClick={props.onDeny}
          style={{
            flex: 1,
            padding: '12px 16px',
            borderRadius: 8,
            background: 'transparent',
            border: `1px solid ${C.border}`,
            color: C.text,
            fontSize: 14,
            fontWeight: 500,
            cursor: 'pointer',
          }}
        >
          {props.denyLabel}
        </button>
        
        <button
          type="button"
          onClick={props.onApprove}
          style={{
            flex: 1,
            padding: '12px 16px',
            borderRadius: 8,
            background: `${C.amber}20`,
            border: `1px solid ${C.amber}40`,
            color: C.amber,
            fontSize: 14,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          {props.approveLabel}
        </button>
      </div>
    </div>
  </div>
);
```

## Inline Consent Chip

For less intrusive consent needs:

```typescript
interface ConsentChipProps {
  label: string;
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}

export const ConsentChip: React.FC<ConsentChipProps> = ({
  label,
  enabled,
  onToggle,
}) => (
  <button
    type="button"
    onClick={() => onToggle(!enabled)}
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 8,
      padding: '6px 12px',
      borderRadius: 9999,
      background: enabled ? `${C.green}20` : `${C.border}`,
      border: `1px solid ${enabled ? C.green : C.border}`,
      color: enabled ? C.green : C.textSub,
      fontSize: 12,
      cursor: 'pointer',
    }}
  >
    <span>{enabled ? '✓' : '○'}</span>
    {label}
  </button>
);
```

## Loading State During Consent

```typescript
export const ConsentGateWithLoading: React.FC<ConsentGateProps & {
  isRetrying?: boolean;
}> = ({ isRetrying, children, ...props }) => (
  <div>
    {isRetrying ? (
      <div className="consent-loading">
        <div className="spinner" />
        <p>Autorisierung wird angewendet...</p>
      </div>
    ) : (
      <ConsentGate {...props}>
        {children}
      </ConsentGate>
    )}
  </div>
);
```

## Accessibility Considerations

### ARIA Attributes

```typescript
<div
  role="alertdialog"
  aria-modal="true"
  aria-labelledby="consent-title"
  aria-describedby="consent-description"
>
  <h2 id="consent-title">{title}</h2>
  <p id="consent-description">{fullDescription}</p>
  
  <button
    aria-describedby="approve-description"
    onClick={onApprove}
  >
    {approveLabel}
  </button>
  <span id="approve-description" hidden>
    Aktiviert externe Routen für diese Anfrage einmalig
  </span>
</div>
```

### Focus Management

```typescript
useEffect(() => {
  if (consentRequired) {
    // Focus the deny button first (safe option)
    const denyButton = document.querySelector('.consent-deny') as HTMLButtonElement;
    denyButton?.focus();
  }
}, [consentRequired]);
```

### Keyboard Navigation

Ensure buttons are reachable and Enter/Space activate them:
- Tab navigates between buttons
- Enter or Space activates focused button
- Escape does NOT close (consent requires explicit choice)

## Animation Guidelines

### Entry Animation

```css
.consent-gate {
  animation: consentSlideIn 300ms ease-out;
}

@keyframes consentSlideIn {
  from {
    opacity: 0;
    transform: scale(0.95) translateY(10px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}
```

### Warning Pulse

```css
.consent-icon {
  animation: warningPulse 2s ease-in-out infinite;
}

@keyframes warningPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
```

## Mobile Responsive

```typescript
const ConsentGateMobile: React.FC<ConsentGateProps> = (props) => (
  <div style={{
    position: 'fixed',
    inset: 0,
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'flex-end',
    padding: 16,
    background: 'rgba(0, 0, 0, 0.9)',
  }}>
    <div style={{
      background: C.surface,
      borderRadius: '24px 24px 0 0',
      padding: 24,
    }}>
      {/* Content */}
      
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}>
        <button className="consent-approve">
          {props.approveLabel}
        </button>
        <button className="consent-deny">
          {props.denyLabel}
        </button>
      </div>
    </div>
  </div>
);
```
