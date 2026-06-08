import React from 'react';
import {
  View,
  StyleSheet,
  SafeAreaView,
} from 'react-native';
import { Colors } from '../../utils/theme';
import { useAppStore } from '../../store/appStore';
import { CanvasEditor } from '../../components/CanvasEditor';

interface CanvasScreenProps {
  navigation: any;
}

export const CanvasScreen: React.FC<CanvasScreenProps> = ({ navigation }) => {
  const { cards } = useAppStore();

  // Convert cards to canvas format
  const canvasCards = cards.map((card, index) => ({
    id: card.id,
    title: card.title,
    body: card.body,
    x: 20 + (index % 2) * 180,
    y: 20 + Math.floor(index / 2) * 160,
  }));

  return (
    <SafeAreaView style={styles.container}>
      <CanvasEditor
        cards={canvasCards}
        selectedId={undefined}
        onCardSelect={(id) => console.log('Selected:', id)}
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

export default CanvasScreen;