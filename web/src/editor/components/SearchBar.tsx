import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { search, listTags } from '@/editor/services/vaultApi';
import type { SearchHit, SearchMode, TagCount, TagsOp } from '@/editor/types/vault';

const MODES: { value: SearchMode; label: string }[] = [
  { value: 'hybrid', label: 'H' },
  { value: 'exact', label: 'E' },
  { value: 'semantic', label: 'S' },
];

interface SearchBarProps {
  selectedLang: string;
  currentPath: string;
  onSelectPath: (path: string) => void;
  initialQ?: string;
  initialTags?: string[];
}

export default function SearchBar({ selectedLang, currentPath, onSelectPath, initialQ, initialTags }: SearchBarProps) {
  const [q, setQ] = useState(initialQ || '');
  const [mode, setMode] = useState<SearchMode>(() => {
    return (localStorage.getItem('vault-editor:searchMode') as SearchMode) || 'hybrid';
  });
  const [selectedTags, setSelectedTags] = useState<string[]>(initialTags || []);
  const [tagsOp, setTagsOp] = useState<TagsOp>('and');
  const [tagCandidates, setTagCandidates] = useState<TagCount[]>([]);
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submittedRef = useRef(false);

  const hasTags = tagCandidates.length > 0;

  useEffect(() => {
    setTagCandidates([]);
    setSelectedTags(prev => prev.filter(t => tagCandidates.some(tc => tc.tag === t)));
    if (selectedLang) {
      listTags(selectedLang).then(r => setTagCandidates(r.tags)).catch(() => {});
    }
  }, [selectedLang]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSearch = useCallback(async () => {
    if (!q.trim() || !selectedLang) return;
    submittedRef.current = true;
    setLoading(true);
    setError(null);
    try {
      const resp = await search(selectedLang, {
        q: q.trim(),
        mode,
        tags: selectedTags.length > 0 ? selectedTags : undefined,
        tags_op: selectedTags.length > 0 ? tagsOp : undefined,
      });
      setHits(resp.hits);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [q, mode, selectedTags, tagsOp, selectedLang]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSearch();
  }, [handleSearch]);

  const toggleTag = useCallback((tag: string) => {
    setSelectedTags(prev =>
      prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag],
    );
  }, []);

  const clearSearch = useCallback(() => {
    setQ('');
    setHits([]);
    setError(null);
    submittedRef.current = false;
  }, []);

  return (
    <div className="flex flex-col h-full">
      {/* Search input */}
      <div className="p-2 shrink-0">
        <div className="flex items-center gap-1">
          <Input
            placeholder="搜索…"
            value={q}
            onChange={e => setQ(e.target.value)}
            onKeyDown={handleKeyDown}
            className="h-7 text-xs"
          />
          <Button size="icon-xs" variant="outline" onClick={handleSearch} disabled={loading || !q.trim()}>
            <Search className="size-3" />
          </Button>
        </div>
      </div>

      {/* Mode toggle */}
      <div className="flex items-center gap-1 px-2 pb-1 shrink-0">
        {MODES.map(m => (
          <Button
            key={m.value}
            size="xs"
            variant={mode === m.value ? 'default' : 'outline'}
            onClick={() => {
              setMode(m.value);
              localStorage.setItem('vault-editor:searchMode', m.value);
            }}
          >
            {m.label}
          </Button>
        ))}
      </div>

      {/* Tags */}
      {hasTags && (
        <div className="flex flex-wrap items-center gap-1 px-2 pb-1 shrink-0">
          {tagCandidates.map(tc => {
            const selected = selectedTags.includes(tc.tag);
            return (
              <Button
                key={tc.tag}
                size="xs"
                variant={selected ? 'default' : 'outline'}
                onClick={() => toggleTag(tc.tag)}
              >
                {tc.tag}
                {selected && <X className="size-2.5 ml-0.5" />}
              </Button>
            );
          })}
        </div>
      )}

      {/* tags_op toggle */}
      {selectedTags.length > 1 && (
        <div className="flex items-center gap-1 px-2 pb-1 shrink-0">
          <span className="text-[10px] text-muted-foreground">匹配：</span>
          <Button
            size="xs"
            variant={tagsOp === 'and' ? 'default' : 'outline'}
            onClick={() => setTagsOp('and')}
          >
            全部
          </Button>
          <Button
            size="xs"
            variant={tagsOp === 'or' ? 'default' : 'outline'}
            onClick={() => setTagsOp('or')}
          >
            任一
          </Button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="px-2 py-1 text-[11px] text-red-500 shrink-0">
          {error}
        </div>
      )}

      {/* Clear search hint */}
      {submittedRef.current && hits.length === 0 && !loading && (
        <div className="flex items-center justify-between px-2 py-1 shrink-0">
          <span className="text-[11px] text-muted-foreground">无结果</span>
          <Button size="xs" variant="ghost" onClick={clearSearch}>清除</Button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="px-2 py-2 text-xs text-muted-foreground shrink-0">搜索中…</div>
      )}

      {/* Results */}
      {!loading && hits.length > 0 && (
        <div className="flex-1 overflow-y-auto border-t border-border">
          {hits.map(hit => {
            const isCurrent = hit.file_path === currentPath;
            return (
              <button
                key={hit.ulid}
                className={`w-full text-left px-2 py-1.5 border-b border-border/50 hover:bg-muted/50 transition-colors ${isCurrent ? 'bg-muted' : ''}`}
                onClick={() => onSelectPath(hit.file_path)}
              >
                <div className="flex items-center justify-between gap-1">
                  <span className="text-xs font-medium truncate text-foreground">{hit.title || hit.file_path}</span>
                  <span className="text-[10px] text-muted-foreground shrink-0">{hit.item_type || '—'}</span>
                </div>
                <div className="flex items-center gap-1 mt-0.5">
                  <span className="text-[10px] text-muted-foreground bg-muted/50 rounded px-1">{hit.source}</span>
                  <span className="text-[10px] text-muted-foreground">{hit.score.toFixed(3)}</span>
                </div>
                {hit.snippet && (
                  <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-3 leading-relaxed">{hit.snippet}</p>
                )}
                <p className="text-[10px] text-muted-foreground/60 mt-0.5 truncate">{hit.file_path}</p>
              </button>
            );
          })}
        </div>
      )}

      {/* Submit hint when no results yet */}
      {!submittedRef.current && !loading && (
        <div className="flex-1 flex items-center justify-center px-2 text-[11px] text-muted-foreground">
          输入关键词搜索
        </div>
      )}
    </div>
  );
}
