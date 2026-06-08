import React from 'react';
import { RepoFile } from '../types';

interface RepoFileListProps {
  files: RepoFile[];
}

export const RepoFileList: React.FC<RepoFileListProps> = ({ files }) => {
  return (
    <div>
      {files.map((f) => (
        <div key={f.path}>{f.path}</div>
      ))}
    </div>
  );
};
