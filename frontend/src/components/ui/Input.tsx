import React from 'react';
import { Search, X } from 'lucide-react';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      error,
      helperText,
      leftIcon,
      rightIcon,
      className = '',
      id,
      disabled,
      ...props
    },
    ref
  ) => {
    const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-xs font-medium text-slate-300 mb-1.5"
          >
            {label}
          </label>
        )}
        <div className="relative flex items-center">
          {leftIcon && (
            <div className="absolute left-3 text-slate-400 pointer-events-none flex items-center">
              {leftIcon}
            </div>
          )}
          <input
            id={inputId}
            ref={ref}
            disabled={disabled}
            className={`w-full bg-[#0E1524] text-slate-100 text-sm rounded-lg border transition-all duration-150 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-[#7565F5]/40 disabled:opacity-50 disabled:cursor-not-allowed ${
              leftIcon ? 'pl-9' : 'pl-3.5'
            } ${rightIcon ? 'pr-9' : 'pr-3.5'} py-2 ${
              error
                ? 'border-red-500/60 focus:border-red-500 focus:ring-red-500/20'
                : 'border-white/[0.08] hover:border-white/[0.15] focus:border-[#7565F5]'
            } ${className}`}
            {...props}
          />
          {rightIcon && (
            <div className="absolute right-3 flex items-center">{rightIcon}</div>
          )}
        </div>
        {error ? (
          <p className="text-xs text-rose-400 mt-1.5">{error}</p>
        ) : helperText ? (
          <p className="text-xs text-slate-400 mt-1.5">{helperText}</p>
        ) : null}
      </div>
    );
  }
);

Input.displayName = 'Input';

interface SearchInputProps extends Omit<InputProps, 'leftIcon' | 'rightIcon'> {
  onClear?: () => void;
}

export function SearchInput({ value, onClear, onChange, ...props }: SearchInputProps) {
  return (
    <Input
      leftIcon={<Search className="w-4 h-4 text-slate-400" />}
      rightIcon={
        value && onClear ? (
          <button
            type="button"
            onClick={onClear}
            className="text-slate-400 hover:text-slate-200 transition-colors p-0.5"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        ) : undefined
      }
      value={value}
      onChange={onChange}
      {...props}
    />
  );
}

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
}

export function Select({ label, error, children, className = '', id, ...props }: SelectProps) {
  const selectId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);

  return (
    <div className="w-full">
      {label && (
        <label htmlFor={selectId} className="block text-xs font-medium text-slate-300 mb-1.5">
          {label}
        </label>
      )}
      <select
        id={selectId}
        className={`w-full bg-[#0E1524] text-slate-100 text-sm rounded-lg border border-white/[0.08] hover:border-white/[0.15] focus:border-[#7565F5] focus:ring-2 focus:ring-[#7565F5]/40 focus:outline-none px-3 py-2 transition-all ${
          error ? 'border-red-500/60' : ''
        } ${className}`}
        {...props}
      >
        {children}
      </select>
      {error && <p className="text-xs text-rose-400 mt-1.5">{error}</p>}
    </div>
  );
}
