// Export all components
export { MatrixChat } from './MatrixChat';
export { GitHubExplorer } from './GitHubExplorer';
export { SettingsScreen } from './SettingsScreen';
export { CanvasEditor } from './CanvasEditor';

// Export all screens
export { HomeScreen } from '../screens/HomeScreen';
export { ChatScreen } from '../screens/ChatScreen';
export { ExplorerScreen } from '../screens/ExplorerScreen';
export { SettingsScreenWrapper } from '../screens/SettingsScreenWrapper';
export { CanvasScreen } from '../screens/CanvasScreen';

// Export utils
export { Colors, Spacing, BorderRadius, FontSize, FontWeight, Shadows, CommonStyles } from '../utils/theme';

// Export types
export type * from '../types';

// Export store
export { useAppStore } from '../store/appStore';

// Export AI features
export { 
  providerManager, 
  geminiService, 
  runAwarenessSync,
  FREE_PROVIDERS,
  PROVIDER_INFO,
} from '../features/ai/providerManager';