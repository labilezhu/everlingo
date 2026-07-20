import { describe, it, expect } from 'vitest';
import { normalizeUrl, DEFAULT_API_BASE_URL } from './config';

describe('normalizeUrl', () => {
  it('returns default for empty string', () => {
    expect(normalizeUrl('')).toBe(DEFAULT_API_BASE_URL);
    expect(normalizeUrl('  ')).toBe(DEFAULT_API_BASE_URL);
  });

  it('strips trailing slashes', () => {
    expect(normalizeUrl('http://example.com/')).toBe('http://example.com');
    expect(normalizeUrl('http://example.com///')).toBe('http://example.com');
    expect(normalizeUrl('http://localhost:8000/')).toBe('http://localhost:8000');
  });

  it('throws for missing scheme', () => {
    expect(() => normalizeUrl('localhost:8000')).toThrow();
    expect(() => normalizeUrl('example.com')).toThrow();
  });

  it('accepts http and https', () => {
    expect(normalizeUrl('http://example.com')).toBe('http://example.com');
    expect(normalizeUrl('https://example.com')).toBe('https://example.com');
  });

  it('trims whitespace', () => {
    expect(normalizeUrl('  http://example.com  ')).toBe('http://example.com');
  });
});
