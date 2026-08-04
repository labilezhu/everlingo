import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import ConsolePage from './ConsolePage';
import ErrorBoundary from '@/components/ErrorBoundary';
import '../index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <ConsolePage />
    </ErrorBoundary>
  </StrictMode>,
);
