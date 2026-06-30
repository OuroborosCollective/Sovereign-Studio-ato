import React from 'react';
import { AuditLiveWorkbench } from './features/product/components/AuditLiveWorkbench';

export default function App() {
  return <AuditLiveWorkbench mission="x" repoReady={false} repoReason="x" repoBusy={false} runtimeBusy={false} isPublishing={false} sovereignSummary="x" sovereignPreview="" onMissionChange={() => {}} onGenerateIdeas={() => {}} onGenerateErrorWorkflow={() => {}} onPublishDraftPr={() => {}} />;
}
