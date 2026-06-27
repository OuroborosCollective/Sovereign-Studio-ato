import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import posthog from 'posthog-js';
import App from './SovereignAppWrapper';
import { ErrorBoundary } from './components/ErrorBoundary';
import { installGlobalRuntimeMonitor } from './global-runtime-monitor';
import { flushCanvasStateMirror, restoreCanvasStateMirror } from './store';
import {
  SOVEREIGN_WORKSPACE_COMMAND_EVENT,
  isSovereignWorkspaceTab,
  normalizeSovereignWorkspaceCommandDetail,
  type SovereignWorkspaceCommandDetail,
} from './features/product/runtime/sovereignWorkspaceCommand';
import './runtime-adapter';
import './index.css';
import './styles/arelogic-brand.css';
import './styles/sovereign-release-guide.css';
import './styles/sovereign-playtest-ux.css';
import './styles/sovereign-responsive-ux.css';

/* rest of file unchanged */
