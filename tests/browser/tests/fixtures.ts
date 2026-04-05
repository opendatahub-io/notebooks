export type ConfigFixtures = {
  connectCDP: false | number;
  codeServerSource: CodeServerSource;
};

export type CodeServerSource = EntityUnion<{
  url: string;
  image: string;
}>;

export const CodeServerSource = {
  url: (url: string): CodeServerSource => ({ kind: 'url', url }),
  image: (image: string): CodeServerSource => ({ kind: 'image', image }),
};

type EntityUnion<T extends Record<string, unknown>> =
  'kind' extends keyof T
    ? ['Error: "kind" is reserved as the discriminant and cannot be used as a variant key']
    : { [K in keyof T]: { kind: K } & Record<K, T[K]> }[keyof T];

/**
 * Asserts that a code path is unreachable.
 * Used for exhaustive type checking in switch/if-else blocks.
 */
export function assertUnreachable(x: never): never {
  throw new Error(`Unreachable code reached with value: ${JSON.stringify(x)}`);
}
