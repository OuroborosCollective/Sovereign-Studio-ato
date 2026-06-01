import React, { useCallback, useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  SafeAreaView,
  RefreshControl,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { Colors, Spacing, BorderRadius, FontSize } from '../../utils/theme';
import { useAppStore } from '../../store/appStore';
import { providerManager } from '../../features/ai/providerManager';
import type { RepoFile } from '../../types';

interface HomeScreenProps {
  navigation: any;
}

export const HomeScreen: React.FC<HomeScreenProps> = ({ navigation }) => {
  const {
    repoUrl,
    setRepoUrl,
    repoFiles,
    repoStatus,
    isRepoBusy,
    repoLoaded,
    syncResult,
    isSyncing,
    cards,
    built,
    logs,
    fixLoops,
    settings,
    currentProvider,
    setRepoFiles,
    setRepoStatus,
    setIsRepoBusy,
    setRepoLoaded,
    setSyncResult,
    setIsSyncing,
    addLog,
    setCurrentProvider,
    setSettings,
  } = useAppStore();

  const [refreshing, setRefreshing] = useState(false);

  const parseGithubRepoUrl = (value: string): { owner: string; repo: string } | null => {
    const match = value.match(/github\.com\/([^\/]+)\/([^\/]+)/i);
    if (!match) return null;
    return { owner: match[1], repo: match[2].replace('.git', '') };
  };

  const loadRepoTree = useCallback(async () => {
    const parsed = parseGithubRepoUrl(repoUrl);
    if (!parsed) {
      setRepoStatus('❌ Ungültige GitHub URL');
      return;
    }

    setIsRepoBusy(true);
    setRepoLoaded(false);
    setSyncResult(null);
    setRepoStatus(`Lade ${parsed.owner}/${parsed.repo}...`);
    addLog(`📁 Lade Repository: ${parsed.owner}/${parsed.repo}`);

    try {
      const headers: Record<string, string> = { Accept: 'application/vnd.github+json' };
      const githubToken = useAppStore.getState().githubToken;
      if (githubToken.trim()) {
        headers.Authorization = `Bearer ${githubToken.trim()}`;
      }

      const response = await fetch(
        `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/git/trees/main?recursive=1`,
        { headers }
      );

      if (!response.ok) {
        throw new Error(`GitHub API ${response.status}`);
      }

      const data = await response.json();
      const treeData: any[] = data.tree ?? [];
      const files: RepoFile[] = [];

      for (const f of treeData) {
        if (f.type === 'blob' || f.type === 'tree') {
          files.push({ path: f.path, type: f.type, size: f.size });
          if (files.length >= 250) break;
        }
      }

      setRepoFiles(files);
      setRepoLoaded(true);
      setRepoStatus(`${files.length} Dateien geladen`);
      addLog(`✅ ${files.length} Dateien geladen`);
    } catch (err: any) {
      setRepoStatus(`❌ Fehler: ${err.message}`);
      addLog(`❌ Fehler beim Laden: ${err.message}`);
    } finally {
      setIsRepoBusy(false);
    }
  }, [repoUrl]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await loadRepoTree();
    setRefreshing(false);
  }, [loadRepoTree]);

  const runAwarenessSync = useCallback(async () => {
    setIsSyncing(true);
    addLog('🔮 Starte Awareness Sync...');

    try {
      const { geminiKey, groqKey, hfKey, togetherKey, openrouterKey } = useAppStore.getState();
      const result = await providerManager.generateWithFallback(
        geminiKey,
        'gemini',
        `Analysiere das Repository: ${repoUrl}\n\nDateien: ${repoFiles.slice(0, 20).map(f => f.path).join('\n')}`,
        {},
        (from, to, error) => {
          addLog(`🔄 Fallback: ${from} → ${to}`);
          setCurrentProvider(to);
        }
      );

      setSyncResult({
        summary: result.text.substring(0, 200),
        technologies: ['React', 'TypeScript', 'Capacitor'],
        structure: 'Monorepo mit Android Build',
        suggestions: ['API Keys konfigurieren', 'Repository laden'],
        rawText: result.text,
      });
      addLog('✅ Awareness Sync abgeschlossen');
    } catch (err: any) {
      addLog(`❌ Sync Fehler: ${err.message}`);
    } finally {
      setIsSyncing(false);
    }
  }, [repoUrl, repoFiles]);

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.logoContainer}>
          <Text style={styles.logoEmoji}>🛡️</Text>
          <View>
            <Text style={styles.logoTitle}>SOVEREIGN STUDIO</Text>
            <Text style={styles.logoSubtitle}>AI Product Builder</Text>
          </View>
        </View>
        <View style={styles.statusBadge}>
          <View style={[styles.statusDot, currentProvider === 'gemini' ? styles.statusOnline : styles.statusFree]} />
          <Text style={styles.statusText}>{currentProvider.toUpperCase()}</Text>
        </View>
      </View>

      <ScrollView
        style={styles.content}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={Colors.primary}
          />
        }
      >
        {/* Quick Actions */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>⚡ QUICK ACTIONS</Text>
          <View style={styles.actionGrid}>
            <TouchableOpacity
              style={styles.actionCard}
              onPress={() => navigation.navigate('Chat')}
            >
              <Ionicons name="chatbubbles" size={28} color={Colors.primary} />
              <Text style={styles.actionTitle}>Chat</Text>
              <Text style={styles.actionSubtitle}>AI Assistant</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.actionCard}
              onPress={() => navigation.navigate('Explorer')}
            >
              <Ionicons name="folder" size={28} color={Colors.accent} />
              <Text style={styles.actionTitle}>Explorer</Text>
              <Text style={styles.actionSubtitle}>GitHub Files</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.actionCard}
              onPress={() => navigation.navigate('Settings')}
            >
              <Ionicons name="settings" size={28} color={Colors.warning} />
              <Text style={styles.actionTitle}>Settings</Text>
              <Text style={styles.actionSubtitle}>Konfiguration</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.actionCard}
              onPress={runAwarenessSync}
              disabled={isSyncing}
            >
              <Ionicons name={isSyncing ? 'sync' : 'analytics'} size={28} color={Colors.success} />
              <Text style={styles.actionTitle}>{isSyncing ? 'Sync...' : 'Awareness'}</Text>
              <Text style={styles.actionSubtitle}>Repo Analyse</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.actionCard}
              onPress={() => navigation.navigate('CodeRefactor')}
            >
              <Ionicons name="code-slash" size={28} color="#38BDF8" />
              <Text style={styles.actionTitle}>Refactor</Text>
              <Text style={styles.actionSubtitle}>Code Modifier</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Repository Status */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>📁 REPOSITORY STATUS</Text>
          <View style={styles.repoCard}>
            <View style={styles.repoHeader}>
              <Ionicons name="logo-github" size={20} color={Colors.textSecondary} />
              <Text style={styles.repoLabel} numberOfLines={1}>
                {repoUrl || 'Kein Repository'}
              </Text>
            </View>
            <View style={styles.repoStats}>
              <View style={styles.statItem}>
                <Text style={styles.statValue}>{repoFiles.length}</Text>
                <Text style={styles.statLabel}>Files</Text>
              </View>
              <View style={styles.statItem}>
                <Text style={[styles.statValue, repoLoaded ? styles.textSuccess : styles.textWarning]}>
                  {repoLoaded ? '✓' : '○'}
                </Text>
                <Text style={styles.statLabel}>Loaded</Text>
              </View>
              <View style={styles.statItem}>
                <Text style={styles.statValue}>{cards.length}</Text>
                <Text style={styles.statLabel}>Cards</Text>
              </View>
            </View>
            <TouchableOpacity
              style={[styles.loadButton, isRepoBusy && styles.loadButtonDisabled]}
              onPress={loadRepoTree}
              disabled={isRepoBusy}
            >
              <Ionicons name={isRepoBusy ? 'sync' : 'download'} size={18} color={Colors.background} />
              <Text style={styles.loadButtonText}>
                {isRepoBusy ? 'Laden...' : 'Repository laden'}
              </Text>
            </TouchableOpacity>
            <Text style={styles.repoStatus}>{repoStatus}</Text>
          </View>
        </View>

        {/* Pipeline Status */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>🔄 PIPELINE STATUS</Text>
          <View style={styles.pipelineCard}>
            <View style={styles.pipelineRow}>
              <Text style={styles.pipelineLabel}>FIX_LOOP</Text>
              <Text style={styles.pipelineValue}>{fixLoops}/{settings.maxFixLoops}</Text>
            </View>
            <View style={styles.pipelineRow}>
              <Text style={styles.pipelineLabel}>STATUS</Text>
              <View style={styles.statusPill}>
                <Text style={styles.statusPillText}>{built ? 'BUILT' : 'IDLE'}</Text>
              </View>
            </View>
            <View style={styles.pipelineRow}>
              <Text style={styles.pipelineLabel}>REPO MODE</Text>
              <Text style={styles.pipelineValue}>{settings.repoMode.toUpperCase()}</Text>
            </View>
            <View style={styles.pipelineRow}>
              <Text style={styles.pipelineLabel}>PACKAGE</Text>
              <Text style={styles.pipelineValue}>{settings.packageManager.toUpperCase()}</Text>
            </View>
          </View>
        </View>

        {/* System Log */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>📋 SYSTEM LOG</Text>
          <View style={styles.logContainer}>
            {logs.slice(0, 10).map((entry, index) => (
              <View key={index} style={styles.logEntry}>
                <Text style={[
                  styles.logText,
                  entry.startsWith('❌') && styles.logError,
                  entry.startsWith('✅') && styles.logSuccess,
                  entry.startsWith('📁') && styles.logInfo,
                ]}>{entry}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* Awareness Result */}
        {syncResult && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>🔮 AWARENESS RESULT</Text>
            <View style={styles.awarenessCard}>
              <Text style={styles.awarenessSummary}>{syncResult.summary}</Text>
              <View style={styles.techTags}>
                {syncResult.technologies.slice(0, 5).map((tech, i) => (
                  <View key={i} style={styles.techTag}>
                    <Text style={styles.techTagText}>{tech}</Text>
                  </View>
                ))}
              </View>
            </View>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
    backgroundColor: Colors.surface,
  },
  logoContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  logoEmoji: {
    fontSize: 32,
    marginRight: Spacing.sm,
  },
  logoTitle: {
    color: Colors.primary,
    fontSize: FontSize.lg,
    fontWeight: '700',
    letterSpacing: 1,
  },
  logoSubtitle: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.backgroundTertiary,
    paddingHorizontal: Spacing.sm,
    paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.full,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: Spacing.xs,
  },
  statusOnline: {
    backgroundColor: Colors.online,
  },
  statusFree: {
    backgroundColor: Colors.primary,
  },
  statusText: {
    color: Colors.primary,
    fontSize: FontSize.xs,
    fontWeight: '600',
  },
  content: {
    flex: 1,
  },
  section: {
    padding: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  sectionTitle: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
    fontWeight: '600',
    letterSpacing: 1,
    marginBottom: Spacing.md,
  },
  actionGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  actionCard: {
    width: '48%',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: Spacing.md,
    marginBottom: Spacing.sm,
    alignItems: 'center',
  },
  actionTitle: {
    color: Colors.textPrimary,
    fontSize: FontSize.md,
    fontWeight: '600',
    marginTop: Spacing.sm,
  },
  actionSubtitle: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
    marginTop: 2,
  },
  repoCard: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: Spacing.md,
  },
  repoHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: Spacing.md,
  },
  repoLabel: {
    color: Colors.textPrimary,
    fontSize: FontSize.sm,
    marginLeft: Spacing.sm,
    flex: 1,
  },
  repoStats: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    marginBottom: Spacing.md,
  },
  statItem: {
    alignItems: 'center',
  },
  statValue: {
    color: Colors.primary,
    fontSize: FontSize.xl,
    fontWeight: '700',
  },
  statLabel: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
    marginTop: 2,
  },
  textSuccess: {
    color: Colors.success,
  },
  textWarning: {
    color: Colors.warning,
  },
  loadButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.md,
    paddingVertical: Spacing.sm,
    marginBottom: Spacing.sm,
  },
  loadButtonDisabled: {
    backgroundColor: Colors.backgroundTertiary,
  },
  loadButtonText: {
    color: Colors.background,
    fontSize: FontSize.sm,
    fontWeight: '600',
    marginLeft: Spacing.sm,
  },
  repoStatus: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
    textAlign: 'center',
  },
  pipelineCard: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: Spacing.md,
  },
  pipelineRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: Spacing.xs,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  pipelineLabel: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
    fontWeight: '600',
  },
  pipelineValue: {
    color: Colors.primary,
    fontSize: FontSize.sm,
    fontWeight: '600',
  },
  statusPill: {
    backgroundColor: Colors.backgroundTertiary,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 2,
    borderRadius: BorderRadius.sm,
  },
  statusPillText: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
    fontWeight: '600',
  },
  logContainer: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: Spacing.sm,
    maxHeight: 200,
  },
  logEntry: {
    paddingVertical: 4,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  logText: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
    fontFamily: 'monospace',
  },
  logError: {
    color: Colors.error,
  },
  logSuccess: {
    color: Colors.success,
  },
  logInfo: {
    color: Colors.primary,
  },
  awarenessCard: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: Colors.primary,
    padding: Spacing.md,
  },
  awarenessSummary: {
    color: Colors.textPrimary,
    fontSize: FontSize.sm,
    lineHeight: 22,
    marginBottom: Spacing.md,
  },
  techTags: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.xs,
  },
  techTag: {
    backgroundColor: Colors.backgroundTertiary,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 4,
    borderRadius: BorderRadius.full,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  techTagText: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
  },
});

export default HomeScreen;