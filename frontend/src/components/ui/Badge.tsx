import React from 'react';

export type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral' | 'primary';

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  size?: 'sm' | 'md';
  pulse?: boolean;
  className?: string;
  icon?: React.ReactNode;
}

export function StatusBadge({
  children,
  variant = 'neutral',
  size = 'md',
  pulse = false,
  className = '',
  icon,
}: BadgeProps) {
  const sizeStyles = {
    sm: 'text-[11px] px-2 py-0.5 gap-1',
    md: 'text-xs px-2.5 py-1 gap-1.5',
  };

  const variantStyles: Record<BadgeVariant, { bg: string; text: string; border: string; dot: string }> = {
    success: {
      bg: 'bg-emerald-500/10',
      text: 'text-emerald-400',
      border: 'border-emerald-500/25',
      dot: 'bg-emerald-400',
    },
    warning: {
      bg: 'bg-amber-500/10',
      text: 'text-amber-400',
      border: 'border-amber-500/25',
      dot: 'bg-amber-400',
    },
    error: {
      bg: 'bg-rose-500/10',
      text: 'text-rose-400',
      border: 'border-rose-500/25',
      dot: 'bg-rose-400',
    },
    info: {
      bg: 'bg-sky-500/10',
      text: 'text-sky-400',
      border: 'border-sky-500/25',
      dot: 'bg-sky-400',
    },
    primary: {
      bg: 'bg-[#7565F5]/10',
      text: 'text-[#9B8DFC]',
      border: 'border-[#7565F5]/30',
      dot: 'bg-[#7565F5]',
    },
    neutral: {
      bg: 'bg-slate-800/60',
      text: 'text-slate-300',
      border: 'border-slate-700/60',
      dot: 'bg-slate-400',
    },
  };

  const conf = variantStyles[variant];

  return (
    <span
      className={`inline-flex items-center font-medium rounded-full border ${conf.bg} ${conf.text} ${conf.border} ${sizeStyles[size]} ${className}`}
    >
      {pulse ? (
        <span className="relative flex h-2 w-2">
          <span
            className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${conf.dot}`}
          />
          <span className={`relative inline-flex rounded-full h-2 w-2 ${conf.dot}`} />
        </span>
      ) : icon ? (
        icon
      ) : null}
      <span>{children}</span>
    </span>
  );
}
