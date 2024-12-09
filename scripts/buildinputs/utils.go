package main

// noErr panics if the argument (usually a result of a function call)
// returns a != nil error
func noErr(err error) {
	if err != nil {
		panic(err)
	}
}

// noErr2 is a 2-arity variant of noErr, that passes through the first
// value from the argument
func noErr2[T any](result T, err error) T {
	noErr(err)
	return result
}
