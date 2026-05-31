import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { StatusBar } from 'expo-status-bar';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { HomeScreen } from './src/screens/HomeScreen';
import { ChatScreen } from './src/screens/ChatScreen';
import { ExplorerScreen } from './src/screens/ExplorerScreen';
import { SettingsScreenWrapper } from './src/screens/SettingsScreenWrapper';
import { CanvasScreen } from './src/screens/CanvasScreen';
import { Colors, FontSize, Spacing, BorderRadius } from './src/utils/theme';

// Type definitions for navigation
type RootStackParamList = {
  Home: undefined;
  Chat: undefined;
  Explorer: undefined;
  Settings: undefined;
  Canvas: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

// Simple tab bar icon component
const TabIcon = ({ name, focused }: { name: string; focused: boolean }) => (
  <Ionicons
    name={name as any}
    size={24}
    color={focused ? Colors.primary : Colors.textMuted}
  />
);

export default function App() {
  return (
    <View style={styles.container}>
      <StatusBar style="light" />
      <NavigationContainer>
        <Stack.Navigator
          screenOptions={{
            headerStyle: {
              backgroundColor: Colors.surface,
            },
            headerTintColor: Colors.primary,
            headerTitleStyle: {
              fontWeight: '600',
              fontSize: FontSize.md,
            },
            contentStyle: {
              backgroundColor: Colors.background,
            },
          }}
        >
          <Stack.Screen
            name="Home"
            component={HomeScreen}
            options={{
              headerShown: false,
            }}
          />
          <Stack.Screen
            name="Chat"
            component={ChatScreen}
            options={{
              title: 'AGENT WORKSPACE',
              headerBackTitle: 'Back',
            }}
          />
          <Stack.Screen
            name="Explorer"
            component={ExplorerScreen}
            options={{
              title: 'GITHUB EXPLORER',
              headerBackTitle: 'Back',
            }}
          />
          <Stack.Screen
            name="Settings"
            component={SettingsScreenWrapper}
            options={{
              title: 'SETTINGS',
              headerBackTitle: 'Back',
            }}
          />
          <Stack.Screen
            name="Canvas"
            component={CanvasScreen}
            options={{
              title: 'CANVAS EDITOR',
              headerBackTitle: 'Back',
            }}
          />
        </Stack.Navigator>
      </NavigationContainer>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
});