import React, { useCallback } from 'react';
import {
  View,
  StyleSheet,
  SafeAreaView,
} from 'react-native';
import { Colors } from '../../utils/theme';
import { useAppStore } from '../../store/appStore';
import { GitHubExplorer } from '../../components/GitHubExplorer';
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
    githubToken,
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
      const headers: Record<string, string> = { Accept: 'application/vnd.github+json' };
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
  }, [repoUrl, githubToken]);

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