import { describe, expect, it } from 'vitest';
import { sha256Bytes, sha256Hex } from './sha256';

const hexEncode = (buf: Uint8Array) => Array.from(buf).map(b => b.toString(16).padStart(2, '0')).join('');

async function nativeSha256(buf: Uint8Array): Promise<string> {
  const copy = new Uint8Array(buf.length);
  copy.set(buf);
  const digest = await crypto.subtle.digest('SHA-256', copy);
  return hexEncode(new Uint8Array(digest));
}

describe('sha256Bytes', () => {
  it('matches NIST FIPS 180-2 test vectors', () => {
    const abc = new TextEncoder().encode('abc');
    expect(sha256Bytes(abc)).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
    const empty = new Uint8Array(0);
    expect(sha256Bytes(empty)).toBe('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
    const long = new TextEncoder().encode('abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq');
    expect(sha256Bytes(long)).toBe('248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1');
  });

  it('matches native crypto.subtle across varied lengths', async () => {
    for (const len of [63, 64, 65, 127, 128, 129, 1024, 4096]) {
      const buf = new Uint8Array(len);
      for (let i = 0; i < len; i++) buf[i] = (i * 7 + len) & 0xff;
      expect(sha256Bytes(buf)).toBe(await nativeSha256(buf));
    }
  });
});

describe('sha256Hex', () => {
  it('delegates to crypto.subtle when available', async () => {
    const buf = new TextEncoder().encode('everlingo');
    expect(await sha256Hex(buf.buffer)).toBe(await nativeSha256(buf));
  });
});