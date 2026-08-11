"use client";

import { useId, useState, type ReactNode } from "react";
import { inputControlClassName } from "@/components/ui/form-styles";

type FormFieldProps = {
  label: string;
  helper?: string;
  labelAction?: ReactNode;
  type?: "text" | "email" | "password" | "number";
  autoComplete?: string;
  required?: boolean;
  minLength?: number;
  min?: number;
  step?: number;
  inputMode?: "decimal" | "numeric" | "text";
  value: string;
  onChange: (value: string) => void;
  id?: string;
};

function EyeIcon({ hidden }: { hidden: boolean }) {
  if (hidden) {
    return (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        className="h-4 w-4"
        aria-hidden
      >
        <path d="M3 3l18 18" />
        <path d="M10.58 10.58A2 2 0 0012 14a2 2 0 001.41-3.41" />
        <path d="M9.88 5.09A10.94 10.94 0 0112 5c5 0 9.27 3.11 11 7.5a11.8 11.8 0 01-2.08 3.17M6.12 6.12A11.76 11.76 0 003 12.5C4.73 16.39 9 19.5 14 19.5c1.02 0 2-.13 2.93-.37" />
      </svg>
    );
  }

  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      className="h-4 w-4"
      aria-hidden
    >
      <path d="M2 12.5C3.73 8.11 8 5 13 5s9.27 3.11 11 7.5c-1.73 4.39-6 7.5-11 7.5S3.73 16.89 2 12.5z" />
      <circle cx="13" cy="12.5" r="3" />
    </svg>
  );
}

export function FormField({
  label,
  helper,
  labelAction,
  type = "text",
  autoComplete,
  required,
  minLength,
  min,
  step,
  inputMode,
  value,
  onChange,
  id,
}: FormFieldProps) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const helperId = helper ? `${fieldId}-helper` : undefined;
  const isPassword = type === "password";
  const [visible, setVisible] = useState(false);
  const inputType = isPassword && visible ? "text" : type;

  return (
    <div className="block space-y-1.5">
      <div className="flex items-center justify-between gap-3">
        <label
          htmlFor={fieldId}
          className="text-sm font-medium text-zinc-700 dark:text-zinc-200"
        >
          {label}
        </label>
        {labelAction}
      </div>

      <div className="relative">
        <input
          id={fieldId}
          type={inputType}
          autoComplete={autoComplete}
          required={required}
          minLength={minLength}
          min={min}
          step={step}
          inputMode={inputMode}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-describedby={helperId}
          className={`${inputControlClassName} ${isPassword ? "pr-11" : ""}`}
        />

        {isPassword ? (
          <button
            type="button"
            onClick={() => setVisible((current) => !current)}
            className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-zinc-400 transition hover:text-zinc-700 dark:hover:text-zinc-200"
            aria-label={visible ? "Hide password" : "Show password"}
          >
            <EyeIcon hidden={visible} />
          </button>
        ) : null}
      </div>

      {helper ? (
        <p id={helperId} className="text-xs leading-5 text-zinc-500">
          {helper}
        </p>
      ) : null}
    </div>
  );
}
