// Backup API 类型（/api/backup/*）。
// ref: docs/ADR/20260810-vault-version-control.md — P3 UI console

export interface BackupStatus {
  enabled: boolean;
  initialized: boolean;
  dirty: boolean;
  has_commits: boolean;
  last_commit_at: string | null;
  last_push_at: string | null;
  remote_configured: boolean;
  ahead: number;
  behind: number;
  branch: string;
  remote_url: string;
}

export interface BackupConfig {
  enabled: boolean;
  remote_url: string;
  branch: string;
  commit_interval: number;
  push_interval: number;
  auth: {
    method: 'ssh' | 'https_none' | 'https_pat';
    ssh_private_key_file: string;
    pat: string;
  };
}

export interface BackupLogEntry {
  hash: string;
  time: string;
  message: string;
}

export interface BackupLogResponse {
  commits: BackupLogEntry[];
}

export interface BackupTestResponse {
  ok: boolean;
  message: string;
}

export interface BackupResultResponse {
  ok: boolean;
  backup_branch: string | null;
  conflicts: string[];
  message: string;
}
