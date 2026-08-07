import { describe, it, expect } from 'vitest';
import { normalizeUrl, DEFAULT_API_BASE_URL, buildBearerHeader, UrlFormatError } from './config';

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

  it('throws UrlFormatError for missing scheme', () => {
    expect(() => normalizeUrl('localhost:8000')).toThrowError(UrlFormatError);
    expect(() => normalizeUrl('example.com')).toThrowError(UrlFormatError);
  });

  it('accepts http and https', () => {
    expect(normalizeUrl('http://example.com')).toBe('http://example.com');
    expect(normalizeUrl('https://example.com')).toBe('https://example.com');
  });

  it('trims whitespace', () => {
    expect(normalizeUrl('  http://example.com  ')).toBe('http://example.com');
  });
});

describe('buildBearerHeader', () => {
  it('returns null when token is empty', () => {
    expect(buildBearerHeader('')).toBeNull();
  });

  it('returns null when token is only whitespace', () => {
    expect(buildBearerHeader('  ')).toBeNull();
  });

  it('builds valid Bearer header with token', () => {
    expect(buildBearerHeader('elpat_abc123')).toBe('Bearer elpat_abc123');
  });

  it('trims whitespace around token', () => {
    expect(buildBearerHeader('  elpat_abc123  ')).toBe('Bearer elpat_abc123');
  });

  it('handles access_token (JWT) format', () => {
    const jwt = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.x';
    expect(buildBearerHeader(jwt)).toBe('Bearer ' + jwt);
  });
});
