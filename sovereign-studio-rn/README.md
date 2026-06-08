# Sovereign Studio React Native App

**AI-Powered Product Builder for Android**

A complete rebuild of the Sovereign Studio application using React Native (TypeScript) for Android. This app provides an AI-powered development environment with multi-provider LLM support, GitHub repository exploration, and a Matrix-style chat interface.

## Features

### 🤖 AI-Powered Product Builder
- Multi-provider LLM support with automatic fallback
- Awareness sync for repository analysis
- Living product preview with cards system

### 💬 Matrix Chat Interface
- Dark cyberpunk theme with emerald green accents
- Real-time AI responses
- Provider status indicators

### 📁 GitHub Explorer
- Repository URL input and parsing
- File tree visualization
- File selection and navigation

### ⚙️ Settings & Configuration
- API key management for multiple providers
- Project settings (repo mode, package manager, linter)
- Max fix loops configuration

### 🎨 Canvas Editor
- Visual card-based workflow
- Drag-and-drop interface
- Grid overlay background

## Supported LLM Providers

| Provider | API Key Required | Free Tier |
|----------|------------------|-----------|
| **MLVOCA** | ❌ No | ✓ Yes |
| **Groq** | ✅ Yes | ✓ Yes |
| **HuggingFace** | ✅ Yes | ✓ Yes |
| **Together AI** | ✅ Yes | ✓ Yes |
| **OpenRouter** | ✅ Yes | ✓ Yes |
| **Google Gemini** | ✅ Yes | ❌ No |

## Installation

### Prerequisites
- Node.js >= 22
- npm >= 10
- Expo CLI (`npx expo`)
- Android Studio (for native builds)

### Setup

1. Install dependencies:
```bash
npm install
```

2. Start development:
```bash
npm start
```

3. Run on Android:
```bash
npm run android
```

## Build for Android

### Development Build
```bash
npx expo prebuild
cd android
./gradlew assembleDebug
```

### Production Build (AAB/APK)
```bash
npm run build:android
```

Or use EAS:
```bash
eas build -p android --profile production
```

## Project Structure

```
sovereign-studio-rn/
├── App.tsx                 # Main app with navigation
├── app.json                # Expo configuration
├── package.json            # Dependencies
├── eas.json                # EAS Build config
├── babel.config.js         # Babel config
├── metro.config.js         # Metro bundler config
├── tsconfig.json           # TypeScript config
├── assets/                 # App icons and splash
├── src/
│   ├── components/         # UI Components
│   │   ├── MatrixChat.tsx   # Matrix-style chat
│   │   ├── GitHubExplorer.tsx # GitHub file explorer
│   │   ├── SettingsScreen.tsx  # Configuration screen
│   │   └── CanvasEditor.tsx    # Visual canvas editor
│   ├── screens/            # App screens
│   │   ├── HomeScreen.tsx
│   │   ├── ChatScreen.tsx
│   │   ├── ExplorerScreen.tsx
│   │   ├── SettingsScreenWrapper.tsx
│   │   └── CanvasScreen.tsx
│   ├── features/           # Feature modules
│   │   └── ai/
│   │       └── providerManager.ts # LLM provider system
│   ├── store/              # State management
│   │   └── appStore.ts     # Zustand store
│   ├── types/              # TypeScript types
│   │   └── index.ts
│   └── utils/              # Utilities
│       └── theme.ts        # Matrix dark theme
└── .github/
    └── workflows/          # CI/CD pipelines
        └── android-release.yml
```

## CI/CD Pipeline

The project includes a GitHub Actions workflow for Android release builds:

1. **Build AAB (Android App Bundle)** - For Play Store upload
2. **Build APK (Universal)** - For direct distribution
3. **Artifact Upload** - ZIP file with AAB/APK and version info

### Required Secrets
- `ANDROID_KEYSTORE_BASE64` - Base64 encoded keystore
- `ANDROID_KEYSTORE_PASSWORD` - Keystore password
- `ANDROID_KEY_ALIAS` - Key alias name

## Design System

### Matrix Dark Theme
- Background: `#0a0a0a`
- Primary (Matrix Green): `#10b981`
- Surface: `#141414`
- Accent: `#8b5cf6`
- Text: `#e5e5e5`

### Typography
- Headers: Bold, letter-spacing
- Body: Regular, 14-16px
- Code: Monospace

## Tech Stack

- **Framework**: React Native + Expo SDK 52
- **Language**: TypeScript
- **Navigation**: React Navigation 7 (Native Stack)
- **State Management**: Zustand 5
- **LLM Integration**: Google Generative AI SDK
- **Icons**: Ionicons (Expo)
- **Styling**: StyleSheet (native)

## License

MIT © Ouroboros Collective