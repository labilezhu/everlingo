import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import PatPage from './PatPage';
import '../index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <PatPage />
  </StrictMode>,
);
