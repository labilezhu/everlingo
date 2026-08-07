import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import EditorApp from './components/EditorApp';
import ErrorBoundary from '@/components/ErrorBoundary';
import { bootstrapI18n, bootstrapLoadingText, setPageTitle } from '@/i18n/bootstrap';
import '../index.css';
import '@milkdown/kit/prose/view/style/prosemirror.css';

async function boot() {
  const root = createRoot(document.getElementById('root')!);
  root.render(<div className="flex items-center justify-center h-screen text-muted-foreground">{bootstrapLoadingText()}</div>);
  await bootstrapI18n();
  setPageTitle('editor', 'app_name');
  root.render(
    <StrictMode>
      <ErrorBoundary>
        <EditorApp />
      </ErrorBoundary>
    </StrictMode>,
  );
}

void boot();