import React from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, BorderRadius, FontSize } from '../../utils/theme';
import type { RepoFile } from '../../types';

interface GitHubExplorerProps {
  repoUrl: string;
  onRepoUrlChange: (url: string) => void;
  repoFiles: RepoFile[];
  repoStatus: string;
  isLoading: boolean;
  onLoadRepo: () => void;
  onFileSelect: (file: RepoFile) => void;
}

export const GitHubExplorer: React.FC<GitHubExplorerProps> = ({
  repoUrl,
  onRepoUrlChange,
  repoFiles,
  repoStatus,
  isLoading,
  onLoadRepo,
  onFileSelect,
}) => {
  const getFileIcon = (path: string, type: string) => {
    if (type === 'tree') return '📁';
    
    const ext = path.split('.').pop()?.toLowerCase() || '';
    const iconMap: Record<string, string> = {
      ts: '🔷',
      tsx: '🔷',
      js: '🟨',
      jsx: '🟨',
      json: '📋',
      md: '📝',
      yml: '⚙️',
      yaml: '⚙️',
      gradle: '🟢',
      xml: '📄',
      png: '🖼️',
      jpg: '🖼️',
      svg: '🎨',
    };
    return iconMap[ext] || '📄';
  };

  const getFileName = (path: string) => {
    const parts = path.split('/');
    return parts[parts.length - 1];
  };

  const getFilePath = (path: string) => {
    const parts = path.split('/');
    parts.pop();
    return parts.join('/');
  };

  // Group files by directory
  const groupedFiles = repoFiles.reduce((acc, file) => {
    const dir = file.type === 'tree' ? file.path : getFilePath(file.path);
    if (!acc[dir]) acc[dir] = [];
    acc[dir].push(file);
    return acc;
  }, {} as Record<string, RepoFile[]>);

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <Ionicons name="logo-github" size={20} color={Colors.textPrimary} />
          <Text style={styles.headerTitle}>GITHUB EXPLORER</Text>
        </View>
        <View style={styles.fileCount}>
          <Text style={styles.fileCountText}>{repoFiles.length} files</Text>
        </View>
      </View>

      {/* URL Input */}
      <View style={styles.inputContainer}>
        <TextInput
          style={styles.input}
          value={repoUrl}
          onChangeText={onRepoUrlChange}
          placeholder="https://github.com/owner/repo"
          placeholderTextColor={Colors.textMuted}
          autoCapitalize="none"
          autoCorrect={false}
        />
        <TouchableOpacity
          style={[styles.loadButton, isLoading && styles.loadButtonDisabled]}
          onPress={onLoadRepo}
          disabled={isLoading}
        >
          {isLoading ? (
            <ActivityIndicator size="small" color={Colors.background} />
          ) : (
            <Ionicons name="refresh" size={18} color={Colors.background} />
          )}
        </TouchableOpacity>
      </View>

      {/* Status */}
      <View style={styles.statusContainer}>
        <Text style={styles.statusText}>{repoStatus}</Text>
      </View>

      {/* File List */}
      <ScrollView style={styles.fileList} showsVerticalScrollIndicator={false}>
        {repoFiles.length === 0 ? (
          <View style={styles.emptyState}>
            <Text style={styles.emptyEmoji}>📂</Text>
            <Text style={styles.emptyText}>Keine Dateien geladen</Text>
            <Text style={styles.emptySubtext}>
              GitHub URL eingeben und laden
            </Text>
          </View>
        ) : (
          Object.entries(groupedFiles).map(([dir, files]) => (
            <View key={dir} style={styles.directoryGroup}>
              {/* Directory Header */}
              <View style={styles.directoryHeader}>
                <Ionicons name="folder" size={14} color={Colors.primary} />
                <Text style={styles.directoryPath} numberOfLines={1}>
                  {dir || '/'}
                </Text>
              </View>

              {/* Files */}
              {files
                .filter(f => f.type === 'blob')
                .slice(0, 30)
                .map((file) => (
                  <TouchableOpacity
                    key={file.path}
                    style={styles.fileItem}
                    onPress={() => onFileSelect(file)}
                  >
                    <Text style={styles.fileIcon}>
                      {getFileIcon(file.path, file.type)}
                    </Text>
                    <View style={styles.fileInfo}>
                      <Text style={styles.fileName} numberOfLines={1}>
                        {getFileName(file.path)}
                      </Text>
                      <Text style={styles.filePath} numberOfLines={1}>
                        {file.path}
                      </Text>
                    </View>
                    {file.size && (
                      <Text style={styles.fileSize}>
                        {(file.size / 1024).toFixed(1)}KB
                      </Text>
                    )}
                  </TouchableOpacity>
                ))}
            </View>
          ))
        )}
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.surface,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  headerTitle: {
    color: Colors.textPrimary,
    fontSize: FontSize.sm,
    fontWeight: '600',
    marginLeft: Spacing.sm,
    letterSpacing: 1,
  },
  fileCount: {
    backgroundColor: Colors.backgroundTertiary,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 2,
    borderRadius: BorderRadius.sm,
  },
  fileCountText: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
  },
  inputContainer: {
    flexDirection: 'row',
    padding: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  input: {
    flex: 1,
    backgroundColor: Colors.backgroundTertiary,
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    color: Colors.textPrimary,
    fontSize: FontSize.sm,
  },
  loadButton: {
    width: 44,
    height: 44,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: Spacing.sm,
  },
  loadButtonDisabled: {
    backgroundColor: Colors.backgroundTertiary,
  },
  statusContainer: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  statusText: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
  },
  fileList: {
    flex: 1,
  },
  emptyState: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 60,
  },
  emptyEmoji: {
    fontSize: 48,
    marginBottom: Spacing.md,
  },
  emptyText: {
    color: Colors.textPrimary,
    fontSize: FontSize.lg,
    fontWeight: '600',
    marginBottom: Spacing.xs,
  },
  emptySubtext: {
    color: Colors.textSecondary,
    fontSize: FontSize.sm,
  },
  directoryGroup: {
    marginBottom: Spacing.sm,
  },
  directoryHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    backgroundColor: Colors.backgroundTertiary,
  },
  directoryPath: {
    color: Colors.primary,
    fontSize: FontSize.xs,
    fontWeight: '600',
    marginLeft: Spacing.xs,
    flex: 1,
  },
  fileItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  fileIcon: {
    fontSize: 16,
    marginRight: Spacing.sm,
  },
  fileInfo: {
    flex: 1,
  },
  fileName: {
    color: Colors.textPrimary,
    fontSize: FontSize.sm,
    fontWeight: '500',
  },
  filePath: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
    marginTop: 2,
  },
  fileSize: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
    marginLeft: Spacing.sm,
  },
});

export default GitHubExplorer;