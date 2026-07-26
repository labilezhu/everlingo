import { describe, it, expect } from 'vitest';
import { normalizeUrl, DEFAULT_API_BASE_URL, buildBasicAuthHeader } from './config';

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

describe('buildBasicAuthHeader', () => {
  it('returns null when username is empty', () => {
    expect(buildBasicAuthHeader('', 'pass')).toBeNull();
    expect(buildBasicAuthHeader('', '')).toBeNull();
  });

  it('returns null when username is only whitespace', () => {
    expect(buildBasicAuthHeader('  ', 'pass')).toBeNull();
  });

  it('builds valid Basic header with username and password', () => {
    const result = buildBasicAuthHeader('alice', 'secret');
    expect(result).toBe('Basic ' + btoa('alice:secret'));
  });

  it('handles empty password', () => {
    const result = buildBasicAuthHeader('admin', '');
    expect(result).toBe('Basic ' + btoa('admin:'));
  });

  it('handles password containing colon', () => {
    const result = buildBasicAuthHeader('user', 'pass:word');
    expect(result).toBe('Basic ' + btoa('user:pass:word'));
  });

  it('handles Unicode characters in username and password', () => {
    const result = buildBasicAuthHeader('用户', '密码');
    expect(result).toBe('Basic ' + btoa(unescape(encodeURIComponent('用户:密码'))));
  });

  it('handles special characters', () => {
    const result = buildBasicAuthHeader('user@host', 'p@$$!');
    expect(result).toBe('Basic ' + btoa('user@host:p@$$!'));
  });
});
