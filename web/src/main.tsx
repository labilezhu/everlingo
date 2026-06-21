import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import ChatBot from './ChatBot';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ChatBot />
  </StrictMode>,
);
