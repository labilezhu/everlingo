import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import TargetLanguagePage from './TargetLanguagePage';
import ErrorBoundary from '@/components/ErrorBoundary';
import '../index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <TargetLanguagePage />
    </ErrorBoundary>
  </StrictMode>,
);
