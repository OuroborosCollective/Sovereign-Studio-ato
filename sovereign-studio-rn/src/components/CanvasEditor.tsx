import React, { useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Animated,
  PanResponder,
  Dimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, BorderRadius, FontSize } from '../../utils/theme';

interface CanvasCard {
  id: string;
  title: string;
  body: string;
  x: number;
  y: number;
}

interface CanvasEditorProps {
  cards: CanvasCard[];
  onCardSelect?: (id: string) => void;
  selectedId?: string;
}

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

export const CanvasEditor: React.FC<CanvasEditorProps> = ({
  cards,
  onCardSelect,
  selectedId,
}) => {
  const [selectedCard, setSelectedCard] = useState<string | null>(null);

  const handleCardPress = useCallback((id: string) => {
    setSelectedCard(id);
    onCardSelect?.(id);
  }, [onCardSelect]);

  const renderCard = (card: CanvasCard) => {
    const isSelected = selectedCard === card.id;

    return (
      <TouchableOpacity
        key={card.id}
        style={[
          styles.card,
          {
            left: card.x,
            top: card.y,
          },
          isSelected && styles.cardSelected,
        ]}
        onPress={() => handleCardPress(card.id)}
        activeOpacity={0.8}
      >
        <View style={styles.cardHeader}>
          <View style={styles.cardNumber}>
            <Text style={styles.cardNumberText}>
              {card.title.split(' · ')[0]}
            </Text>
          </View>
          {isSelected && (
            <View style={styles.selectedIndicator}>
              <Ionicons name="checkmark-circle" size={14} color={Colors.primary} />
            </View>
          )}
        </View>
        <Text style={styles.cardTitle} numberOfLines={2}>
          {card.title.split(' · ')[1] || card.title}
        </Text>
        <Text style={styles.cardBody} numberOfLines={3}>
          {card.body}
        </Text>
        <View style={styles.cardFooter}>
          <View style={styles.cardDot} />
          <Text style={styles.cardDotText}>AUTO</Text>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      {/* Canvas Background */}
      <View style={styles.canvasBackground}>
        {/* Grid Pattern */}
        <View style={styles.gridOverlay}>
          {[...Array(20)].map((_, i) => (
            <View key={`h-${i}`} style={[styles.gridLine, styles.gridLineHorizontal, { top: i * 40 }]} />
          ))}
          {[...Array(10)].map((_, i) => (
            <View key={`v-${i}`} style={[styles.gridLine, styles.gridLineVertical, { left: i * 80 }]} />
          ))}
        </View>

        {/* Cards */}
        {cards.map(renderCard)}

        {/* Empty State */}
        {cards.length === 0 && (
          <View style={styles.emptyState}>
            <Text style={styles.emptyEmoji}>🎯</Text>
            <Text style={styles.emptyText}>Keine Cards vorhanden</Text>
            <Text style={styles.emptySubtext}>
              Cards werden automatisch aus dem Workflow erstellt
            </Text>
          </View>
        )}
      </View>

      {/* Canvas Controls */}
      <View style={styles.canvasControls}>
        <TouchableOpacity style={styles.controlButton}>
          <Ionicons name="add" size={20} color={Colors.textPrimary} />
        </TouchableOpacity>
        <TouchableOpacity style={styles.controlButton}>
          <Ionicons name="grid" size={20} color={Colors.textPrimary} />
        </TouchableOpacity>
        <TouchableOpacity style={styles.controlButton}>
          <Ionicons name="move" size={20} color={Colors.textPrimary} />
        </TouchableOpacity>
      </View>

      {/* Canvas Info */}
      <View style={styles.canvasInfo}>
        <Text style={styles.canvasInfoText}>
          {cards.length} Cards • Zoom: 100%
        </Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.backgroundSecondary,
  },
  canvasBackground: {
    flex: 1,
    position: 'relative',
  },
  gridOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
  },
  gridLine: {
    position: 'absolute',
    backgroundColor: Colors.border,
    opacity: 0.3,
  },
  gridLineHorizontal: {
    left: 0,
    right: 0,
    height: 1,
  },
  gridLineVertical: {
    top: 0,
    bottom: 0,
    width: 1,
  },
  card: {
    position: 'absolute',
    width: 160,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: Spacing.md,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 4,
    elevation: 3,
  },
  cardSelected: {
    borderColor: Colors.primary,
    shadowColor: Colors.primary,
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 5,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: Spacing.sm,
  },
  cardNumber: {
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 2,
    borderRadius: BorderRadius.sm,
  },
  cardNumberText: {
    color: Colors.background,
    fontSize: FontSize.xs,
    fontWeight: '700',
  },
  selectedIndicator: {
    position: 'absolute',
    right: -4,
    top: -4,
  },
  cardTitle: {
    color: Colors.textPrimary,
    fontSize: FontSize.sm,
    fontWeight: '600',
    marginBottom: Spacing.xs,
  },
  cardBody: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
    lineHeight: 16,
  },
  cardFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: Spacing.sm,
  },
  cardDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: Colors.success,
    marginRight: Spacing.xs,
  },
  cardDotText: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
    fontWeight: '600',
  },
  emptyState: {
    position: 'absolute',
    top: '50%',
    left: '50%',
    transform: [{ translateX: -100 }, { translateY: -50 }],
    alignItems: 'center',
    padding: Spacing.xl,
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
    color: Colors.textMuted,
    fontSize: FontSize.sm,
  },
  canvasControls: {
    position: 'absolute',
    right: Spacing.md,
    top: Spacing.md,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: Spacing.xs,
  },
  controlButton: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: BorderRadius.sm,
  },
  canvasInfo: {
    position: 'absolute',
    left: Spacing.md,
    bottom: Spacing.md,
    backgroundColor: Colors.surface,
    paddingHorizontal: Spacing.sm,
    paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.sm,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  canvasInfoText: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
  },
});

export default CanvasEditor;