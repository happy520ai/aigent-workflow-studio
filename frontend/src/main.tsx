// frontend/src/main.tsx —— T42：顶层 ErrorBoundary + 全局 ToastHost 包裹
import React from 'react';
import ReactDOM from 'react-dom/client';
import Workbench from './Workbench';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ToastHost } from './components/Toast';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <Workbench />
      <ToastHost />
    </ErrorBoundary>
  </React.StrictMode>
);
