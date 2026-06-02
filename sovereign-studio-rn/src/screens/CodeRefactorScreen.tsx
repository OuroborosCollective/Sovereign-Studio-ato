import React, { useState, useRef } from "react";
import {
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  ScrollView,
  SafeAreaView,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Linking,
} from "react-native";
import { runRefactorPipeline, LogItem } from "../agents/orchestrator";
import { pushUpdatedCodeToGitHub } from "../services/githubService";
import { Colors, FontSize, Spacing, BorderRadius } from "../utils/theme";

const GROQ_API_URL = "https://console.groq.com/keys";

export function CodeRefactorScreen() {
  // Config States
  const [patToken, setPatToken] = useState("");
  const [owner, setOwner] = useState("");
  const [repo, setRepo] = useState("");
  const [branch, setBranch] = useState("main");
  const [path, setPath] = useState("src/App.tsx");
  const [instruction, setInstruction] = useState("");

  // App-State
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [finalCode, setFinalCode] = useState("");
  const [inReview, setInReview] = useState(false);

  const termScroll = useRef<ScrollView>(null);

  // Open Groq API Key registration page
  const openGroqConsole = () => {
    Linking.openURL(GROQ_API_URL);
  };

  const addLog = (text: string, type: LogItem["type"] = "info") => {
    setLogs((prev) => [
      ...prev,
      {
        id: Math.random().toString(),
        time: new Date().toLocaleTimeString(),
        type,
        text,
      },
    ]);
  };

  // Workflow Trigger
  const triggerRefactor = async () => {
    if (!patToken || !owner || !repo || !path || !instruction) {
      addLog("⚠️ Bitte alle Konfigurationsfelder ausfüllen!", "warn");
      return;
    }
    setLoading(true);
    setInReview(false);
    setLogs([]);

    const processedCode = await runRefactorPipeline(
      { patToken, owner, repo, branch, path, instruction },
      addLog
    );

    if (processedCode) {
      setFinalCode(processedCode);
      setInReview(true);
    } else {
      addLog(
        "❌ Pipeline fehlgeschlagen. Überarbeiteter Code instabil.",
        "error"
      );
    }
    setLoading(false);
  };

  // Push Trigger
  const executePush = async () => {
    setLoading(true);
    try {
      addLog("📤 Übermittle modifizierten Code an GitHub...", "info");
      await pushUpdatedCodeToGitHub({
        patToken,
        owner,
        repo,
        branch,
        path,
        code: finalCode,
        commitMessage: "🤖 Refactor: Code-Überarbeitung via APK Mobile Agent",
      });
      addLog("🚀 Datei erfolgreich auf GitHub aktualisiert!", "success");
      setInReview(false);
    } catch (e: any) {
      addLog(`❌ Push fehlgeschlagen: ${e.message}`, "error");
    }
    setLoading(false);
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        style={{ flex: 1 }}
      >
        <Text style={styles.title}>📱 In-APK Code Modifier</Text>

        {!inReview && (
          <ScrollView
            style={styles.form}
            keyboardShouldPersistTaps="handled"
          >
            {/* Groq API Key Section */}
            <View style={styles.apiKeySection}>
              <TextInput
                style={styles.input}
                placeholder="Groq API Key (für AI Refactoring)"
                secureTextEntry
                value={patToken}
                onChangeText={setPatToken}
                placeholderTextColor="#666"
              />
              <TouchableOpacity
                style={styles.helpBtn}
                onPress={openGroqConsole}
              >
                <Text style={styles.helpBtnText}>🔑 Kostenlosen Key holen</Text>
              </TouchableOpacity>
              <Text style={styles.helpHint}>
                Kostenloser Key: 30 Anfragen/Min, keine Kreditkarte nötig.
                {"\n"}Tippe auf "Kostenlosen Key holen" für die Anleitung.
              </Text>
            </View>

            <Text style={styles.sectionTitle}>📦 GitHub Konfiguration</Text>
            <View style={styles.row}>
              <TextInput
                style={[styles.input, { flex: 1, marginRight: 5 }]}
                placeholder="Owner (z.B. facebook)"
                value={owner}
                onChangeText={setOwner}
                placeholderTextColor="#666"
              />
              <TextInput
                style={[styles.input, { flex: 1 }]}
                placeholder="Repository Name"
                value={repo}
                onChangeText={setRepo}
                placeholderTextColor="#666"
              />
            </View>
            <View style={styles.row}>
              <TextInput
                style={[styles.input, { flex: 0.3, marginRight: 5 }]}
                placeholder="Branch"
                value={branch}
                onChangeText={setBranch}
                placeholderTextColor="#666"
              />
              <TextInput
                style={[styles.input, { flex: 0.7 }]}
                placeholder="Dateipfad (z.B. src/utils.ts)"
                value={path}
                onChangeText={setPath}
                placeholderTextColor="#666"
              />
            </View>
            <TextInput
              style={[styles.input, styles.txtArea]}
              placeholder="Welche Änderungen sollen vorgenommen werden?"
              multiline
              value={instruction}
              onChangeText={setInstruction}
              placeholderTextColor="#666"
            />

            <TouchableOpacity
              style={styles.btn}
              onPress={triggerRefactor}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.btnTxt}>Überarbeitung starten</Text>
              )}
            </TouchableOpacity>
          </ScrollView>
        )}

        {/* Live Terminal */}
        <Text style={styles.sectionLabel}>Terminal-Protokoll:</Text>
        <View style={[styles.terminal, inReview && { flex: 0.25 }]}>
          <ScrollView
            ref={termScroll}
            onContentSizeChange={() =>
              termScroll.current?.scrollToEnd({ animated: true })
            }
          >
            {logs.map((l) => (
              <Text
                key={l.id}
                style={[styles.logText, styles[l.type] as any]}
              >
                [{l.time}] {l.text}
              </Text>
            ))}
          </ScrollView>
        </View>

        {/* Review-Editor-Phase */}
        {inReview && (
          <View style={styles.editorContainer}>
            <Text style={styles.sectionLabel}>
              📝 Code-Review & finaler Feinschliff:
            </Text>
            <TextInput
              style={styles.editor}
              multiline
              value={finalCode}
              onChangeText={setFinalCode}
              autoCapitalize="none"
              autoCorrect={false}
            />
            <View style={styles.row}>
              <TouchableOpacity
                style={[styles.btn, { flex: 0.4, backgroundColor: "#6B7280" }]}
                onPress={() => setInReview(false)}
              >
                <Text style={styles.btnTxt}>Zurück</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[
                  styles.btn,
                  { flex: 0.55, backgroundColor: "#10B981" },
                ]}
                onPress={executePush}
              >
                <Text style={styles.btnTxt}>Änderung pushen</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
    padding: Spacing.md,
  },
  title: {
    fontSize: FontSize.lg,
    fontWeight: "bold",
    color: Colors.textPrimary,
    textAlign: "center",
    marginBottom: Spacing.md,
  },
  form: {
    flex: 1,
  },
  apiKeySection: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginBottom: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.primary,
  },
  sectionTitle: {
    color: Colors.primary,
    fontSize: FontSize.sm,
    fontWeight: "600",
    marginBottom: Spacing.sm,
  },
  helpBtn: {
    backgroundColor: Colors.primary,
    padding: Spacing.sm,
    borderRadius: BorderRadius.sm,
    alignItems: "center",
    marginTop: Spacing.xs,
  },
  helpBtnText: {
    color: Colors.background,
    fontWeight: "bold",
    fontSize: FontSize.sm,
  },
  helpHint: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
    marginTop: Spacing.xs,
    textAlign: "center",
  },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: Spacing.sm,
  },
  input: {
    backgroundColor: Colors.surface,
    color: Colors.textPrimary,
    padding: Spacing.sm,
    borderRadius: BorderRadius.sm,
    marginBottom: Spacing.sm,
    fontSize: FontSize.sm,
  },
  txtArea: {
    height: 60,
    textAlignVertical: "top",
  },
  btn: {
    backgroundColor: Colors.primary,
    padding: Spacing.sm,
    borderRadius: BorderRadius.sm,
    alignItems: "center",
    marginTop: Spacing.xs,
  },
  btnTxt: {
    color: Colors.textPrimary,
    fontWeight: "bold",
    fontSize: FontSize.sm,
  },
  sectionLabel: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
    fontWeight: "600",
    marginVertical: Spacing.sm,
  },
  terminal: {
    flex: 0.4,
    backgroundColor: "#000",
    borderRadius: BorderRadius.sm,
    padding: Spacing.sm,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  logText: {
    fontFamily: "monospace",
    fontSize: FontSize.xs,
    marginBottom: 2,
  },
  info: {
    color: "#E2E8F0",
  },
  success: {
    color: "#34D399",
    fontWeight: "bold",
  },
  warn: {
    color: "#FBBF24",
  },
  error: {
    color: "#F87171",
    fontWeight: "bold",
  },
  editorContainer: {
    flex: 1,
    marginTop: Spacing.xs,
  },
  editor: {
    flex: 1,
    backgroundColor: Colors.surface,
    color: "#38BDF8",
    fontFamily: "monospace",
    fontSize: FontSize.xs,
    padding: Spacing.sm,
    borderRadius: BorderRadius.sm,
    textAlignVertical: "top",
    borderWidth: 1,
    borderColor: Colors.border,
  },
});