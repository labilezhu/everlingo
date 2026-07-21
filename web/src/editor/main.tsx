import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import EditorApp from './components/EditorApp';
import '../index.css';
import '@milkdown/kit/prose/view/style/prosemirror.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <EditorApp />
  </StrictMode>,
);
