import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import InterfaceLanguagePage from './InterfaceLanguagePage';
import ErrorBoundary from '@/components/ErrorBoundary';
import '../index.css';

async function boot() {
  const { bootstrapI18n } = await import('@/i18n/bootstrap');
  await bootstrapI18n();
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ErrorBoundary>
        <InterfaceLanguagePage />
      </ErrorBoundary>
    </StrictMode>,
  );
}

void boot();