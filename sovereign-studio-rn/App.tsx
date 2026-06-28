import React, { useCallback, useMemo, useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';

import { HomeScreen } from './src/screens/HomeScreen';
import { ChatScreen } from './src/screens/ChatScreen';
import { ExplorerScreen } from './src/screens/ExplorerScreen';
import { SettingsScreenWrapper } from './src/screens/SettingsScreenWrapper';
import { CanvasScreen } from './src/screens/CanvasScreen';
import { CodeRefactorScreen } from './src/screens/CodeRefactorScreen';
import { Colors, FontSize, Spacing } from './src/utils/theme';

// Type definitions for navigation
// Keep this tiny navigation contract local and JS-only. The mobile app only uses
// navigate() from Home today, so pulling in the native-stack/screens Android
// module for CI/E2E adds native build risk without adding required runtime value.
type RootStackRoute = 'Home' | 'Chat' | 'Explorer' | 'Settings' | 'Canvas' | 'CodeRefactor';

type RootStackParamList = Record<RootStackRoute, undefined>;

type LocalNavigation = {
  navigate: (routeName: RootStackRoute) => void;
  goBack: () => void;
  canGoBack: () => boolean;
};

const ROUTE_TITLES: Record<RootStackRoute, string> = {
  Home: 'SOVEREIGN STUDIO',
  Chat: 'AGENT WORKSPACE',
  Explorer: 'GITHUB EXPLORER',
  Settings: 'SETTINGS',
  Canvas: 'CANVAS EDITOR',
  CodeRefactor: 'CODE REFACTOR',
};

export default function App() {
  const [routeStack, setRouteStack] = useState<RootStackRoute[]>(['Home']);
  const currentRoute = routeStack[routeStack.length - 1] ?? 'Home';

  const navigate = useCallback((routeName: RootStackRoute) => {
    setRouteStack((previousStack) => [...previousStack, routeName]);
  }, []);

  const goBack = useCallback(() => {
    setRouteStack((previousStack) => (
      previousStack.length > 1 ? previousStack.slice(0, -1) : previousStack
    ));
  }, []);

  const canGoBack = useCallback(() => routeStack.length > 1, [routeStack.length]);

  const navigation = useMemo<LocalNavigation>(() => ({
    navigate,
    goBack,
    canGoBack,
  }), [canGoBack, goBack, navigate]);

  const screen = useMemo(() => {
    const props = { navigation };

    switch (currentRoute) {
      case 'Chat':
        return <ChatScreen {...props} />;
      case 'Explorer':
        return <ExplorerScreen {...props} />;
      case 'Settings':
        return <SettingsScreenWrapper {...props} />;
      case 'Canvas':
        return <CanvasScreen {...props} />;
      case 'CodeRefactor':
        return <CodeRefactorScreen {...props} />;
      case 'Home':
      default:
        return <HomeScreen {...props} />;
    }
  }, [currentRoute, navigation]);

  return (
    <View style={styles.container}>
      <StatusBar style="light" />
      {currentRoute !== 'Home' && (
        <View style={styles.header}>
          <TouchableOpacity
            accessibilityRole="button"
            accessibilityLabel="Back"
            onPress={goBack}
            style={styles.backButton}
          >
            <Text style={styles.backButtonText}>‹ Back</Text>
          </TouchableOpacity>
          <Text style={styles.headerTitle} numberOfLines={1}>{ROUTE_TITLES[currentRoute]}</Text>
          <View style={styles.headerSpacer} />
        </View>
      )}
      <View style={styles.screen}>{screen}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  screen: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  header: {
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderBottomColor: Colors.border,
    borderBottomWidth: 1,
    flexDirection: 'row',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
  },
  backButton: {
    minWidth: 76,
    paddingVertical: Spacing.xs,
  },
  backButtonText: {
    color: Colors.primary,
    fontSize: FontSize.sm,
    fontWeight: '600',
  },
  headerTitle: {
    color: Colors.primary,
    flex: 1,
    fontSize: FontSize.md,
    fontWeight: '600',
    textAlign: 'center',
  },
  headerSpacer: {
    width: 76,
  },
});
