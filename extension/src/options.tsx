import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import OptionsForm from './components/OptionsForm';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <OptionsForm />
  </StrictMode>,
);
