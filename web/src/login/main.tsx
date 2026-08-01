import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import LoginPage from './LoginPage';
import '../index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LoginPage />
  </StrictMode>,
);
