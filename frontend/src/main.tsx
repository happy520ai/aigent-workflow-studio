// frontend/src/main.tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import Workbench from './Workbench';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Workbench />
  </React.StrictMode>
);
