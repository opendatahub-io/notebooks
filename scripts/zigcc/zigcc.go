package main

import (
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"syscall"
)

const (
	zig          = "/mnt/zig"
	glibcVersion = "2.34"

	CC  = "clang"
	CXX = "clang++"
)

func getTarget(subcommand string, args []string) string {
	var arch string
	switch os.Getenv("ZIGCC_ARCH") {
	case "amd64":
		arch = "x86_64"
	case "arm64":
		arch = "aarch64"
	case "ppc64le":
		arch = "powerpc64le"
	case "s390x":
		arch = "s390x"
	default:
		fmt.Fprintf(os.Stderr, "zigcc.go: Error: unknown architecture: %s\n", os.Getenv("ZIGCC_ARCH"))
		os.Exit(1)
	}

	// target glibc 2.28 or newer (supports FORTIFY_SOURCE)
	//return arch + "-linux-gnu"
	// specify glibc version with . separator between gnu and the version, otherwise
	//  error: unable to parse target query 'x86_64-linux-gnu2.34': UnknownApplicationBinaryInterface
	//  error: unable to parse target query 'x86_64-linux-gnu+2.34': UnknownApplicationBinaryInterface
	//  error: unable to parse target query 'x86_64-unknown-linux-gnu.2.34': UnknownOperatingSystem
	//  error: unable to parse target query 'x86_64-linux-gnuabi2.34': UnknownApplicationBinaryInterface
	// but for some reason, I'm still having problems with npm in codeserver
	//  zig c++ -target s390x-linux-gnu.2.34 -o Release/obj.target/windows.node -shared -pthread -rdynamic -m64 -march=z196 -Wl,-soname=windows.node -Wl,--start-group -Wl,--end-group
	//  npm error zig: error: version '.2.34' in target triple 's390x-unknown-linux-gnu.2.34' is invalid
	// and in trustyai
	//  zig: warning: argument unused during compilation: '-c' [-Wunused-command-line-argument]
	//  zig cc -target powerpc64le-linux-gnu.2.34 --sysroot / -isystem /usr/include -L/usr/lib64 -isystem /usr/local/include -L/usr/local/lib64 -dumpversion
	//  zig: error: version '.2.34' in target triple 'powerpc64le-unknown-linux-gnu.2.34' is invalid
	//  ../Makefile.power:60: your compiler is too old to fully support POWER9, getting a newer version of gcc is recommended

	// "-nostdinc" "-nostdlib" and be done with it?
	return arch + "-linux-gnu"

	if subcommand == CXX {
		// https://github.com/ziglang/zig/issues/25994#issuecomment-3562961055
		return arch + "-linux-gnu"
	}
	if slices.Contains(args, "-dumpversion") {
		return arch + "-linux-gnu"
	}
	if slices.Contains(args, "--version") || slices.Contains(args, "-v") {
		// https://github.com/ziglang/zig/issues/22269
		return arch + "-linux-gnu"
	}
	return arch + "-linux-gnu" + "." + glibcVersion
}

func processArg0(arg0 string) (string, error) {
	switch arg0 {
	case CC:
		return "cc", nil
	case CXX:
		return "c++", nil

	// `llvm-` prefix so that CMake finds it
	// https://gitlab.kitware.com/cmake/cmake/-/issues/23554
	// https://gitlab.kitware.com/cmake/cmake/-/issues/18712#note_1006035
	// ../../libtool: line 1887: /mnt/ar: No such file or directory
	case "ar", "llvm-ar":
		return "ar", nil
	case "ranlib", "llvm-ranlib":
		return "ranlib", nil
	case "strip", "llvm-strip":
		return "strip", nil

	default:
		return "", fmt.Errorf("zigcc.go: Error: unknown wrapper name: %s", arg0)
	}
}

func processArgs(args []string) []string {
	newArgs := make([]string, 0, len(args))
	for _, arg := range args {
		// deal with -Wp,-D_FORTIFY_SOURCE=2:
		//  this comes in https://github.com/giampaolo/psutil/blob/master/setup.py#L254
		//  build defaults to using python's flags and they are the RHEL fortified ones
		if strings.HasPrefix(arg, "-Wp,") {
			newArgs = append(newArgs, strings.Split(arg, ",")[1:]...)

		} else if arg == "-mtune=generic" {
			// error: unknown target CPU 'generic'
			// https://github.com/ziglang/zig/issues/12767
			continue

		} else if strings.HasPrefix(arg, "-mcpu=power") {
			// error: unknown CPU: 'power9'
			newArgs = append(newArgs, "-mcpu=pwr"+arg[len("-mcpu=power"):])
		} else if strings.HasPrefix(arg, "-mtune=power") {
			newArgs = append(newArgs, "-mtune=pwr"+arg[len("-mtune=power"):])

			// OpenBLAS's Makefile.power detects that you are using a Clang-based compiler (Zig) and automatically appends -fno-integrated-as.
			// /usr/bin/as -a64 -mppc64 -mlittle-endian -mpower8 -I .. -I . -o /root/.cache/zig/tmp/29e640c58e36ff72-tobf16.o /tmp/tobf16-0619ba.s -gdwarf-4
			// > /tmp/tobf16-423d78.s:63: Error: unrecognized opcode: `extswsli'
			// --env=CFLAGS=-fintegrated-as",
		} else if arg == "-fno-integrated-as" {
			newArgs = append(newArgs, "-fintegrated-as")

		} else {
			newArgs = append(newArgs, arg)
		}
	}
	return newArgs
}

func main() {
	arg0 := filepath.Base(os.Args[0])
	subcommand, err := processArg0(arg0)
	if err != nil {
		fmt.Fprintf(os.Stderr, "zigcc.go: Error: %v\n", err)
		os.Exit(1)
	}

	argv := os.Args[1:]
	target := getTarget(subcommand, argv)

	newArgs := []string{
		zig,
		subcommand,
	}
	if subcommand == "cc" || subcommand == "c++" {
		newArgs = append(newArgs, "-target", target)
		// codeserver: :33:10: fatal error: 'X11/Xlib.h' file not found
		// -isystem=... does not work, requires passing as two separate args

		// Kimi K2 suggests using --search-prefix= instead of --sysroot
		newArgs = append(newArgs, "--sysroot", "/")

		//// Gemini suggests disabling zig's libc
		//switch subcommand {
		//case CC:
		//	newArgs = append(newArgs,
		//		"-nostdinc", // Exclude Zig's internal headers
		//		"-nostdlib", // Exclude Zig's startup/crt files
		//		"-lc",       // Link against glibc's libc
		//
		//		// K2 also suggests -Wl,--version-script
		//		//  # Prevents linking symbols newer than 2.17, but doesn't fix headers
		//		//  echo '{ global: *; }; GLIBC_2.17;' > version.script
		//		//  zig cc -target x86_64-linux-gnu.2.28 -Wl,--version-script=version.script main.c
		//	)
		//case CXX:
		//	newArgs = append(newArgs, "-nostdinc++", "-nostdlib++", "-lc++")
		//}

		newArgs = append(newArgs,
			"-isystem", "/usr/include",
			"-L/usr/lib64",
			"-isystem", "/usr/local/include",
			"-L/usr/local/lib64",

			//// Get Zig's internal library path first
			//"-isystem", "/mnt/lib/include",

			//// trustryai installs the gcc13 toolset but does not activate it
			////dnf whatprovides '**/omp.h'
			//// /usr/lib/clang/19/include/omp.h
			// we need to add the clang version of the library, the gcc one fails on atomics def mismatches
			"-isystem", "/usr/lib/clang/20/include",
			"-L/usr/lib64/llvm20/lib64",
			//// /usr/lib/gcc/s390x-redhat-linux/11/include/omp.h
			//// /opt/rh/gcc-toolset-13/root/usr/lib/gcc/s390x-redhat-linux/13/include/omp.h
			//"-isystem", "/usr/lib/gcc/x86_64-redhat-linux/11/include",
			//"-isystem", "/usr/lib/gcc/aarch64-redhat-linux/11/include",
			//"-isystem", "/usr/lib/gcc/ppc64le-redhat-linux/11/include",
			//"-isystem", "/usr/lib/gcc/s390x-redhat-linux/11/include",

			// https://github.com/llvm/llvm-project/issues/109993
			// putting clang-based zigcc where previously gcc was expected causes headaches
			// it worked for the simple things, but for the more complicated ones it's a problem
			// and another gotcha will be when some images use the developer toolset with newer gcc

			// it is super hard to inject all this transparently
		)
	}
	newArgs = append(newArgs, processArgs(argv)...)

	//// these will be at the end of the command line and will overpower everything that came before
	//switch subcommand {
	//case CC:
	//	newArgs = append(newArgs, cflags...)
	//case CXX:
	//	newArgs = append(newArgs, cxxflags...)
	//}

	env := os.Environ()
	// TODO: I should introduce ccache here, so that it caches the modified args, not original cmdline
	// anyways, ccache is not really very helpful right now; need to evaluate if it is worth it overall
	// the hit rate when I tried this was extremely low, but nonzero; what's going on?
	if err := syscall.Exec(newArgs[0], newArgs, env); err != nil {
		fmt.Fprintf(os.Stderr, "zigcc.go: Error executing zig: %v\n", err)
		os.Exit(1)
	}
}
