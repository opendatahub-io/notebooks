import { describe, expect, it } from 'vitest';
import { chain, chainable, type Chain } from '../tests/models/jupyterlab/chain';

class Counter {
  readonly details = { label: 'counter' };
  readonly optionalDetails: { label: string } | undefined = undefined;
  readonly nullableDetails: { label: string } | null = null;

  constructor(private value: number) {}

  add(amount: number): Promise<Counter> {
    this.value += amount;
    return Promise.resolve(this);
  }

  result(): Promise<number> {
    return Promise.resolve(this.value);
  }
}

describe('page-object chains', () => {
  it('sequences methods and preserves their receiver', async () => {
    const counter = chain(Promise.resolve(new Counter(1)))
      .add(2)
      .add(4);

    await expect(counter.result()).resolves.toBe(7);
    await expect(counter).resolves.toBeInstanceOf(Counter);
  });

  it('adapts an async entry point without losing its signature', async () => {
    const open = chainable((initial: number): Promise<Counter> => Promise.resolve(new Counter(initial)));
    const result: Chain<number> = open(5).add(3).result();

    await expect(result).resolves.toBe(8);
  });

  it('defers nested properties and preserves optional values', async () => {
    const counter = chain(Promise.resolve(new Counter(1)));

    await expect(counter.details.label).resolves.toBe('counter');
    await expect(counter.optionalDetails).resolves.toBeUndefined();
    await expect(counter.nullableDetails).resolves.toBeNull();
  });
});
