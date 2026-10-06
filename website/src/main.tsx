import React from 'react';
import ReactDOM from 'react-dom/client';
import { MotionConfig } from 'motion/react';
import '@fontsource-variable/geist';
import '@fontsource/instrument-serif/latin-400.css';
import '@fontsource/instrument-serif/latin-400-italic.css';
import '@fontsource-variable/jetbrains-mono';
import App from './App';
import './styles.css';
import './readability.css';

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><MotionConfig reducedMotion="user"><App /></MotionConfig></React.StrictMode>);
