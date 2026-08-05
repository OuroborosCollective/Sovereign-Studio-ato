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
import {
  runRefactorPipeline,
  type LogItem,
  type RefactorReview,
} from '../agents/orchestrator';
import { createDraftPatch } from '../services/githubService';
import { Colors, FontSize, Spacing, BorderRadius } from '../utils/theme';

function buildDraftBranchName(path: string, sourceSha: string): string {
  const normalizedPath = path
    .toLowerCase()
    .replace(/[^a-z0-9/_-]+/g, '-')
    .replace(/[/_]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 48);
  if (!normalizedPath || !/^[0-9a-f]{40}$/.test(sourceSha)) {
    throw new Error('Dateipfad oder GitHub-SHA ist nicht revisionsfähig.');
  }
  return `sovereign/mobile-refactor/${normalizedPath}-${sourceSha.slice(0, 12)}`;
}

export function CodeRefactorScreen() {
  // Config States
  const [owner, setOwner] = useState("");
  const [repo, setRepo] = useState("");
  const [branch, setBranch] = useState("main");
  const [path, setPath] = useState("src/App.tsx");
  const [instruction, setInstruction] = useState("");

  // App-State
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [finalCode, setFinalCode] = useState('');
  const [review, setReview] = useState<RefactorReview | null>(null);
  const [inReview, setInReview] = useState(false);
  const [draftPrUrl, setDraftPrUrl] = useState('');

  const termScroll = useRef<ScrollView>(null);
  const logSequence = useRef(0);

  const addLog = (text: string, type: LogItem['type'] = 'info') => {
    logSequence.current += 1;
    setLogs((prev) => [
      ...prev,
      {
        id: `mobile-refactor-log-${logSequence.current}`,
        time: new Date().toLocaleTimeString(),
        type,
        text,
      },
    ]);
  };

  const triggerRefactor = async () => {
    if (!owner || !repo || !branch || !path || !instruction) {
      addLog('⚠️ Bitte Repository, Branch, Dateipfad und Änderungsauftrag vollständig angeben.', 'warn');
      return;
    }
    setLoading(true);
    setInReview(false);
    setReview(null);
    setDraftPrUrl('');
    setLogs([]);

    const candidate = await runRefactorPipeline(
      { owner, repo, branch, path, instruction },
      addLog,
    );

    if (candidate) {
      setReview(candidate);
      setFinalCode(candidate.updatedCode);
      setInReview(true);
    } else {
      addLog('❌ Es wurde kein revisionsfähiger Änderungskandidat erzeugt.', 'error');
    }
    setLoading(false);
  };

  const executeDraftPr = async () => {
    if (!review) {
      addLog('❌ Die revisionsgebundene Ausgangsfassung fehlt.', 'error');
      return;
    }
    setLoading(true);
    try {
      const branchName = buildDraftBranchName(path, review.sourceSha);
      addLog('📤 Fordere über den Sovereign-Gateway einen CAS-gebundenen Draft-PR an.', 'info');
      const result = await createDraftPatch({
        owner,
        repo,
        branch,
        path,
        originalContent: review.originalCode,
        updatedContent: finalCode,
        expectedFileSha: review.sourceSha,
        commitMessage: `Refactor: revisionsgebundene Änderung an ${path}`,
        branchName,
        title: `Draft: revisionsgebundener Mobile-Refactor für ${path}`,
        body: [
          'Dieser Draft-PR wurde über die sessiongeschützte Sovereign-Backend-Grenze erzeugt.',
          `Ausgangs-SHA: ${review.sourceSha}`,
          'Die lokale Kandidatenprüfung beweist weder Build noch CI, Merge, Deployment oder Runtime-Erfolg.',
        ].join('\n\n'),
        baseBranch: branch,
      });
      setDraftPrUrl(result.prUrl);
      addLog(`✅ Draft-PR #${result.prNumber} erstellt; Merge und CI bleiben ausdrücklich offen.`, 'success');
      setInReview(false);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Unbekannter Draft-PR-Fehler';
      addLog(`❌ Draft-PR-Erstellung fehlgeschlagen: ${message}`, 'error');
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
            <View style={styles.gatewaySection}>
              <Text style={styles.gatewayTitle}>🔐 Sessiongebundener GitHub-Gateway</Text>
              <Text style={styles.gatewayHint}>
                GitHub-Zugriff erfolgt ausschließlich über deine aktive Sovereign-Backend-Session.
                {'\n'}Kein PAT oder Provider-Schlüssel wird im Gerät abgefragt oder gespeichert.
                {'\n'}Änderungen werden nur als CAS-gebundener Draft-PR angelegt.
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

        {draftPrUrl ? (
          <TouchableOpacity
            style={styles.prLink}
            onPress={() => Linking.openURL(draftPrUrl)}
          >
            <Text style={styles.prLinkText}>Erstellten Draft-PR öffnen</Text>
          </TouchableOpacity>
        ) : null}

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
                onPress={executeDraftPr}
                disabled={loading || !review}
              >
                <Text style={styles.btnTxt}>Draft-PR erstellen</Text>
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
  gatewaySection: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginBottom: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.primary,
  },
  gatewayTitle: {
    color: Colors.primary,
    fontSize: FontSize.sm,
    fontWeight: '700',
    marginBottom: Spacing.xs,
  },
  gatewayHint: {
    color: Colors.textMuted,
    fontSize: FontSize.xs,
    lineHeight: 18,
  },
  sectionTitle: {
    color: Colors.primary,
    fontSize: FontSize.sm,
    fontWeight: "600",
    marginBottom: Spacing.sm,
  },
  prLink: {
    backgroundColor: Colors.surface,
    borderColor: Colors.primary,
    borderWidth: 1,
    borderRadius: BorderRadius.sm,
    padding: Spacing.sm,
    alignItems: 'center',
    marginBottom: Spacing.xs,
  },
  prLinkText: {
    color: Colors.primary,
    fontSize: FontSize.sm,
    fontWeight: '700',
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