import { describe, it, expect } from 'vitest';
import { buildEnvelope } from './envelope';

describe('buildEnvelope', () => {
  const snapshot = {
    selection: 'bank',
    context: 'I sat on the bank of the river.',
    url: 'https://example.com/article',
    title: 'Example Article',
    deviceId: 'test-device-id',
  };

  it('builds a valid translate envelope with selection and context', () => {
    const env = buildEnvelope('translate', '', snapshot);
    expect(env.schema_version).toBe(1);
    expect(env.task).toBe('translate');
    expect(env.chat.message).toBe('');
    expect(env.selection.text).toBe('bank');
    expect(env.context.text).toBe('I sat on the bank of the river.');
    expect(env.context.kind).toBe('paragraph');
    expect(env.source.kind).toBe('web');
    expect(env.source).toHaveProperty('surface', 'sidecar');
    expect(env.source).toHaveProperty('url', 'https://example.com/article');
    expect(env.device?.platform).toBe('chrome_ext');
    expect(env.device?.device_id).toBe('test-device-id');
  });

  it('sets context kind to plain when context text is empty', () => {
    const env = buildEnvelope('translate', '', { ...snapshot, context: '' });
    expect(env.context.kind).toBe('plain');
    expect(env.context.text).toBe('');
  });

  it('builds a look_up envelope', () => {
    const env = buildEnvelope('look_up', '', snapshot);
    expect(env.task).toBe('look_up');
  });

  it('includes chat message when provided', () => {
    const env = buildEnvelope('translate', '解释一下这个词', snapshot);
    expect(env.chat.message).toBe('解释一下这个词');
  });

  it('handles empty selection gracefully', () => {
    const env = buildEnvelope('none', '', { ...snapshot, selection: '' });
    expect(env.selection.text).toBe('');
  });

  it('does not set device_id when not provided', () => {
    const env = buildEnvelope('translate', 'hello', { ...snapshot, deviceId: undefined });
    expect(env.device?.device_id).toBeUndefined();
  });
});
