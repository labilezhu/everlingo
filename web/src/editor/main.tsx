import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import EditorApp from './components/EditorApp';
import '../index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <EditorApp />
  </StrictMode>,
);
