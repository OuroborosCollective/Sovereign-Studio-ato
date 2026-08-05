import React, { useCallback } from 'react';
import {
  View,
  StyleSheet,
  SafeAreaView,
} from 'react-native';
import { Colors } from '../../utils/theme';
import { useAppStore } from '../../store/appStore';
import { GitHubExplorer } from '../../components/GitHubExplorer';
import { listRepositoryTree } from '../services/githubService';
import type { RepoFile } from '../../types';

interface ExplorerScreenProps {
  navigation: any;
}

export const ExplorerScreen: React.FC<ExplorerScreenProps> = ({ navigation }) => {
  const {
    repoUrl,
    setRepoUrl,
    repoFiles,
    repoStatus,
    isRepoBusy,
    repoLoaded,
    setRepoFiles,
    setRepoStatus,
    setIsRepoBusy,
    setRepoLoaded,
    addLog,
    setSelectedFile,
  } = useAppStore();

  const parseGithubRepoUrl = (value: string): { owner: string; repo: string } | null => {
    const match = value.match(/github\.com\/([^\/]+)\/([^\/]+)/i);
    if (!match) return null;
    return { owner: match[1], repo: match[2].replace('.git', '') };
  };

  const loadRepoTree = useCallback(async () => {
    const parsed = parseGithubRepoUrl(repoUrl);
    if (!parsed) {
      setRepoStatus('❌ Ungültige GitHub URL. Format: https://github.com/owner/repo');
      return;
    }

    setIsRepoBusy(true);
    setRepoLoaded(false);
    setRepoStatus(`Lade ${parsed.owner}/${parsed.repo}...`);
    addLog(`📁 Lade Repository: ${parsed.owner}/${parsed.repo}`);

    try {
      const tree = await listRepositoryTree({
        owner: parsed.owner,
        repo: parsed.repo,
        branch: 'main',
        maxEntries: 250,
      });
      const files: RepoFile[] = tree.map((entry) => ({
        path: entry.path,
        type: entry.type,
        size: entry.size,
      }));

      setRepoFiles(files);
      setRepoLoaded(true);
      setRepoStatus(`${files.length} Einträge über den Sovereign-Gateway geladen`);
      addLog(`✅ ${files.length} revisionsgebundene Repository-Einträge geladen`);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Unbekannter Gateway-Fehler';
      setRepoStatus(`❌ Fehler: ${message}`);
      addLog(`❌ Fehler beim Laden: ${message}`);
    } finally {
      setIsRepoBusy(false);
    }
  }, [repoUrl]);

  const handleFileSelect = useCallback((file: RepoFile) => {
    addLog(`📄 Datei ausgewählt: ${file.path}`);
    setSelectedFile({ path: file.path, icon: '📄' });
    // Could navigate to detail view
  }, []);

  return (
    <SafeAreaView style={styles.container}>
      <GitHubExplorer
        repoUrl={repoUrl}
        onRepoUrlChange={setRepoUrl}
        repoFiles={repoFiles}
        repoStatus={repoStatus}
        isLoading={isRepoBusy}
        onLoadRepo={loadRepoTree}
        onFileSelect={handleFileSelect}
      />
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
});

export default ExplorerScreen;