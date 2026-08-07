import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import InterfaceLanguagePage from './InterfaceLanguagePage';
import ErrorBoundary from '@/components/ErrorBoundary';
import { bootstrapI18n, setPageTitle } from '@/i18n/bootstrap';
import '../index.css';

async function boot() {
  await bootstrapI18n();
  setPageTitle('onboarding', 'interface_page_title');
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ErrorBoundary>
        <InterfaceLanguagePage />
      </ErrorBoundary>
    </StrictMode>,
  );
}

void boot();