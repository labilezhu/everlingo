import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Code, Eye, Save, Search, FolderTree, Menu, MessageSquare, ExternalLink } from 'lucide-react';
import { listLangs, tree, read, write, mkdir, deleteEntry, rename } from '@/editor/services/vaultApi';
import FileTree from './FileTree';
import SearchBar from './SearchBar';
import MilkdownEditor from './MilkdownEditor';
import ChatWindow from '@/components/ChatWindow';
import { useMediaQuery } from '@/editor/hooks/useMediaQuery';
import type { Entry } from '@/editor/types/vault';

function mergeChildren(entries: Entry[], dirPath: string, newChildren: Entry[]): Entry[] {
  return entries.map(entry => {
    if (entry.path === dirPath) {
      return { ...entry, children: newChildren, loaded: true };
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

  const [chatMounted, setChatMounted] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [leftOpen, setLeftOpen] = useState(false);
  const [chatPct, setChatPct] = useState(() => {
    const saved = localStorage.getItem('vault-editor:chatPanePct');
    if (saved) {
      const n = parseFloat(saved);
      if (!isNaN(n)) return Math.min(50, Math.max(20, n));
    }
    return 32;
  });

  const bodyRef = useRef<HTMLDivElement>(null);
  const dirty = content !== originalContent;
  const isDesktop = useMediaQuery('(min-width: 768px)');

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
            openFileContent(lang, initPath).catch(e => setError(e.message));
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

  // ── open file content (read + set states) ──
  const openFileContent = useCallback(async (lang: string, path: string) => {
    const resp = await read(lang, path);
    setCurrentPath(path);
    setContent(resp.content);
    setOriginalContent(resp.content);
  }, []);

  // ── load file with optional lang switch ──
  const loadFile = useCallback(async (lang: string, path: string) => {
    setLoading(true);
    setError(null);
    try {
      if (lang !== selectedLang) {
        setSelectedLang(lang);
        const treeResp = await tree(lang);
        setEntries(treeResp.entries);
      }
      await openFileContent(lang, path);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedLang, openFileContent]);

  // ── chatbot link click handler ──
  const handleChatLinkClick = useCallback((url: string): boolean => {
    let u: URL;
    try {
      u = new URL(url, location.origin);
    } catch {
      return false;
    }
    if (u.origin !== location.origin) return false;
    if (u.pathname !== '/editor') return false;
    const lang = u.searchParams.get('lang');
    const path = u.searchParams.get('path');
    if (!lang || !path) return false;
    if (!langs.includes(lang)) return false;
    if (dirty && !confirm('有未保存的改动，打开链接将丢弃。确定继续？')) return true;
    void loadFile(lang, path);
    return true;
  }, [langs, dirty, loadFile]);

  // ── editor WYSIWYG link click handler ──
  const handleEditorLinkClick = useCallback((href: string): boolean => {
    // 1. Absolute URL with protocol
    if (/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(href)) {
      try {
        const u = new URL(href);
        if (u.origin === location.origin && u.pathname === '/editor') {
          const lang = u.searchParams.get('lang');
          const path = u.searchParams.get('path');
          if (lang && path && langs.includes(lang)) {
            if (dirty && !confirm('有未保存的改动，打开链接将丢弃。确定继续？')) return true;
            void loadFile(lang, path);
            return true;
          }
        }
      } catch {
        // fall through to new tab
      }
      return false; // external http(s) → new tab
    }

    // 2. Vault path resolution
    let resolvedPath: string;
    if (href.startsWith('/')) {
      resolvedPath = href.slice(1); // from vault root
    } else {
      const dir = currentPath.includes('/') ? currentPath.slice(0, currentPath.lastIndexOf('/') + 1) : '';
      resolvedPath = dir + href;
    }

    const parts = resolvedPath.split('/');
    const result: string[] = [];
    for (const part of parts) {
      if (part === '.' || part === '') continue;
      if (part === '..') {
        if (result.length > 0) result.pop();
        continue;
      }
      result.push(part);
    }
    resolvedPath = result.join('/');

    if (!resolvedPath.includes('.')) {
      resolvedPath += '.md';
    }

    if (!resolvedPath) return false;

    if (dirty && !confirm('有未保存的改动，打开链接将丢弃。确定继续？')) return true;

    void loadFile(selectedLang, resolvedPath);
    return true;
  }, [langs, dirty, loadFile, selectedLang, currentPath]);

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
      <header className="flex items-center gap-2 px-3 py-2 border-b border-border bg-background shrink-0">
        <div className="flex items-center gap-1 shrink-0">
          <button
            className="md:hidden inline-flex items-center justify-center size-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-all outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
            onClick={() => {
              if (!leftOpen && !isDesktop) setChatOpen(false);
              setLeftOpen(v => !v);
            }}
          >
            <Menu className="size-4" />
          </button>
          {langs.length > 0 && (
            <select
              className="h-8 rounded-lg border border-border bg-background px-2 text-sm text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              value={selectedLang}
              onChange={e => handleLangChange(e.target.value)}
            >
              {langs.map(l => <option key={l} value={l}>{l}</option>)}
            </select>
          )}
        </div>

        <div className="flex-1 text-center min-w-0">
          <span className="text-sm font-semibold text-foreground">
            <span className="md:hidden">🐹</span>
            <span className="hidden md:inline">🐹 小记笔记编辑器</span>
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            className={'inline-flex items-center gap-1 h-8 rounded-lg px-3 text-sm font-medium transition-all outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 ' + (chatOpen ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
            onClick={() => {
              if (!chatMounted) setChatMounted(true);
              if (!chatOpen && !isDesktop) setLeftOpen(false);
              setChatOpen(v => !v);
            }}
          >
            <MessageSquare className="size-4" />
            <span className="hidden md:inline">呼叫小记</span>
          </button>

          <button
            className="inline-flex items-center gap-1 h-8 rounded-lg px-3 text-sm font-medium transition-all outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 text-muted-foreground hover:text-foreground"
            onClick={() => { window.location.href = '/'; }}
          >
            <ExternalLink className="size-4" />
            <span className="hidden md:inline">转到小记</span>
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
          className={
            isDesktop
              ? 'flex flex-col shrink-0 border-r border-border bg-background'
              : 'fixed inset-y-0 left-0 z-40 w-[85vw] max-w-sm flex flex-col overflow-hidden border-r border-border bg-background transition-transform ' + (leftOpen ? 'translate-x-0' : '-translate-x-full')
          }
          style={isDesktop ? { width: `${leftPct}%` } : undefined}
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
              <span className="hidden md:inline">Files</span>
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
              <span className="hidden md:inline">Search</span>
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
          className="w-1 shrink-0 cursor-col-resize hover:bg-ring/30 active:bg-ring/40 transition-colors hidden md:block"
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
              <div className="flex items-center gap-2 px-4 py-1 border-b border-border shrink-0 bg-muted/30">
                <span className="flex-1 truncate text-xs text-muted-foreground">{currentPath}</span>
                <div className="flex items-center gap-1 rounded-lg border border-border bg-background p-0.5">
                  <button
                    className={'flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-all outline-none focus-visible:ring-3 focus-visible:ring-ring/50 ' + (mode === 'source' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
                    onClick={() => {
                      setMode('source');
                      localStorage.setItem('vault-editor:mode', 'source');
                    }}
                  >
                    <Code className="size-3.5" />
                    <span className="hidden md:inline">源码</span>
                  </button>
                  <button
                    className={'flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-all outline-none focus-visible:ring-3 focus-visible:ring-ring/50 ' + (mode === 'wysiwyg' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
                    onClick={() => {
                      setMode('wysiwyg');
                      localStorage.setItem('vault-editor:mode', 'wysiwyg');
                    }}
                  >
                    <Eye className="size-3.5" />
                    <span className="hidden md:inline">直观</span>
                  </button>
                </div>
                <button
                  className="inline-flex items-center gap-1 h-7 rounded-lg px-3 text-xs font-medium transition-all outline-none disabled:opacity-40 disabled:pointer-events-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50
                    enabled:hover:bg-primary/80
                    enabled:active:translate-y-px
                    enabled:bg-primary enabled:text-primary-foreground"
                  disabled={!dirty || saving}
                  onClick={handleSave}
                >
                  <Save className="size-3.5" />
                  <span className="hidden md:inline">{saving ? '保存中…' : '保存'}</span>
                </button>
              </div>
              <div className="flex-1 overflow-auto">
                <MilkdownEditor
                  key={`${mode}:${currentPath || ''}`}
                  content={mode === 'wysiwyg' ? body : content}
                  onChange={mode === 'wysiwyg' ? (v) => setContent(fm + v) : setContent}
                  mode={mode}
                  onLinkClick={handleEditorLinkClick}
                />
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
              {loading ? '加载中…' : '选择一个文件开始编辑'}
            </div>
          )}
        </main>

        {/* Right sidebar: resize handle */}
        {chatMounted && (
          <div
            className={'w-1 shrink-0 cursor-col-resize hover:bg-ring/30 active:bg-ring/40 transition-colors hidden md:block ' + (chatOpen ? '' : 'hidden')}
            onPointerDown={e => {
              const container = bodyRef.current;
              if (!container) return;
              const rect = container.getBoundingClientRect();
              const handlePointerMove = (ev: PointerEvent) => {
                const pct = Math.min(50, Math.max(20, ((rect.right - ev.clientX) / rect.width) * 100));
                setChatPct(pct);
              };
              const handlePointerUp = (ev: PointerEvent) => {
                const pct = Math.min(50, Math.max(20, ((rect.right - ev.clientX) / rect.width) * 100));
                setChatPct(pct);
                localStorage.setItem('vault-editor:chatPanePct', String(pct));
                document.removeEventListener('pointermove', handlePointerMove);
                document.removeEventListener('pointerup', handlePointerUp);
              };
              document.addEventListener('pointermove', handlePointerMove);
              document.addEventListener('pointerup', handlePointerUp);
            }}
          />
        )}

        {/* Right sidebar: chatbot */}
        {chatMounted && (
          <aside
            className={isDesktop
              ? 'flex flex-col shrink-0 bg-background overflow-hidden ' + (chatOpen ? '' : 'hidden')
              : 'fixed inset-y-0 right-0 z-40 w-[85vw] max-w-sm flex flex-col overflow-hidden border-l border-border bg-background transition-transform ' + (chatOpen ? 'translate-x-0' : 'translate-x-full')}
            style={isDesktop ? { width: `${chatPct}%` } : undefined}
          >
            <ChatWindow embedded linkListener={handleChatLinkClick} />
          </aside>
        )}

        {!isDesktop && (leftOpen || chatOpen) && (
          <div
            className="fixed inset-0 z-30 bg-black/40"
            onClick={() => { setLeftOpen(false); setChatOpen(false); }}
          />
        )}
      </div>
    </div>
  );
}
