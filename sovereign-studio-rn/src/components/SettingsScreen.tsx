import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  Switch,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, BorderRadius, FontSize } from '../../utils/theme';
import type { ProviderType } from '../../types';
import { PROVIDER_INFO } from '../../features/ai/providerManager';

interface SettingsScreenProps {
  geminiKey: string;
  onGeminiKeyChange: (key: string) => void;
  githubToken: string;
  onGithubTokenChange: (key: string) => void;
  groqKey: string;
  onGroqKeyChange: (key: string) => void;
  hfKey: string;
  onHfKeyChange: (key: string) => void;
  togetherKey: string;
  onTogetherKeyChange: (key: string) => void;
  openrouterKey: string;
  onOpenrouterKeyChange: (key: string) => void;
  settings: any;
  onSettingsChange: (settings: any) => void;
}

export const SettingsScreen: React.FC<SettingsScreenProps> = ({
  geminiKey,
  onGeminiKeyChange,
  githubToken,
  onGithubTokenChange,
  groqKey,
  onGroqKeyChange,
  hfKey,
  onHfKeyChange,
  togetherKey,
  onTogetherKeyChange,
  openrouterKey,
  onOpenrouterKeyChange,
  settings,
  onSettingsChange,
}) => {
  const [showKeys, setShowKeys] = useState(false);

  const getProviderIcon = (provider: ProviderType) => {
    switch (provider) {
      case 'gemini': return '🌟';
      case 'groq': return '⚡';
      case 'mlvoca': return '🔮';
      case 'huggingface': return '🤗';
      case 'together': return '🎯';
      case 'openrouter': return '🌐';
      default: return '🤖';
    }
  };

  const renderApiKeyInput = (
    label: string,
    provider: ProviderType,
    value: string,
    onChange: (text: string) => void,
    isFree: boolean
  ) => (
    <View style={styles.keyInputContainer}>
      <View style={styles.keyLabel}>
        <Text style={styles.keyEmoji}>{getProviderIcon(provider)}</Text>
        <View style={styles.keyLabelText}>
          <Text style={styles.keyName}>{label}</Text>
          {isFree && (
            <View style={styles.freeBadge}>
              <Text style={styles.freeBadgeText}>FREE</Text>
            </View>
          )}
        </View>
      </View>
      <View style={styles.inputWrapper}>
        <TextInput
          style={[styles.keyInput, !isFree && styles.keyInputRequired]}
          value={value}
          onChangeText={onChange}
          placeholder={isFree ? 'Optional (kein Key nötig)' : 'API Key eingeben...'}
          placeholderTextColor={Colors.textMuted}
          secureTextEntry={!showKeys}
          autoCapitalize="none"
          autoCorrect={false}
        />
        {value.length > 0 && (
          <TouchableOpacity
            style={styles.visibilityToggle}
            onPress={() => setShowKeys(!showKeys)}
          >
            <Ionicons
              name={showKeys ? 'eye-off' : 'eye'}
              size={18}
              color={Colors.textSecondary}
            />
          </TouchableOpacity>
        )}
      </View>
      <Text style={styles.keyStatus}>
        {value.trim() ? '✓ Konfiguriert' : isFree ? '○ Kein Key nötig' : '✗ Nicht konfiguriert'}
      </Text>
    </View>
  );

  return (
    <ScrollView style={styles.container} showsVerticalScrollIndicator={false}>
      {/* Header */}
      <View style={styles.header}>
        <Ionicons name="settings" size={24} color={Colors.primary} />
        <Text style={styles.headerTitle}>SYSTEM ENGINE</Text>
        <Text style={styles.headerSubtitle}>Konfiguration & Parameter</Text>
      </View>

      {/* LLM Providers Section */}
      <View style={styles.section}>
        <View style={styles.sectionHeader}>
          <Ionicons name="chatbubbles" size={16} color={Colors.primary} />
          <Text style={styles.sectionTitle}>LLM PROVIDER</Text>
        </View>
        
        {renderApiKeyInput('Google Gemini', 'gemini', geminiKey, onGeminiKeyChange, false)}
        {renderApiKeyInput('Groq', 'groq', groqKey, onGroqKeyChange, true)}
        {renderApiKeyInput('HuggingFace', 'huggingface', hfKey, onHfKeyChange, true)}
        {renderApiKeyInput('Together AI', 'together', togetherKey, onTogetherKeyChange, true)}
        {renderApiKeyInput('OpenRouter', 'openrouter', openrouterKey, onOpenrouterKeyChange, true)}
        
        {/* MLVOCA Note */}
        <View style={styles.mlvocaNote}>
          <Text style={styles.mlvocaEmoji}>🔮</Text>
          <View style={styles.mlvocaText}>
            <Text style={styles.mlvocaTitle}>MLVOCA - Default Provider</Text>
            <Text style={styles.mlvocaDescription}>
              Kein API Key erforderlich! Wird automatisch verwendet, wenn keine anderen Keys konfiguriert sind.
            </Text>
          </View>
        </View>
      </View>

      {/* GitHub Token Section */}
      <View style={styles.section}>
        <View style={styles.sectionHeader}>
          <Ionicons name="logo-github" size={16} color={Colors.textSecondary} />
          <Text style={styles.sectionTitle}>GITHUB ACCESS</Text>
        </View>
        
        {renderApiKeyInput('GitHub Token (PAT)', 'gemini', githubToken, onGithubTokenChange, false)}
        
        <Text style={styles.helperText}>
          GitHub Personal Access Token für Repository-Zugriff. Benötigt repo Scope.
        </Text>
      </View>

      {/* Project Settings Section */}
      <View style={styles.section}>
        <View style={styles.sectionHeader}>
          <Ionicons name="construct" size={16} color={Colors.accent} />
          <Text style={styles.sectionTitle}>PROJEKT EINSTELLUNGEN</Text>
        </View>

        {/* Repo Mode */}
        <View style={styles.settingRow}>
          <Text style={styles.settingLabel}>Repository Mode</Text>
          <View style={styles.segmentedControl}>
            <TouchableOpacity
              style={[
                styles.segment,
                settings.repoMode === 'single' && styles.segmentActive,
              ]}
              onPress={() => onSettingsChange({ ...settings, repoMode: 'single' })}
            >
              <Text style={[
                styles.segmentText,
                settings.repoMode === 'single' && styles.segmentTextActive,
              ]}>Single</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[
                styles.segment,
                settings.repoMode === 'monorepo' && styles.segmentActive,
              ]}
              onPress={() => onSettingsChange({ ...settings, repoMode: 'monorepo' })}
            >
              <Text style={[
                styles.segmentText,
                settings.repoMode === 'monorepo' && styles.segmentTextActive,
              ]}>Monorepo</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Package Manager */}
        <View style={styles.settingRow}>
          <Text style={styles.settingLabel}>Package Manager</Text>
          <View style={styles.pillGroup}>
            {['auto', 'npm', 'pnpm', 'yarn', 'bun'].map((pm) => (
              <TouchableOpacity
                key={pm}
                style={[
                  styles.pill,
                  settings.packageManager === pm && styles.pillActive,
                ]}
                onPress={() => onSettingsChange({ ...settings, packageManager: pm })}
              >
                <Text style={[
                  styles.pillText,
                  settings.packageManager === pm && styles.pillTextActive,
                ]}>
                  {pm.toUpperCase()}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* Linter */}
        <View style={styles.settingRow}>
          <Text style={styles.settingLabel}>Linter</Text>
          <View style={styles.pillGroup}>
            {['auto', 'eslint', 'biome', 'prettier-eslint'].map((linter) => (
              <TouchableOpacity
                key={linter}
                style={[
                  styles.pill,
                  settings.linter === linter && styles.pillActive,
                ]}
                onPress={() => onSettingsChange({ ...settings, linter: linter })}
              >
                <Text style={[
                  styles.pillText,
                  settings.linter === linter && styles.pillTextActive,
                ]}>
                  {linter.toUpperCase()}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* Max Fix Loops */}
        <View style={styles.settingRow}>
          <Text style={styles.settingLabel}>Max Fix Loops</Text>
          <View style={styles.counterContainer}>
            <TouchableOpacity
              style={styles.counterButton}
              onPress={() => onSettingsChange({ 
                ...settings, 
                maxFixLoops: Math.max(1, settings.maxFixLoops - 1)
              })}
            >
              <Ionicons name="remove" size={20} color={Colors.textPrimary} />
            </TouchableOpacity>
            <Text style={styles.counterValue}>{settings.maxFixLoops}</Text>
            <TouchableOpacity
              style={styles.counterButton}
              onPress={() => onSettingsChange({ 
                ...settings, 
                maxFixLoops: Math.min(10, settings.maxFixLoops + 1)
              })}
            >
              <Ionicons name="add" size={20} color={Colors.textPrimary} />
            </TouchableOpacity>
          </View>
        </View>

        {/* Specialization */}
        <View style={styles.settingRow}>
          <Text style={styles.settingLabel}>Specialization</Text>
          <TextInput
            style={styles.textInput}
            value={settings.specialization}
            onChangeText={(text) => onSettingsChange({ ...settings, specialization: text })}
            placeholder="React/Vite + Capacitor Android..."
            placeholderTextColor={Colors.textMuted}
            multiline
          />
        </View>
      </View>

      {/* Version Info */}
      <View style={styles.footer}>
        <Text style={styles.versionText}>SOVEREIGN STUDIO V3.0.0</Text>
        <Text style={styles.copyrightText}>© Ouroboros Collective</Text>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  header: {
    alignItems: 'center',
    paddingVertical: Spacing.xl,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  headerTitle: {
    color: Colors.textPrimary,
    fontSize: FontSize.xl,
    fontWeight: '700',
    marginTop: Spacing.sm,
    letterSpacing: 2,
  },
  headerSubtitle: {
    color: Colors.textMuted,
    fontSize: FontSize.sm,
    marginTop: Spacing.xs,
  },
  section: {
    padding: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: Spacing.md,
  },
  sectionTitle: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
    fontWeight: '600',
    marginLeft: Spacing.sm,
    letterSpacing: 1,
  },
  keyInputContainer: {
    marginBottom: Spacing.md,
  },
  keyLabel: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: Spacing.xs,
  },
  keyEmoji: {
    fontSize: 18,
    marginRight: Spacing.sm,
  },
  keyLabelText: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  keyName: {
    color: Colors.textPrimary,
    fontSize: FontSize.md,
    fontWeight: '500',
  },
  freeBadge: {
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 2,
    borderRadius: BorderRadius.sm,
    marginLeft: Spacing.sm,
  },
  freeBadgeText: {
    color: Colors.background,
    fontSize: FontSize.xs,
    fontWeight: '700',
  },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  keyInput: {
    flex: 1,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    color: Colors.textPrimary,
    fontSize: FontSize.sm,
  },
  keyInputRequired: {
    borderColor: Colors.warning,
  },
  visibilityToggle: {
    position: 'absolute',
    right: Spacing.sm,
    padding: Spacing.xs,
  },
  keyStatus: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
    marginTop: Spacing.xs,
  },
  mlvocaNote: {
    flexDirection: 'row',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: Colors.primary,
    padding: Spacing.md,
    marginTop: Spacing.sm,
  },
  mlvocaEmoji: {
    fontSize: 24,
    marginRight: Spacing.md,
  },
  mlvocaText: {
    flex: 1,
  },
  mlvocaTitle: {
    color: Colors.primary,
    fontSize: FontSize.sm,
    fontWeight: '600',
    marginBottom: Spacing.xs,
  },
  mlvocaDescription: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
    lineHeight: 18,
  },
  helperText: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
    marginTop: Spacing.xs,
    fontStyle: 'italic',
  },
  settingRow: {
    marginBottom: Spacing.md,
  },
  settingLabel: {
    color: Colors.textSecondary,
    fontSize: FontSize.sm,
    marginBottom: Spacing.sm,
  },
  segmentedControl: {
    flexDirection: 'row',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    padding: 2,
  },
  segment: {
    flex: 1,
    paddingVertical: Spacing.sm,
    alignItems: 'center',
    borderRadius: BorderRadius.sm,
  },
  segmentActive: {
    backgroundColor: Colors.primary,
  },
  segmentText: {
    color: Colors.textSecondary,
    fontSize: FontSize.sm,
    fontWeight: '500',
  },
  segmentTextActive: {
    color: Colors.background,
  },
  pillGroup: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.xs,
  },
  pill: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.full,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  pillActive: {
    backgroundColor: Colors.primary,
    borderColor: Colors.primary,
  },
  pillText: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
    fontWeight: '600',
  },
  pillTextActive: {
    color: Colors.background,
  },
  counterContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  counterButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  counterValue: {
    color: Colors.primary,
    fontSize: FontSize.xl,
    fontWeight: '700',
    marginHorizontal: Spacing.md,
    minWidth: 30,
    textAlign: 'center',
  },
  textInput: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    color: Colors.textPrimary,
    fontSize: FontSize.sm,
    minHeight: 80,
    textAlignVertical: 'top',
  },
  footer: {
    alignItems: 'center',
    paddingVertical: Spacing.xl,
    paddingBottom: Spacing.xxl,
  },
  versionText: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
    fontWeight: '600',
    letterSpacing: 1,
  },
  copyrightText: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
    marginTop: Spacing.xs,
  },
});

export default SettingsScreen;