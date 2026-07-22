import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Code, Eye, Save, FileCode, Search, FolderTree } from 'lucide-react';
import { listLangs, tree, read, write, mkdir, deleteEntry, rename } from '@/editor/services/vaultApi';
import FileTree from './FileTree';
import SearchBar from './SearchBar';
import MilkdownEditor from './MilkdownEditor';
import type { Entry } from '@/editor/types/vault';

function mergeChildren(entries: Entry[], dirPath: string, newChildren: Entry[]): Entry[] {
  return entries.map(entry => {
    if (entry.path === dirPath) {
      return { ...entry, children: newChildren };
    }
    if (entry.children && entry.children.length > 0) {
      return { ...entry, children: mergeChildren(entry.children, dirPath, newChildren) };
    }
    return entry;
  });
}

type LeftTab = 'files' | 'search';

export default function EditorApp() {
  // ── state ──
  const [langs, setLangs] = useState<string[]>([]);
  const [selectedLang, setSelectedLang] = useState<string>('');
  const [entries, setEntries] = useState<Entry[]>([]);
  const [currentPath, setCurrentPath] = useState<string>('');
  const [content, setContent] = useState('');
  const [originalContent, setOriginalContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [treeRefreshing, setTreeRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [mode, setMode] = useState<'source' | 'wysiwyg'>(() => {
    return (localStorage.getItem('vault-editor:mode') as 'source' | 'wysiwyg') || 'wysiwyg';
  });
  const [leftTab, setLeftTab] = useState<LeftTab>(() => {
    const urlQ = new URLSearchParams(location.search).get('q');
    if (urlQ) return 'search';
    return (localStorage.getItem('vault-editor:leftTab') as LeftTab) || 'files';
  });
  const [leftPct, setLeftPct] = useState(() => {
    const saved = localStorage.getItem('vault-editor:leftPanePct');
    if (saved) {
      const n = parseFloat(saved);
      if (!isNaN(n)) return Math.min(50, Math.max(15, n));
    }
    return 22;
  });

  const bodyRef = useRef<HTMLDivElement>(null);
  const dirty = content !== originalContent;

  // ── frontmatter stripping for WYSIWYG ──
  const { fm, body } = useMemo(() => {
    if (mode !== 'wysiwyg') return { fm: '', body: content };
    const m = /^---\r?\n[\s\S]*?\r?\n---\r?\n?/.exec(content);
    if (m) return { fm: m[0], body: content.slice(m[0].length) };
    return { fm: '', body: content };
  }, [content, mode]);

  // ── parse URL params ──
  const params = useMemo(() => new URLSearchParams(location.search), []);
  const initLang = params.get('lang') || '';
  const initPath = params.get('path') || '';
  const initQ = params.get('q') || '';
  const initTags = useMemo(() => {
    const t = params.getAll('tag');
    return t.length > 0 ? t : undefined;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── init: fetch langs ──
  useEffect(() => {
    setLoading(true);
    listLangs()
      .then(resp => {
        const v = resp.vaults;
        setLangs(v);
        const pre = initLang && v.includes(initLang) ? initLang : (v[0] || '');
        setSelectedLang(pre);
        return pre;
      })
      .then(lang => {
        if (!lang) return;
        return tree(lang).then(resp => {
          setEntries(resp.entries);
          if (initPath) {
            read(lang, initPath).then(r => {
              setCurrentPath(initPath);
              setContent(r.content);
              setOriginalContent(r.content);
            }).catch(e => setError(e.message));
          }
        });
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── lang change ──
  const handleLangChange = useCallback(async (newLang: string) => {
    if (dirty && !confirm('有未保存的改动，切换语言将丢弃。确定继续？')) return;
    setSelectedLang(newLang);
    setCurrentPath('');
    setContent('');
    setOriginalContent('');
    setError(null);
    setLoading(true);
    try {
      const resp = await tree(newLang);
      setEntries(resp.entries);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [dirty]);

  // ── file select ──
  const handleFileSelect = useCallback(async (path: string) => {
    if (dirty && !confirm('有未保存的改动，切换文件将丢弃。确定继续？')) return;
    if (!selectedLang) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await read(selectedLang, path);
      setCurrentPath(path);
      setContent(resp.content);
      setOriginalContent(resp.content);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [dirty, selectedLang]);

  // ── save ──
  const handleSave = useCallback(async () => {
    if (!selectedLang || !currentPath || !dirty || saving) return;
    setSaving(true);
    setError(null);
    try {
      await write(selectedLang, currentPath, content);
      setOriginalContent(content);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }, [selectedLang, currentPath, content, dirty, saving]);

  // ── refresh tree ──
  const refreshTree = useCallback(async () => {
    if (!selectedLang) return;
    setTreeRefreshing(true);
    setError(null);
    try {
      const resp = await tree(selectedLang);
      setEntries(resp.entries);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setTreeRefreshing(false);
    }
  }, [selectedLang]);

  // ── lazy load dir ──
  const handleLazyLoad = useCallback(async (dirPath: string) => {
    if (!selectedLang) return;
    const resp = await tree(selectedLang, dirPath, 2);
    setEntries(prev => mergeChildren(prev, dirPath, resp.entries));
  }, [selectedLang]);

  // ── create file ──
  const handleCreateFile = useCallback(async (parent: Entry | null, name: string) => {
    if (!selectedLang) return;
    const fullPath = parent ? `${parent.path}/${name}` : name;
    setLoading(true);
    setError(null);
    try {
      await write(selectedLang, fullPath, '');
      await refreshTree();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedLang, refreshTree]);

  // ── mkdir ──
  const handleMkdir = useCallback(async (parent: Entry | null, name: string) => {
    if (!selectedLang) return;
    const fullPath = parent ? `${parent.path}/${name}` : name;
    setLoading(true);
    setError(null);
    try {
      await mkdir(selectedLang, fullPath);
      await refreshTree();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedLang, refreshTree]);

  // ── rename ──
  const handleRename = useCallback(async (entry: Entry, newName: string) => {
    if (!selectedLang) return;
    const parentDir = entry.path.includes('/') ? entry.path.slice(0, entry.path.lastIndexOf('/')) : '';
    const target = parentDir ? `${parentDir}/${newName}` : newName;
    setLoading(true);
    setError(null);
    try {
      await rename(selectedLang, entry.path, target);
      if (currentPath === entry.path) {
        setCurrentPath(target);
      } else if (entry.type === 'dir' && currentPath && (currentPath === entry.path || currentPath.startsWith(entry.path + '/'))) {
        setCurrentPath('');
        setContent('');
        setOriginalContent('');
      }
      await refreshTree();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedLang, currentPath, refreshTree]);

  // ── delete ──
  const handleDelete = useCallback(async (entry: Entry) => {
    if (!selectedLang) return;
    setLoading(true);
    setError(null);
    try {
      await deleteEntry(selectedLang, entry.path);
      if (currentPath === entry.path || (currentPath && currentPath.startsWith(entry.path + '/'))) {
        setCurrentPath('');
        setContent('');
        setOriginalContent('');
      }
      await refreshTree();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedLang, currentPath, refreshTree]);

  // ── beforeunload ──
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, []);

  // ── sync URL ──
  useEffect(() => {
    const params = new URLSearchParams();
    if (selectedLang) params.set('lang', selectedLang);
    if (currentPath) params.set('path', currentPath);
    const qs = params.toString();
    const newUrl = qs ? `${location.pathname}?${qs}` : location.pathname;
    history.replaceState(null, '', newUrl);
  }, [selectedLang, currentPath]);

  // ── render ──
  return (
    <div className="flex flex-col h-screen border-x border-border">
      {/* Header */}
      <header className="flex items-center justify-between gap-3 px-4 py-2 border-b border-border bg-background shrink-0">
        <div className="flex items-center gap-2">
          <FileCode className="size-5 text-muted-foreground" />
          <span className="text-sm font-semibold text-foreground">Vault Editor</span>
        </div>

        <div className="flex items-center gap-3">
          {langs.length > 0 && (
            <select
              className="h-8 rounded-lg border border-border bg-background px-2 text-sm text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              value={selectedLang}
              onChange={e => handleLangChange(e.target.value)}
            >
              {langs.map(l => <option key={l} value={l}>{l}</option>)}
            </select>
          )}

          <div className="flex items-center gap-1 rounded-lg border border-border p-0.5">
            <button
              className={'flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-all outline-none focus-visible:ring-3 focus-visible:ring-ring/50 ' + (mode === 'source' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
              onClick={() => {
                setMode('source');
                localStorage.setItem('vault-editor:mode', 'source');
              }}
            >
              <Code className="size-3.5" />
              Source
            </button>
            <button
              className={'flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-all outline-none focus-visible:ring-3 focus-visible:ring-ring/50 ' + (mode === 'wysiwyg' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
              onClick={() => {
                setMode('wysiwyg');
                localStorage.setItem('vault-editor:mode', 'wysiwyg');
              }}
            >
              <Eye className="size-3.5" />
              WYSIWYG
            </button>
          </div>

          <button
            className="inline-flex items-center gap-1 h-8 rounded-lg px-3 text-sm font-medium transition-all outline-none disabled:opacity-40 disabled:pointer-events-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50
              enabled:hover:bg-primary/80
              enabled:active:translate-y-px
              enabled:bg-primary enabled:text-primary-foreground"
            disabled={!dirty || saving}
            onClick={handleSave}
          >
            <Save className="size-4" />
            {saving ? '保存中…' : '保存'}
          </button>
        </div>
      </header>

      {/* Error bar */}
      {error && (
        <div className="px-4 py-2 bg-red-50 text-red-600 text-sm border-b border-red-200 shrink-0">
          {error}
          <button className="ml-2 underline" onClick={() => setError(null)}>关闭</button>
        </div>
      )}

      {/* Body */}
      <div ref={bodyRef} className="flex flex-1 overflow-hidden">
        {/* Left pane: tab bar + content */}
        <aside
          className="flex flex-col shrink-0 border-r border-border bg-background"
          style={{ width: `${leftPct}%` }}
        >
          {/* Tab bar */}
          <div className="flex items-center gap-0.5 px-1 py-1 border-b border-border shrink-0">
            <button
              className={`flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-all outline-none focus-visible:ring-3 focus-visible:ring-ring/50 ${
                leftTab === 'files'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
              onClick={() => {
                setLeftTab('files');
                localStorage.setItem('vault-editor:leftTab', 'files');
              }}
            >
              <FolderTree className="size-3.5" />
              Files
            </button>
            <button
              className={`flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-all outline-none focus-visible:ring-3 focus-visible:ring-ring/50 ${
                leftTab === 'search'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
              onClick={() => {
                setLeftTab('search');
                localStorage.setItem('vault-editor:leftTab', 'search');
              }}
            >
              <Search className="size-3.5" />
              Search
            </button>
          </div>

          {/* FileTree tab */}
          <div className={leftTab === 'files' ? 'flex-1 flex flex-col overflow-hidden' : 'hidden'}>
            {loading && !currentPath ? (
              <div className="p-4 text-sm text-muted-foreground">加载中…</div>
            ) : (
              <FileTree
                entries={entries}
                selectedPath={currentPath}
                onSelect={handleFileSelect}
                onLazyLoad={handleLazyLoad}
                onCreateFile={handleCreateFile}
                onMkdir={handleMkdir}
                onRename={handleRename}
                onDelete={handleDelete}
                onRefresh={refreshTree}
                refreshing={treeRefreshing}
              />
            )}
          </div>

          {/* SearchBar tab */}
          <div className={leftTab === 'search' ? 'flex-1 flex flex-col overflow-hidden' : 'hidden'}>
            <SearchBar
              selectedLang={selectedLang}
              currentPath={currentPath}
              onSelectPath={handleFileSelect}
              initialQ={initQ}
              initialTags={initTags}
            />
          </div>
        </aside>

        {/* Resize handle */}
        <div
          className="w-1 shrink-0 cursor-col-resize hover:bg-ring/30 active:bg-ring/40 transition-colors"
          onPointerDown={e => {
            const container = bodyRef.current;
            if (!container) return;
            const rect = container.getBoundingClientRect();
            const handlePointerMove = (ev: PointerEvent) => {
              const pct = Math.min(50, Math.max(15, ((ev.clientX - rect.left) / rect.width) * 100));
              setLeftPct(pct);
            };
            const handlePointerUp = (ev: PointerEvent) => {
              const pct = Math.min(50, Math.max(15, ((ev.clientX - rect.left) / rect.width) * 100));
              setLeftPct(pct);
              localStorage.setItem('vault-editor:leftPanePct', String(pct));
              document.removeEventListener('pointermove', handlePointerMove);
              document.removeEventListener('pointerup', handlePointerUp);
            };
            document.addEventListener('pointermove', handlePointerMove);
            document.addEventListener('pointerup', handlePointerUp);
          }}
        />

        {/* Right: editor */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {currentPath ? (
            <>
              <div className="px-4 py-1.5 text-xs text-muted-foreground border-b border-border shrink-0 bg-muted/30 truncate">
                {currentPath}
              </div>
              <div className="flex-1 overflow-auto">
                <MilkdownEditor
                  key={`${mode}:${currentPath || ''}`}
                  content={mode === 'wysiwyg' ? body : content}
                  onChange={mode === 'wysiwyg' ? (v) => setContent(fm + v) : setContent}
                  mode={mode}
                />
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
              {loading ? '加载中…' : '选择一个文件开始编辑'}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
