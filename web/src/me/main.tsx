import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import MePage from './MePage';
import '../index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MePage />
  </StrictMode>,
);
