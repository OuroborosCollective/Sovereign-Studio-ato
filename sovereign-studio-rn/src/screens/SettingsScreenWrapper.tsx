import React from 'react';
import {
  View,
  StyleSheet,
  SafeAreaView,
} from 'react-native';
import { Colors } from '../../utils/theme';
import { useAppStore } from '../../store/appStore';
import { SettingsScreen } from '../../components/SettingsScreen';

interface SettingsScreenWrapperProps {
  navigation: any;
}

export const SettingsScreenWrapper: React.FC<SettingsScreenWrapperProps> = ({ navigation }) => {
  const {
    geminiKey,
    setGeminiKey,
    githubToken,
    setGithubToken,
    groqKey,
    setGroqKey,
    hfKey,
    setHfKey,
    togetherKey,
    setTogetherKey,
    openrouterKey,
    setOpenrouterKey,
    settings,
    setSettings,
  } = useAppStore();

  return (
    <SafeAreaView style={styles.container}>
      <SettingsScreen
        geminiKey={geminiKey}
        onGeminiKeyChange={setGeminiKey}
        githubToken={githubToken}
        onGithubTokenChange={setGithubToken}
        groqKey={groqKey}
        onGroqKeyChange={setGroqKey}
        hfKey={hfKey}
        onHfKeyChange={setHfKey}
        togetherKey={togetherKey}
        onTogetherKeyChange={setTogetherKey}
        openrouterKey={openrouterKey}
        onOpenrouterKeyChange={setOpenrouterKey}
        settings={settings}
        onSettingsChange={setSettings}
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

export default SettingsScreenWrapper;