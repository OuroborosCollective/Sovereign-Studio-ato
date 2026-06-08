import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, BorderRadius, FontSize } from '../../utils/theme';
import type { ChatMessage, ProviderType } from '../../types';

interface MatrixChatProps {
  messages: ChatMessage[];
  onSend: (message: string) => void;
  isLoading?: boolean;
  currentProvider?: ProviderType;
}

export const MatrixChat: React.FC<MatrixChatProps> = ({
  messages,
  onSend,
  isLoading = false,
  currentProvider = 'mlvoca',
}) => {
  const [input, setInput] = useState('');
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    // Auto-scroll to bottom when new messages arrive
    setTimeout(() => {
      scrollRef.current?.scrollToEnd({ animated: true });
    }, 100);
  }, [messages]);

  const handleSend = () => {
    if (input.trim() && !isLoading) {
      onSend(input.trim());
      setInput('');
    }
  };

  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  };

  const getProviderIcon = (provider: ProviderType) => {
    switch (provider) {
      case 'gemini':
        return '🌟';
      case 'groq':
        return '⚡';
      case 'mlvoca':
        return '🔮';
      case 'huggingface':
        return '🤗';
      case 'together':
        return '🎯';
      case 'openrouter':
        return '🌐';
      default:
        return '🤖';
    }
  };

  const renderMessage = (message: ChatMessage) => {
    const isUser = message.role === 'user';
    const isSystem = message.role === 'system';

    return (
      <View
        key={message.id}
        style={[
          styles.messageContainer,
          isUser ? styles.userMessage : styles.assistantMessage,
          isSystem && styles.systemMessage,
        ]}
      >
        {/* Avatar */}
        <View style={[
          styles.avatar,
          isUser ? styles.userAvatar : styles.assistantAvatar,
          isSystem && styles.systemAvatar,
        ]}>
          {isUser ? (
            <Ionicons name="person" size={18} color={Colors.textPrimary} />
          ) : isSystem ? (
            <Ionicons name="cog" size={18} color={Colors.textMuted} />
          ) : (
            <Text style={styles.avatarEmoji}>{getProviderIcon(message.provider || 'mlvoca')}</Text>
          )}
        </View>

        {/* Message Content */}
        <View style={styles.messageContent}>
          {/* Header */}
          <View style={styles.messageHeader}>
            <Text style={styles.senderName}>
              {isUser ? 'Du' : isSystem ? 'System' : currentProvider.toUpperCase()}
            </Text>
            <Text style={styles.timestamp}>{formatTime(message.timestamp)}</Text>
          </View>

          {/* Message Body */}
          <Text style={[
            styles.messageText,
            isUser && styles.userMessageText,
          ]}>
            {message.content}
          </Text>

          {/* Provider indicator for assistant */}
          {!isUser && !isSystem && message.provider && (
            <View style={styles.providerBadge}>
              <Text style={styles.providerText}>
                {getProviderIcon(message.provider)} {message.provider.toUpperCase()}
              </Text>
            </View>
          )}
        </View>
      </View>
    );
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={90}
    >
      {/* Matrix Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <View style={styles.statusIndicator} />
          <Text style={styles.headerTitle}>AGENT WORKSPACE</Text>
        </View>
        <View style={styles.providerIndicator}>
          <Text style={styles.providerLabel}>{currentProvider.toUpperCase()}</Text>
        </View>
      </View>

      {/* Messages Area */}
      <ScrollView
        ref={scrollRef}
        style={styles.messagesArea}
        contentContainerStyle={styles.messagesContent}
        showsVerticalScrollIndicator={false}
      >
        {messages.length === 0 ? (
          <View style={styles.emptyState}>
            <Text style={styles.emptyEmoji}>🔮</Text>
            <Text style={styles.emptyText}>Starte eine Konversation</Text>
            <Text style={styles.emptySubtext}>
              Beschreibe was du bauen möchtest
            </Text>
          </View>
        ) : (
          messages.map(renderMessage)
        )}

        {isLoading && (
          <View style={styles.loadingContainer}>
            <View style={styles.assistantMessage}>
              <View style={styles.avatar}>
                <Text style={styles.avatarEmoji}>{getProviderIcon(currentProvider)}</Text>
              </View>
              <View style={styles.messageContent}>
                <View style={styles.messageHeader}>
                  <Text style={styles.senderName}>{currentProvider.toUpperCase()}</Text>
                </View>
                <View style={styles.loadingBubble}>
                  <ActivityIndicator size="small" color={Colors.primary} />
                  <Text style={styles.loadingText}>Denkt...</Text>
                </View>
              </View>
            </View>
          </View>
        )}
      </ScrollView>

      {/* Input Area */}
      <View style={styles.inputArea}>
        <View style={styles.inputContainer}>
          <TextInput
            style={styles.input}
            value={input}
            onChangeText={setInput}
            placeholder="Befehl eingeben oder beschreiben..."
            placeholderTextColor={Colors.textMuted}
            multiline
            maxLength={2000}
            onSubmitEditing={handleSend}
            blurOnSubmit={false}
          />
          <TouchableOpacity
            style={[
              styles.sendButton,
              (!input.trim() || isLoading) && styles.sendButtonDisabled,
            ]}
            onPress={handleSend}
            disabled={!input.trim() || isLoading}
          >
            {isLoading ? (
              <ActivityIndicator size="small" color={Colors.background} />
            ) : (
              <Ionicons name="send" size={20} color={Colors.background} />
            )}
          </TouchableOpacity>
        </View>
        
        {/* Status Bar */}
        <View style={styles.statusBar}>
          <Text style={styles.statusText}>
            Enter zum Senden • Auto-fallback aktiv
          </Text>
          <View style={styles.providerDots}>
            <Text style={styles.dot}>●</Text>
            <Text style={[styles.dot, styles.dotActive]}>●</Text>
            <Text style={styles.dot}>●</Text>
          </View>
        </View>
      </View>
    </KeyboardAvoidingView>
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
    paddingVertical: Spacing.sm,
    backgroundColor: Colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statusIndicator: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: Colors.online,
    marginRight: Spacing.sm,
  },
  headerTitle: {
    color: Colors.primary,
    fontSize: FontSize.sm,
    fontWeight: '600',
    letterSpacing: 1,
  },
  providerIndicator: {
    backgroundColor: Colors.backgroundTertiary,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 2,
    borderRadius: BorderRadius.sm,
  },
  providerLabel: {
    color: Colors.primary,
    fontSize: FontSize.xs,
    fontWeight: '600',
  },
  messagesArea: {
    flex: 1,
  },
  messagesContent: {
    padding: Spacing.md,
    paddingBottom: Spacing.lg,
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
  messageContainer: {
    flexDirection: 'row',
    marginBottom: Spacing.md,
  },
  userMessage: {
    flexDirection: 'row-reverse',
  },
  assistantMessage: {
    flexDirection: 'row',
  },
  systemMessage: {
    flexDirection: 'row',
    opacity: 0.7,
  },
  avatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  userAvatar: {
    backgroundColor: Colors.primary,
  },
  assistantAvatar: {
    backgroundColor: Colors.surfaceTertiary,
  },
  systemAvatar: {
    backgroundColor: Colors.backgroundTertiary,
  },
  avatarEmoji: {
    fontSize: 16,
  },
  messageContent: {
    flex: 1,
    marginHorizontal: Spacing.sm,
    maxWidth: '80%',
  },
  messageHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
  },
  senderName: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
    fontWeight: '600',
    marginRight: Spacing.sm,
  },
  timestamp: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
  },
  messageText: {
    color: Colors.textPrimary,
    fontSize: FontSize.md,
    lineHeight: 22,
  },
  userMessageText: {
    color: Colors.background,
    backgroundColor: Colors.primary,
    padding: Spacing.sm,
    borderRadius: BorderRadius.lg,
    borderBottomRightRadius: BorderRadius.sm,
    overflow: 'hidden',
  },
  providerBadge: {
    marginTop: Spacing.xs,
    alignSelf: 'flex-start',
  },
  providerText: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
  },
  loadingContainer: {
    marginBottom: Spacing.md,
  },
  loadingBubble: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    padding: Spacing.sm,
    borderRadius: BorderRadius.lg,
    paddingRight: Spacing.md,
  },
  loadingText: {
    color: Colors.primary,
    fontSize: FontSize.sm,
    marginLeft: Spacing.sm,
  },
  inputArea: {
    backgroundColor: Colors.surface,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    padding: Spacing.md,
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
  },
  input: {
    flex: 1,
    backgroundColor: Colors.backgroundTertiary,
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    color: Colors.textPrimary,
    fontSize: FontSize.md,
    maxHeight: 100,
    marginRight: Spacing.sm,
  },
  sendButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: Colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendButtonDisabled: {
    backgroundColor: Colors.backgroundTertiary,
  },
  statusBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: Spacing.sm,
  },
  statusText: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
  },
  providerDots: {
    flexDirection: 'row',
  },
  dot: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
    marginLeft: Spacing.xs,
  },
  dotActive: {
    color: Colors.primary,
  },
});

export default MatrixChat;