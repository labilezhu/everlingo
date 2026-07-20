import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import ChatWindow from './components/ChatWindow';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ChatWindow />
  </StrictMode>,
);
