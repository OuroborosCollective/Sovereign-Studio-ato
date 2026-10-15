import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  initialFocusRef?: React.RefObject<HTMLElement | null>;
}

export function Modal({ isOpen, onClose, title, children, initialFocusRef }: Props) {
  const titleId = React.useId();
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const lastFocusedElement = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!isOpen || typeof document === 'undefined') return;

    lastFocusedElement.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusableSelector = [
      'button:not([disabled])',
      '[href]',
      'input:not([disabled])',
      'select:not([disabled])',
      'textarea:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
    ].join(',');
    const focusables = () => dialogRef.current ? Array.from(dialogRef.current.querySelectorAll<HTMLElement>(focusableSelector)) : [];
    const focusFrame = window.requestAnimationFrame(() => {
      initialFocusRef?.current?.focus();
      if (document.activeElement === lastFocusedElement.current || !document.activeElement) focusables()[0]?.focus();
    });
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab') return;
      const items = focusables();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener('keydown', onKeyDown);
      lastFocusedElement.current?.focus();
      lastFocusedElement.current = null;
    };
  }, [initialFocusRef, isOpen]);

  return (
    <AnimatePresence mode="wait">
      {isOpen && (
        <motion.div
          key="modal-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.22, ease: 'easeOut' }}
          onClick={onClose}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md"
        >
          <motion.div
            key="modal-chassis"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            data-sovereign-modal="true"
            ref={dialogRef}
            onClick={(e) => e.stopPropagation()}
            initial={{ opacity: 0, scale: 0.94, y: 16, filter: 'brightness(1.25)' }}
            animate={{ opacity: 1, scale: 1, y: 0, filter: 'brightness(1)' }}
            exit={{ opacity: 0, scale: 0.93, y: -14, filter: 'brightness(0.65)', transition: { duration: 0.18, ease: [0.32, 0, 0.67, 0] } }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="theme-diamond-cut w-full max-w-lg rounded-lg border border-[var(--red-pulse)] flex flex-col overflow-hidden shadow-[0_0_35px_rgba(0,0,0,0.95),0_0_20px_rgba(255,30,56,0.18)] breathing-machine"
          >
            <div className="relative flex items-center justify-between p-3.5 border-b border-[rgba(255,30,56,0.25)] bg-[var(--carbon-deep)]">
              <div className="absolute top-0 left-0 right-0 h-[1.5px] bg-gradient-to-r from-transparent via-[var(--red-laser)] to-transparent" />
              <h2 id={titleId} className="font-mono text-xs font-bold tracking-wider text-white flex items-center gap-2 uppercase"><span className="w-1.5 h-1.5 rounded-full bg-[var(--red-laser)] animate-pulse" />{title}</h2>
              <motion.button type="button" whileHover={{ scale: 1.15, rotate: 90 }} whileTap={{ scale: 0.9 }} onClick={onClose} className="text-[var(--text-muted)] hover:text-white transition-colors cursor-pointer p-1 rounded" aria-label="Close"><X size={16} /></motion.button>
            </div>
            <div className="p-4 bg-[var(--carbon-surface)] max-h-[80vh] overflow-y-auto">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
