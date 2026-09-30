import React from "react";
export function Otter({ small = false }: { small?: boolean }) {
  return (
    <svg
      width={small ? 34 : 58}
      height={small ? 34 : 58}
      viewBox="0 0 64 64"
      fill="none"
      aria-label="QueryOtter mascot"
    >
      <rect width="64" height="64" rx="18" fill="#d9eee7" />
      <ellipse cx="32" cy="42" rx="19" ry="16" fill="#9b7558" />
      <circle cx="17" cy="21" r="8" fill="#9b7558" />
      <circle cx="47" cy="21" r="8" fill="#9b7558" />
      <ellipse cx="32" cy="31" rx="22" ry="19" fill="#b9916c" />
      <ellipse cx="32" cy="37" rx="15" ry="10" fill="#ead5bb" />
      <circle cx="24" cy="27" r="2.5" fill="#20342c" />
      <circle cx="40" cy="27" r="2.5" fill="#20342c" />
      <path d="M28 33Q32 30 36 33L32 37Z" fill="#20342c" />
      <path
        d="M25 39q7 7 14 0M15 34l8 2m-8 4 8-1m26-5-8 2m8 4-8-1"
        stroke="#614a37"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="m30 48-7 6m11-6 7 6"
        stroke="#7b583f"
        strokeWidth="5"
        strokeLinecap="round"
      />
    </svg>
  );
}
