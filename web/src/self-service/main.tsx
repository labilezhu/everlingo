import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import SelfServicePage from './SelfServicePage';
import ErrorBoundary from '@/components/ErrorBoundary';
import '../index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <SelfServicePage />
    </ErrorBoundary>
  </StrictMode>,
);
