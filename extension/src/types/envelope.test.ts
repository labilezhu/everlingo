import { describe, it, expect } from 'vitest';
import { buildEnvelope } from './envelope';

describe('buildEnvelope', () => {
  const snapshot = {
    text: 'bank',
    paragraph_text: 'I sat on the bank of the river.',
    deviceId: 'test-device-id',
  };

  it('builds a valid translate envelope with selected_text in resource_contexts', () => {
    const env = buildEnvelope('translate', '', snapshot);
    expect(env.schema_version).toBe(1);
    expect(env.task).toBe('translate');
    expect(env.chat.message).toBe('');
    expect(env.chat_context.resource_contexts).toHaveLength(1);
    const ctx = env.chat_context.resource_contexts[0];
    expect(ctx.kind).toBe('selected_text');
    if (ctx.kind === 'selected_text') {
      expect(ctx.text).toBe('bank');
      expect(ctx.paragraph_text).toBe('I sat on the bank of the river.');
    }
    expect(env.source.kind).toBe('chrome_ext');
    expect(env.source).toHaveProperty('surface', 'sidecar');
    expect(env.device?.platform).toBe('chrome_ext');
    expect(env.device?.device_id).toBe('test-device-id');
  });

  it('builds a look_up envelope', () => {
    const env = buildEnvelope('look_up', '', snapshot);
    expect(env.task).toBe('look_up');
  });

  it('includes chat message when provided', () => {
    const env = buildEnvelope('translate', '解释一下这个词', snapshot);
    expect(env.chat.message).toBe('解释一下这个词');
  });

  it('produces empty resource_contexts when no selection', () => {
    const env = buildEnvelope('none', '', { text: '', paragraph_text: '', deviceId: 'x' });
    expect(env.chat_context.resource_contexts).toEqual([]);
  });

  it('does not set device_id when not provided', () => {
    const env = buildEnvelope('translate', 'hello', { text: 'hello', paragraph_text: '', deviceId: undefined });
    expect(env.device?.device_id).toBeUndefined();
  });
});
