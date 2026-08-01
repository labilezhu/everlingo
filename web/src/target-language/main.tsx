import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import TargetLanguagePage from './TargetLanguagePage';
import '../index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <TargetLanguagePage />
  </StrictMode>,
);
