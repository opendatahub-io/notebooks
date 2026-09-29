/** A callable method as exposed by a page-object chain. */
type ChainMethod = (...args: never[]) => unknown;

/**
 * The methods of `T`, with asynchronous results represented by another chain.
 * `then` is deliberately omitted from the mapped members so it remains the
 * PromiseLike implementation supplied by the runtime proxy.
 */
export type ChainMethods<T> = {
  [Key in keyof T as Key extends 'then'
    ? never
    : T[Key] extends ChainMethod
      ? Key
      : never]: T[Key] extends (...args: infer Arguments) => infer Result
    ? (...args: Arguments) => Chain<Awaited<Result>>
    : never;
};

/** A typed, awaitable view of a page object that forwards method calls in order. */
export type Chain<T> = PromiseLike<T> & ChainMethods<T>;

/** Alias for callers that want to name the awaitable result explicitly. */
export type Chainable<T> = Chain<T>;

/**
 * Wrap an asynchronous value so methods can be called before awaiting it.
 * Each method waits for the preceding value and invokes the method with the
 * resolved object as its receiver, preserving page-object `this` semantics.
 */
export function chain<T>(value: PromiseLike<T>): Chain<T> {
  const promise = Promise.resolve(value);

  return new Proxy({} as Chain<T>, {
    get(_target, property: string | symbol): unknown {
      if (property === 'then') {
        return promise.then.bind(promise);
      }

      return (...args: unknown[]) => chain(
        promise.then((resolved) => {
          const member: unknown = Reflect.get(resolved as object, property) as unknown;
          if (typeof member !== 'function') {
            throw new TypeError(`Cannot call ${String(property)} on the chained value`);
          }
          return Reflect.apply(member as (...callArgs: unknown[]) => unknown, resolved, args);
        }),
      );
    },
  });
}

/**
 * Adapt an async factory, retaining its parameter and result types while
 * returning a chainable result. This is useful for async page-object entry
 * points such as `JupyterLab.open`.
 */
export function chainable<Arguments extends readonly unknown[], Result>(
  factory: (...args: Arguments) => PromiseLike<Result>,
): (...args: Arguments) => Chain<Awaited<Result>> {
  return (...args) => chain(Promise.resolve(factory(...args)));
}
