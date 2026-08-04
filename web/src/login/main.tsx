import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import LoginPage from './LoginPage';
import ErrorBoundary from '@/components/ErrorBoundary';
import '../index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <LoginPage />
    </ErrorBoundary>
  </StrictMode>,
);
