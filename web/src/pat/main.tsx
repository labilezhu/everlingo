import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import PatPage from './PatPage';
import ErrorBoundary from '@/components/ErrorBoundary';
import '../index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <PatPage />
    </ErrorBoundary>
  </StrictMode>,
);
