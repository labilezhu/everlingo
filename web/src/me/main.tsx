import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import MePage from './MePage';
import ErrorBoundary from '@/components/ErrorBoundary';
import '../index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <MePage />
    </ErrorBoundary>
  </StrictMode>,
);
