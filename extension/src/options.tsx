import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import OptionsForm from './components/OptionsForm';
import { bootstrapI18n } from './i18n/bootstrap';
import './index.css';

bootstrapI18n().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <OptionsForm />
    </StrictMode>,
  );
});
