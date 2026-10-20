import React from 'react';

interface MetricCardProps {
  title: string;
  value: string | number;
  icon: React.ReactNode;
  subtitle?: string;
  badge?: React.ReactNode;
  accentColor?: 'violet' | 'sky' | 'emerald' | 'amber' | 'rose';
  className?: string;
}

export function MetricCard({
  title,
  value,
  icon,
  subtitle,
  badge,
  accentColor = 'violet',
  className = '',
}: MetricCardProps) {
  const iconTints = {
    violet: 'bg-[#7565F5]/10 text-[#9B8DFC] border-[#7565F5]/20',
    sky: 'bg-sky-500/10 text-sky-400 border-sky-500/20',
    emerald: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    amber: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    rose: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
  };

  return (
    <div
      className={`bg-[#151C2C] border border-white/[0.06] hover:border-white/[0.12] transition-colors rounded-xl p-4 sm:p-5 flex flex-col justify-between shadow-lg shadow-black/20 ${className}`}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
          {title}
        </span>
        <div
          className={`w-9 h-9 rounded-lg border flex items-center justify-center shrink-0 ${iconTints[accentColor]}`}
        >
          {icon}
        </div>
      </div>

      <div className="flex items-baseline justify-between gap-2 mt-auto">
        <span className="text-2xl sm:text-3xl font-bold text-slate-100 tracking-tight font-mono">
          {value}
        </span>
        {badge}
      </div>

      {subtitle && (
        <p className="text-xs text-slate-400 mt-2 truncate font-medium">
          {subtitle}
        </p>
      )}
    </div>
  );
}
