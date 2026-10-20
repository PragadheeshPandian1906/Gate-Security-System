import React from 'react';
import { AlertCircle, CheckCircle2, AlertTriangle, Info, X } from 'lucide-react';

interface AlertBannerProps {
  variant?: 'error' | 'success' | 'warning' | 'info';
  title?: string;
  children: React.ReactNode;
  onClose?: () => void;
  className?: string;
}

export function AlertBanner({
  variant = 'info',
  title,
  children,
  onClose,
  className = '',
}: AlertBannerProps) {
  const configs = {
    error: {
      bg: 'bg-rose-500/10',
      border: 'border-rose-500/30',
      text: 'text-rose-200',
      iconText: 'text-rose-400',
      icon: <AlertCircle className="w-4 h-4 shrink-0" />,
    },
    success: {
      bg: 'bg-emerald-500/10',
      border: 'border-emerald-500/30',
      text: 'text-emerald-200',
      iconText: 'text-emerald-400',
      icon: <CheckCircle2 className="w-4 h-4 shrink-0" />,
    },
    warning: {
      bg: 'bg-amber-500/10',
      border: 'border-amber-500/30',
      text: 'text-amber-200',
      iconText: 'text-amber-400',
      icon: <AlertTriangle className="w-4 h-4 shrink-0" />,
    },
    info: {
      bg: 'bg-sky-500/10',
      border: 'border-sky-500/30',
      text: 'text-sky-200',
      iconText: 'text-sky-400',
      icon: <Info className="w-4 h-4 shrink-0" />,
    },
  };

  const conf = configs[variant];

  return (
    <div
      role="alert"
      className={`flex items-start gap-3 p-3.5 rounded-lg border text-xs sm:text-sm ${conf.bg} ${conf.border} ${conf.text} ${className}`}
    >
      <div className={`mt-0.5 ${conf.iconText}`}>{conf.icon}</div>
      <div className="flex-1">
        {title && <h4 className="font-semibold mb-0.5 text-slate-100">{title}</h4>}
        <div className="leading-relaxed">{children}</div>
      </div>
      {onClose && (
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-200 p-0.5 rounded transition-colors -mr-1"
          aria-label="Dismiss alert"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
