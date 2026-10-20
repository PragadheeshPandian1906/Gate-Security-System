import React from 'react';
import { Loader2, AlertCircle, Inbox } from 'lucide-react';
import { Button } from './Button';

interface LoadingStateProps {
  message?: string;
  className?: string;
}

export function LoadingState({ message = 'Loading...', className = '' }: LoadingStateProps) {
  return (
    <div className={`flex flex-col items-center justify-center p-8 sm:p-12 text-center ${className}`}>
      <Loader2 className="w-7 h-7 text-[#7565F5] animate-spin mb-3" />
      <p className="text-xs sm:text-sm text-slate-400 font-medium">{message}</p>
    </div>
  );
}

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export function EmptyState({
  icon = <Inbox className="w-8 h-8 text-slate-500" />,
  title,
  description,
  action,
  className = '',
}: EmptyStateProps) {
  return (
    <div className={`flex flex-col items-center justify-center p-8 sm:p-12 text-center ${className}`}>
      <div className="w-12 h-12 rounded-xl bg-white/[0.04] border border-white/[0.06] flex items-center justify-center mb-3.5">
        {icon}
      </div>
      <h4 className="text-sm font-semibold text-slate-200 mb-1">{title}</h4>
      {description && <p className="text-xs text-slate-400 max-w-sm mb-4 leading-relaxed">{description}</p>}
      {action && (
        <Button variant="secondary" size="sm" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  );
}

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
  className = '',
}: ErrorStateProps) {
  return (
    <div className={`flex flex-col items-center justify-center p-8 text-center ${className}`}>
      <div className="w-11 h-11 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 flex items-center justify-center mb-3">
        <AlertCircle className="w-6 h-6" />
      </div>
      <h4 className="text-sm font-semibold text-slate-200 mb-1">{title}</h4>
      <p className="text-xs text-rose-300/90 max-w-md mb-4">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try Again
        </Button>
      )}
    </div>
  );
}

interface UserAvatarProps {
  name: string;
  role?: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export function UserAvatar({ name, role, size = 'md', className = '' }: UserAvatarProps) {
  const sizeClasses = {
    sm: 'w-7 h-7 text-xs',
    md: 'w-8 h-8 text-xs',
    lg: 'w-10 h-10 text-sm',
  };

  const initial = name ? name[0].toUpperCase() : 'U';
  const isSecurity = role === 'SECURITY';

  return (
    <div
      className={`rounded-lg flex items-center justify-center font-bold text-white shrink-0 shadow-inner select-none ${
        isSecurity
          ? 'bg-gradient-to-tr from-sky-600 to-cyan-500 border border-sky-400/30'
          : 'bg-gradient-to-tr from-[#7565F5] to-indigo-500 border border-indigo-400/30'
      } ${sizeClasses[size]} ${className}`}
    >
      {initial}
    </div>
  );
}
