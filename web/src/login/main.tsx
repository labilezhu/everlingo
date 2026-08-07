import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import LoginPage from './LoginPage';
import ErrorBoundary from '@/components/ErrorBoundary';
import { bootstrapI18n, bootstrapLoadingText, setPageTitle } from '@/i18n/bootstrap';
import '../index.css';

async function boot() {
  const root = createRoot(document.getElementById('root')!);
  root.render(<div className="flex items-center justify-center h-screen text-muted-foreground">{bootstrapLoadingText()}</div>);
  await bootstrapI18n();
  setPageTitle('login', 'page_title');
  root.render(
    <StrictMode>
      <ErrorBoundary>
        <LoginPage />
      </ErrorBoundary>
    </StrictMode>,
  );
}

void boot();