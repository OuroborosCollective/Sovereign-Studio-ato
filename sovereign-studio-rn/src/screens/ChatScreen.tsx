import React, { useCallback, useState } from 'react';
import {
  View,
  StyleSheet,
  SafeAreaView,
} from 'react-native';
import { Colors } from '../../utils/theme';
import { useAppStore } from '../../store/appStore';
import { providerManager } from '../../features/ai/providerManager';
import { MatrixChat } from '../../components/MatrixChat';
import type { ChatMessage, RepoFile } from '../../types';

interface ChatScreenProps {
  navigation: any;
}

export const ChatScreen: React.FC<ChatScreenProps> = ({ navigation }) => {
  const {
    chatMessages,
    addChatMessage,
    clearChatMessages,
    currentProvider,
    setCurrentProvider,
    geminiKey,
    groqKey,
    hfKey,
    togetherKey,
    openrouterKey,
    repoUrl,
    repoFiles,
    addLog,
    setIsGenerating,
    isGenerating,
  } = useAppStore();

  const handleSendMessage = useCallback(async (message: string) => {
    // Add user message
    addChatMessage({
      role: 'user',
      content: message,
      provider: undefined,
    });

    setIsGenerating(true);
    addLog(`📤 Nachricht gesendet: ${message.substring(0, 50)}...`);

    try {
      // Build context prompt
      const contextPrompt = repoFiles.length > 0
        ? `Repository: ${repoUrl}\n\nDateien:\n${repoFiles.slice(0, 50).map(f => f.path).join('\n')}\n\n---\n\nUser: ${message}`
        : `User: ${message}`;

      // Try to generate response
      const result = await providerManager.generateWithFallback(
        geminiKey,
        'gemini',
        contextPrompt,
        {
          model: 'gemini-1.5-flash',
          temperature: 0.7,
          maxOutputTokens: 2048,
        },
        (from, to, error) => {
          addLog(`🔄 Fallback: ${from} → ${to}`);
          setCurrentProvider(to);
        }
      );

      // Add assistant response
      addChatMessage({
        role: 'assistant',
        content: result.text,
        provider: result.provider,
      });

      addLog(`✅ Antwort von ${result.provider.toUpperCase()}`);
    } catch (err: any) {
      addChatMessage({
        role: 'system',
        content: `❌ Fehler: ${err.message}\n\nBitte versuche es erneut oder konfiguriere einen API Key.`,
        provider: undefined,
      });
      addLog(`❌ Chat Fehler: ${err.message}`);
    } finally {
      setIsGenerating(false);
    }
  }, [repoUrl, repoFiles, geminiKey]);

  const handleClearChat = useCallback(() => {
    clearChatMessages();
    addLog('🗑️ Chat geleert');
  }, []);

  return (
    <SafeAreaView style={styles.container}>
      <MatrixChat
        messages={chatMessages}
        onSend={handleSendMessage}
        isLoading={isGenerating}
        currentProvider={currentProvider}
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

export default ChatScreen;