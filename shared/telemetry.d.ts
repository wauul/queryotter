export const operations: Set<string>;
export function sampleRate(value: unknown, fallback?: number): number;
export function releaseName(value: unknown): string | undefined;
export function environmentName(value: unknown): string;
export function routeName(value: string): string;
export function traceHeaders(
  headers: Headers | Record<string, string | undefined>,
): Record<string, string>;
export function sanitizeSpan<T>(span: T): T;
export function sanitizeEvent<T>(event: T, hint?: { attachments?: unknown }): T;
