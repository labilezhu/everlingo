import { useCallback, useRef, useState } from 'react';
import { ChevronRight, ChevronDown, File, Folder } from 'lucide-react';
import type { Entry } from '@/editor/types/vault';

interface FileTreeProps {
  entries: Entry[];
  selectedPath?: string;
  onSelect: (path: string) => void;
  onLazyLoad: (dirPath: string) => Promise<void>;
}

export default function FileTree({ entries, selectedPath, onSelect, onLazyLoad }: FileTreeProps) {
  return (
    <div className="overflow-y-auto">
      {entries.map(entry => (
        <FileTreeNode
          key={entry.path}
          entry={entry}
          depth={0}
          selectedPath={selectedPath}
          onSelect={onSelect}
          onLazyLoad={onLazyLoad}
        />
      ))}
    </div>
  );
}

interface FileTreeNodeProps {
  entry: Entry;
  depth: number;
  selectedPath?: string;
  onSelect: (path: string) => void;
  onLazyLoad: (dirPath: string) => Promise<void>;
}

function FileTreeNode({ entry, depth, selectedPath, onSelect, onLazyLoad }: FileTreeNodeProps) {
  const [expanded, setExpanded] = useState(depth === 0);
  const [loading, setLoading] = useState(false);
  const loadedRef = useRef(false);

  const handleDirClick = useCallback(async () => {
    if (!expanded) {
      setExpanded(true);
      const needsLoad = !loadedRef.current && (!entry.children || entry.children.length === 0);
      if (needsLoad) {
        loadedRef.current = true;
        setLoading(true);
        try {
          await onLazyLoad(entry.path);
        } finally {
          setLoading(false);
        }
      }
    } else {
      setExpanded(false);
    }
  }, [expanded, entry, onLazyLoad]);

  if (entry.type === 'dir') {
    return (
      <div>
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
        {expanded && entry.children && (
          <div>
            {entry.children.map(child => (
              <FileTreeNode
                key={child.path}
                entry={child}
                depth={depth + 1}
                selectedPath={selectedPath}
                onSelect={onSelect}
                onLazyLoad={onLazyLoad}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  const isSelected = selectedPath === entry.path;
  return (
    <button
      className={`flex w-full items-center gap-1 px-2 py-1 text-left text-sm hover:bg-muted ${isSelected ? 'bg-muted font-medium text-foreground' : 'text-muted-foreground'}`}
      style={{ paddingLeft: `${depth * 16 + 24}px` }}
      onClick={() => onSelect(entry.path)}
    >
      <File className="size-4 shrink-0" />
      <span className="truncate">{entry.name}</span>
    </button>
  );
}
