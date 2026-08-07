import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import ChatWindow from './components/ChatWindow';
import { bootstrapI18n } from './i18n/bootstrap';
import './index.css';

bootstrapI18n().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ChatWindow />
    </StrictMode>,
  );
});
