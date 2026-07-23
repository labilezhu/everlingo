import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronRight, ChevronDown, File, Folder, FilePlus, FolderPlus, Pencil, RefreshCw, Trash2 } from 'lucide-react';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import { Input } from '@/components/ui/input';
import type { Entry } from '@/editor/types/vault';

type InlineAction =
  | { kind: 'new-file'; parent: Entry | null }
  | { kind: 'new-dir'; parent: Entry | null }
  | { kind: 'rename'; entry: Entry };

interface FileTreeProps {
  entries: Entry[];
  selectedPath?: string;
  onSelect: (path: string) => void;
  onLazyLoad: (dirPath: string) => Promise<void>;
  onCreateFile: (parent: Entry | null, name: string) => void;
  onMkdir: (parent: Entry | null, name: string) => void;
  onRename: (entry: Entry, newName: string) => void;
  onDelete: (entry: Entry) => void;
  onRefresh: () => void;
  refreshing: boolean;
}

export default function FileTree({ entries, selectedPath, onSelect, onLazyLoad, onCreateFile, onMkdir, onRename, onDelete, onRefresh, refreshing }: FileTreeProps) {
  return (
    <div className="flex flex-col h-full">
      {/* header toolbar */}
      <div className="flex items-center justify-end gap-1 px-2 py-1 border-b border-border shrink-0">
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          title="刷新"
          className="inline-flex items-center justify-center size-6 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-40 disabled:pointer-events-none"
        >
          <RefreshCw className={`size-3.5 ${refreshing ? 'animate-spin' : ''}`} />
        </button>
      </div>
      {/* tree */}
      <div className="flex-1 overflow-y-auto">
        {entries.map(entry => (
          <FileTreeNode
            key={entry.path}
            entry={entry}
            depth={0}
            selectedPath={selectedPath}
            onSelect={onSelect}
            onLazyLoad={onLazyLoad}
            onCreateFile={onCreateFile}
            onMkdir={onMkdir}
            onRename={onRename}
            onDelete={onDelete}
          />
        ))}
      </div>
    </div>
  );
}

interface FileTreeNodeProps {
  entry: Entry;
  depth: number;
  selectedPath?: string;
  onSelect: (path: string) => void;
  onLazyLoad: (dirPath: string) => Promise<void>;
  onCreateFile: (parent: Entry | null, name: string) => void;
  onMkdir: (parent: Entry | null, name: string) => void;
  onRename: (entry: Entry, newName: string) => void;
  onDelete: (entry: Entry) => void;
}

function FileTreeNode({ entry, depth, selectedPath, onSelect, onLazyLoad, onCreateFile, onMkdir, onRename, onDelete }: FileTreeNodeProps) {
  const [expanded, setExpanded] = useState(depth === 0);
  const [loading, setLoading] = useState(false);
  const [inlineAction, setInlineAction] = useState<InlineAction | null>(null);

  const needsLoad = !entry.loaded && (!entry.children || entry.children.length === 0);

  const handleDirClick = useCallback(async () => {
    if (needsLoad) {
      // 未加载（含刷新后 children 被重置为空壳的情况）：仅加载，不折叠
      if (!expanded) setExpanded(true);
      setLoading(true);
      try {
        await onLazyLoad(entry.path);
      } finally {
        setLoading(false);
      }
      return;
    }
    setExpanded(e => !e);
  }, [needsLoad, expanded, entry, onLazyLoad]);

  const isDir = entry.type === 'dir';

  const row = (
    <div>
      {isDir ? (
        <button
          className="flex w-full items-center gap-1 px-2 py-1 text-left text-sm hover:bg-muted"
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
          onClick={handleDirClick}
        >
          {loading ? (
            <span className="size-3.5 shrink-0 text-muted-foreground">…</span>
          ) : expanded ? (
            <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
          )}
          <Folder className="size-4 shrink-0 text-muted-foreground" />
          <span className="truncate">{entry.name}</span>
        </button>
      ) : (
        <button
          className={`flex w-full items-center gap-1 px-2 py-1 text-left text-sm hover:bg-muted ${selectedPath === entry.path ? 'bg-muted font-medium text-foreground' : 'text-muted-foreground'}`}
          style={{ paddingLeft: `${depth * 16 + 24}px` }}
          onClick={() => onSelect(entry.path)}
        >
          <File className="size-4 shrink-0" />
          <span className="truncate">{entry.name}</span>
        </button>
      )}
    </div>
  );

  const menuItems = (
    <ContextMenuContent>
      {isDir && (
        <>
          <ContextMenuItem onClick={() => setInlineAction({ kind: 'new-file', parent: entry })}>
            <FilePlus className="size-4" />
            新建文件
          </ContextMenuItem>
          <ContextMenuItem onClick={() => setInlineAction({ kind: 'new-dir', parent: entry })}>
            <FolderPlus className="size-4" />
            新建目录
          </ContextMenuItem>
          <ContextMenuSeparator />
        </>
      )}
      <ContextMenuItem onClick={() => setInlineAction({ kind: 'rename', entry })}>
        <Pencil className="size-4" />
        重命名
      </ContextMenuItem>
      <ContextMenuItem
        variant="destructive"
        onClick={() => {
          if (confirm(`确定删除「${entry.name}」？此操作不可撤销。`)) {
            onDelete(entry);
          }
        }}
      >
        <Trash2 className="size-4" />
        删除
      </ContextMenuItem>
    </ContextMenuContent>
  );

  return (
    <ContextMenu>
      <ContextMenuTrigger className="select-none">
        {row}
      </ContextMenuTrigger>
      {menuItems}
      {inlineAction && (
        <InlineInput
          entry={entry}
          action={inlineAction}
          depth={depth}
          onConfirm={(name) => {
            const a = inlineAction;
            setInlineAction(null);
            if (a.kind === 'new-file') {
              onCreateFile(a.parent, name);
            } else if (a.kind === 'new-dir') {
              onMkdir(a.parent, name);
            } else if (a.kind === 'rename') {
              onRename(a.entry, name);
            }
          }}
          onCancel={() => setInlineAction(null)}
        />
      )}
      {isDir && expanded && entry.children && (
        <div>
          {entry.children.map(child => (
            <FileTreeNode
              key={child.path}
              entry={child}
              depth={depth + 1}
              selectedPath={selectedPath}
              onSelect={onSelect}
              onLazyLoad={onLazyLoad}
              onCreateFile={onCreateFile}
              onMkdir={onMkdir}
              onRename={onRename}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}
    </ContextMenu>
  );
}

// ── Inline input for new-file / new-dir / rename ──

interface InlineInputProps {
  entry: Entry;
  action: InlineAction;
  depth: number;
  onConfirm: (name: string) => void;
  onCancel: () => void;
}

function InlineInput({ entry, action, depth, onConfirm, onCancel }: InlineInputProps) {
  const [value, setValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      const trimmed = value.trim();
      if (!trimmed) return;
      if (action.kind === 'new-file') {
        onConfirm(trimmed.endsWith('.md') ? trimmed : trimmed + '.md');
      } else {
        onConfirm(trimmed);
      }
    } else if (e.key === 'Escape') {
      onCancel();
    }
  };

  const placeholder = action.kind === 'new-file'
    ? '文件名（自动 .md）'
    : action.kind === 'new-dir'
      ? '目录名'
      : '新名称';

  return (
    <div style={{ paddingLeft: `${depth * 16 + (action.kind === 'rename' ? 24 : 8)}px` }} className="flex items-center gap-1 px-2 py-0.5">
      <Input
        ref={inputRef}
        className="h-6 text-xs"
        placeholder={placeholder}
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={() => {
          if (!value.trim()) onCancel();
        }}
      />
    </div>
  );
}