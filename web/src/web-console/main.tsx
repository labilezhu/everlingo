import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import ConsolePage from './ConsolePage';
import ErrorBoundary from '@/components/ErrorBoundary';
import { bootstrapI18n, bootstrapLoadingText, setPageTitle } from '@/i18n/bootstrap';
import '../index.css';

async function boot() {
  const root = createRoot(document.getElementById('root')!);
  root.render(<div className="flex items-center justify-center h-screen text-muted-foreground">{bootstrapLoadingText()}</div>);
  await bootstrapI18n();
  setPageTitle('web-console', 'page_title');
  root.render(
    <StrictMode>
      <ErrorBoundary>
        <ConsolePage />
      </ErrorBoundary>
    </StrictMode>,
  );
}

void boot();