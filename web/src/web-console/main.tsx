import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import ConsolePage from './ConsolePage';
import '../index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConsolePage />
  </StrictMode>,
);
