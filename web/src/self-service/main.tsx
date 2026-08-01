import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import SelfServicePage from './SelfServicePage';
import '../index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <SelfServicePage />
  </StrictMode>,
);
