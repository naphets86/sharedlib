# Proposal: A Unified Shared Library Format (`.sl`) with a Standardized Loading Procedure

**Status:** Discussion draft
**Subject:** Unifying file format, naming, loading behavior, and symbol export of dynamic libraries across operating systems
**Motivation:** Experience from the projects `subgraph-sat-solver-econ` and `gen-db`, where C++ code is used from Python through a shared library

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Situation: What Differs Today](#2-current-situation-what-differs-today)
   - 2.1 [Evidence from the two projects](#21-evidence-from-the-two-projects)
3. [Problem Analysis](#3-problem-analysis)
   - 3.1 [Extra effort without added value](#31-extra-effort-without-added-value)
   - 3.2 [Avoidable sources of error](#32-avoidable-sources-of-error)
   - 3.3 [Understanding and onboarding](#33-understanding-and-onboarding)
   - 3.4 [Dependence on the operating system](#34-dependence-on-the-operating-system)
4. [Goals and Non-Goals](#4-goals-and-non-goals)
5. [Core Requirement: A Standardized, OS-Independent Loading Procedure](#5-core-requirement-a-standardized-os-independent-loading-procedure)
   - 5.1 [Principle: specify behavior, not mechanism](#51-principle-specify-behavior-not-mechanism)
   - 5.2 [Layered architecture](#52-layered-architecture)
   - 5.3 [The standardized loading procedure](#53-the-standardized-loading-procedure)
   - 5.4 [Standardized search order](#54-standardized-search-order)
   - 5.5 [Standardized API surface](#55-standardized-api-surface)
   - 5.6 [Standardized error model](#56-standardized-error-model)
   - 5.7 [Standardized lifecycle and threading rules](#57-standardized-lifecycle-and-threading-rules)
   - 5.8 [Standardized symbol export](#58-standardized-symbol-export)
   - 5.9 [Conformance testing](#59-conformance-testing)
6. [The `.sl` Format](#6-the-sl-format)
   - 6.1 [Naming](#61-naming)
   - 6.2 [Metadata header](#62-metadata-header)
   - 6.3 [Container options](#63-container-options)
7. [Benefits](#7-benefits)
8. [Objections and Honest Assessment](#8-objections-and-honest-assessment)
   - 8.1 ["Same CPU architecture means same library"](#81-same-cpu-architecture-means-same-library)
   - 8.2 ["The problem is already solved by abstractions"](#82-the-problem-is-already-solved-by-abstractions)
   - 8.3 [Legacy and compatibility](#83-legacy-and-compatibility)
   - 8.4 [Who decides?](#84-who-decides)
   - 8.5 ["Another loader means another attack surface"](#85-another-loader-means-another-attack-surface)
9. [Implementation Paths](#9-implementation-paths)
10. [Security Considerations](#10-security-considerations)
11. [Risks](#11-risks)
12. [Application to the Example Projects](#12-application-to-the-example-projects)
13. [Recommended Roadmap](#13-recommended-roadmap)
14. [Open Questions](#14-open-questions)
- [Appendix A: Example Metadata Sketch](#appendix-a-example-metadata-sketch)
- [Appendix B: Resolution Flow (Informal)](#appendix-b-resolution-flow-informal)

---

## 1. Executive Summary

Today the same concept is called `.dll`, `.so`, or `.dylib`, depending on the operating system. Behind these names are three different binary formats (PE, ELF, Mach-O), three loaders, and three different rules for deciding which functions are visible to the outside. Anyone who ships software for several systems has to build, test, and document everything three times.

This draft proposes a **unified shared library (`.sl`)**: one file name convention, one container description, one set of export rules, and above all **one standardized loading procedure**.

The central requirement of this proposal is the following:

> **The loading procedure must be made operating-system independent through abstraction and standardization.**

Concretely, a program must be able to say "load the library `wsat_shim`, find the symbol `wsat_solve`, and call it" using the same API, the same search order, the same error model, and the same lifecycle on Windows, Linux, and macOS. Everything platform-specific is hidden behind a defined interface and is the responsibility of the loader implementation, not of every individual project.

This document explains why that is worthwhile, which parts can realistically be unified and which cannot, and how to get there in stages.

---

## 2. Current Situation: What Differs Today

| Aspect | Windows | Linux | macOS |
|---|---|---|---|
| File extension | `.dll` | `.so` (often `.so.1.2.3`) | `.dylib` (or `.so` for plug-ins) |
| Name prefix | none (MSVC) or `lib` (MinGW) | `lib` | `lib` |
| Binary format | PE/COFF | ELF | Mach-O |
| Load API | `LoadLibrary` | `dlopen` | `dlopen` |
| Symbol lookup | `GetProcAddress` | `dlsym` | `dlsym` |
| Default visibility | nothing exported unless `__declspec(dllexport)` | everything visible unless hidden | everything visible unless hidden |
| Dependency lookup | DLL search path, `PATH`, `add_dll_directory` | `RPATH`, `RUNPATH`, `LD_LIBRARY_PATH` | `@rpath`, `@loader_path`, `DYLD_*` |
| Link-time companion file | import library `.lib` | the `.so` itself | the `.dylib` itself |
| Versioning | manifest, file version | SONAME, symbol versions | `install_name`, compatibility version |
| Initialization hooks | `DllMain` | `__attribute__((constructor))`, `.init_array` | `__attribute__((constructor))`, `__mod_init_func` |
| Error reporting | `GetLastError`, error codes | `dlerror` string | `dlerror` string |
| Unloading | `FreeLibrary` | `dlclose` | `dlclose` |

### 2.1 Evidence from the two projects

- `src/native.py` (`subgraph-sat-solver-econ`) contains `library_filename()`, which knows four file names depending on `sys.platform`: `wsat_shim.dll`, `libwsat_shim.dll`, `libwsat_shim.so`, `libwsat_shim.dylib`.
- The same file calls `os.add_dll_directory(...)` for each `PATH` entry on Windows so that dependent DLLs can be found. This is not necessary on Linux.
- `build_shim()` contains a special case that additionally looks for `libwsat_shim.dll` in case MinGW was used instead of MSVC.
- `csubgraph_shim.cpp` (`gen-db`) defines a macro `CSUB_EXPORT`, which is `extern "C" __declspec(dllexport)` on Windows and something different elsewhere.
- `csubgraph_native.py` (`gen-db`) contains code that statically links the MinGW runtime on Windows so that `libstdc++-6.dll` does not have to be loaded at run time.
- The README of `subgraph-sat-solver-econ` describes the build using PowerShell syntax and lists four possible file names ("depends on platform and toolchain").

None of these places contains domain logic. All of it is pure platform glue.

---

## 3. Problem Analysis

### 3.1 Extra effort without added value

Every project that offers a native library must solve at least the following for each platform:

1. **Naming:** Which file name is searched for?
2. **Export:** How is a function made visible? This requires macros, `.def` files, or visibility flags.
3. **Search paths:** Where do dependencies live, and how is this configured?
4. **Runtime:** Is the C++ runtime linked statically or dynamically, and how does it reach the user?
5. **Build:** Which compiler and which flags?
6. **Test:** Does everything work on every system with every toolchain?
7. **Loading code:** Which API is called, in which order, with which error handling?

This is the same work in every project. It is repeated thousands of times, and each repetition introduces its own errors.

### 3.2 Avoidable sources of error

- A function is visible on Linux but not exported on Windows. The bug only shows up on the second system.
- A DLL fails to load on Windows because a dependent DLL is not on the search path. The error message often names only the requested file, not the missing dependency.
- MinGW and MSVC libraries are mixed, and the C++ runtimes do not match.
- Files with the same name but different meaning: on macOS, `.so` is a plug-in while `.dylib` is a library.
- Search-path semantics differ in subtle ways (current directory, `PATH`, `LD_LIBRARY_PATH`), which leads to "works on my machine" situations and to security problems.

### 3.3 Understanding and onboarding

For beginners and non-specialists, for example scientists who want to use a solver from Python, it is not apparent why three names exist for the same concept. The learning effort concerns the operating system rather than the actual problem. In `subgraph-sat-solver-econ` and `gen-db`, a dedicated README section had to be written for exactly this.

### 3.4 Dependence on the operating system

Code that loads a library cannot be portable as long as it must know the file name and the load API. Every abstraction (`ctypes.CDLL`, `libloading`, `dlopen` wrappers) is a workaround that fills exactly this gap. The fact that such wrappers exist in every language demonstrates the need, but each of them defines its own search order, its own error messages, and its own edge cases. **The abstraction exists, but it is not standardized.**

---

## 4. Goals and Non-Goals

### Goals

1. One file name convention on all systems: `<name>.sl`.
2. **One standardized, OS-independent loading procedure**, defined by a specification and not by the behavior of the underlying system loader.
3. One export model: explicit, opt-in, identical on all platforms.
4. One metadata block describing ABI version, name, version, and dependencies.
5. One search-path policy with defined precedence.
6. One error model with machine-readable codes and human-readable messages, including naming of missing dependencies.
7. Coexistence with existing libraries (no big-bang replacement).

### Non-goals

1. Making identical machine code run on every OS and CPU (see section 8.1).
2. Replacing PE, ELF, or Mach-O in the short term.
3. Standardizing C++ ABIs. The stable boundary is the **C ABI**.

---

## 5. Core Requirement: A Standardized, OS-Independent Loading Procedure

This section is the heart of the proposal. A uniform file name is helpful, but the real unification must happen in the **procedure** by which a library is located, validated, loaded, initialized, queried, and released.

### 5.1 Principle: specify behavior, not mechanism

The specification defines **what must happen and in which order**, not which system call performs it. A conforming loader implementation may use `LoadLibraryEx` on Windows, `dlopen` on Linux and macOS, or its own user-space ELF/PE/Mach-O mapper. The caller cannot tell the difference.

This is the same architectural idea as a POSIX-style portability layer, a language runtime's module system, or the WebAssembly Component Model: a thin, strictly specified interface above heterogeneous systems.

### 5.2 Layered architecture

```
+-------------------------------------------------------------+
|  Application / language binding (Python, Rust, Java, C++ ...)|
+-------------------------------------------------------------+
|  Standard Loader Interface (SLI)  <-- specified, uniform     |
|    sl_open / sl_symbol / sl_close / sl_error / sl_info       |
+-------------------------------------------------------------+
|  Loader core: resolution, validation, lifecycle, errors      |
|    (reference implementation, one behavior everywhere)       |
+-------------------------------------------------------------+
|  Platform adapter (the only OS-specific code)                |
|    Windows: LoadLibraryEx / AddDllDirectory                  |
|    Linux:   dlopen / dlsym  (RTLD_*)                         |
|    macOS:   dlopen / dlsym  (@rpath, @loader_path)           |
+-------------------------------------------------------------+
|  Native library container: PE / ELF / Mach-O (inside .sl)    |
+-------------------------------------------------------------+
```

All OS-specific behavior is confined to the **platform adapter**. Everything above it is identical on every system and can be tested once with one conformance suite.

### 5.3 The standardized loading procedure

A conforming loader performs the following steps, in this order, on every platform:

1. **Name resolution.** Input is a logical name (`wsat_shim`) or an explicit path. The loader appends `.sl` if needed. No platform prefixes (`lib`) or suffixes (`.dll`, `.so.1`) are part of the logical name.
2. **Location.** The loader walks the search order defined in section 5.4 and stops at the first match. The result of the walk (all candidates examined) is retained for diagnostics.
3. **Container validation.** The loader reads the `.sl` header and checks magic number, container version, target platform, CPU architecture, and ABI version. A mismatch yields a specific error (see section 5.6) *before* any code is mapped.
4. **Dependency resolution.** The dependency list from the metadata is resolved recursively using the same search order, with the directory of the requesting library as a fixed search root. Cycles are detected and reported. All dependencies are resolved *before* the library itself is mapped, so that a missing dependency produces an error that names the dependency.
5. **Mapping.** The platform adapter maps the native payload using the system facility or the loader's own mapper.
6. **Initialization.** Initialization runs in a defined order: dependencies first, then the library. The optional `sl_init` entry point is called exactly once per process and handle group. Platform-specific hooks (`DllMain`, constructors) are wrapped so that the observable ordering and re-entrancy rules are the same everywhere.
7. **Export table binding.** Only symbols marked as exported in the metadata are visible to `sl_symbol`. Lookup of a non-exported symbol fails on all platforms, even where the native format would have exposed it.
8. **Handle return.** The caller receives an opaque handle. Handles are reference-counted; opening the same library twice returns the same underlying instance.
9. **Release.** `sl_close` decrements the count. At zero, `sl_fini` runs (if defined), the library is unmapped, and resources are released, in reverse dependency order.

### 5.4 Standardized search order

The following precedence applies on every platform. A lookup stops at the first hit.

1. **Explicit path** passed by the caller.
2. **Environment variable `SL_PATH`** (list separator is standardized: `;` is *not* used on one system and `:` on another; the specification fixes a single separator, for example `:` with a defined escaping rule, or alternatively a list API).
3. **Directory of the requesting module** (the library or executable that calls `sl_open`), including a defined relative subdirectory such as `./sl/`.
4. **Application directory.**
5. **System-wide directories** declared per platform in the adapter, and *only* those.

Explicitly excluded, on all platforms:

- The **current working directory** is never searched implicitly (prevents DLL hijacking).
- Platform-specific variables (`PATH`, `LD_LIBRARY_PATH`, `DYLD_LIBRARY_PATH`) are **not** consulted for `.sl` resolution. This removes a whole class of surprises and makes behavior reproducible.
- Dependencies are looked up in the same order as the library itself, with no per-platform exceptions. The need for `os.add_dll_directory` disappears.

### 5.5 Standardized API surface

A minimal, language-neutral C API forms the normative interface. Language bindings are thin wrappers over it.

```c
typedef struct sl_handle sl_handle;

typedef enum {
    SL_OK = 0,
    SL_ERR_NOT_FOUND,         /* no candidate in the search order          */
    SL_ERR_DEPENDENCY_MISSING,/* a declared dependency could not be found  */
    SL_ERR_ARCH_MISMATCH,     /* wrong CPU architecture or platform target */
    SL_ERR_ABI_MISMATCH,      /* incompatible ABI version                  */
    SL_ERR_INVALID_CONTAINER, /* corrupt or unknown container              */
    SL_ERR_SYMBOL_NOT_FOUND,  /* symbol absent or not exported             */
    SL_ERR_INIT_FAILED,       /* sl_init returned failure                  */
    SL_ERR_CYCLE,             /* cyclic dependency                         */
    SL_ERR_ACCESS_DENIED,     /* rejected by security policy               */
    SL_ERR_INTERNAL           /* platform adapter failure                  */
} sl_status;

typedef struct {
    sl_status   code;
    const char *message;       /* human readable, stable wording           */
    const char *failed_name;   /* the library or dependency that failed    */
    const char *searched;      /* newline-separated list of paths tried    */
    int         native_error;  /* original OS error code, for diagnostics  */
} sl_error;

sl_status sl_open  (const char *name_or_path, unsigned flags,
                    sl_handle **out, sl_error *err);
sl_status sl_symbol(sl_handle *h, const char *symbol,
                    void **out, sl_error *err);
sl_status sl_info  (sl_handle *h, /* name, version, abi, deps, path */ ...);
sl_status sl_close (sl_handle *h, sl_error *err);
```

Language bindings then look the same everywhere. For Python:

```python
import sl                              # reference binding
lib = sl.open("wsat_shim")             # identical on Windows, Linux, macOS
solve = lib.symbol("wsat_solve", argtypes=[...], restype=...)
```

Compare this with the current code, which needs a platform switch, a path walk, and platform-specific preparation before the first symbol can be used.

### 5.6 Standardized error model

Today, error handling is one of the least portable parts of loading libraries: `GetLastError()` returns a number, `dlerror()` returns a free-form string, and both often omit the real cause. The standard requires:

- A fixed set of **error codes** (section 5.5) that mean the same thing everywhere.
- A **`failed_name`** field that always names the actual culprit, which is the missing dependency, not just the library that was requested.
- A **`searched`** field listing the paths tried, in order.
- The original OS error preserved in **`native_error`** for debugging.
- Messages with stable wording so that they can be documented and searched.

Example of the intended diagnostic:

```
SL_ERR_DEPENDENCY_MISSING: cannot load 'wsat_shim'
  missing dependency: 'cryptosolver' (required >= 1.2)
  searched:
    /opt/app/sl/cryptosolver.sl
    /opt/app/cryptosolver.sl
    /usr/local/lib/sl/cryptosolver.sl
```

### 5.7 Standardized lifecycle and threading rules

The specification fixes behaviors that currently differ subtly:

- `sl_open` and `sl_close` are thread-safe. Concurrent opens of the same library produce one instance.
- Initialization is executed at most once and never while holding a loader-internal lock that user code could re-enter.
- Initialization must not call `sl_open` on a library that is currently being initialized (reported as `SL_ERR_CYCLE`), which avoids the loader-lock deadlock class known from Windows.
- Unloading while symbols are still in use is the caller's responsibility, but the loader guarantees reference-counting semantics identical on every platform.

### 5.8 Standardized symbol export

- **Default is hidden.** Only symbols explicitly marked are exported, via one standardized macro or attribute (`SL_EXPORT`, later possibly `[[sl::export]]`).
- The build tooling translates this to `__declspec(dllexport)`, `__attribute__((visibility("default")))`, or an export list, so projects never write these themselves.
- The exported symbol list is stored in the `.sl` metadata and enforced by the loader. A symbol missing from this list is not reachable, regardless of what the native format would expose.
- The exported interface is a **C ABI** (`extern "C"`, fixed-width integer types). C++ types do not cross the boundary.

### 5.9 Conformance testing

A standard is only as good as its test suite. The project should ship a **conformance suite** that any loader implementation, platform adapter, or language binding must pass. It covers search order, dependency resolution, error codes, lifecycle, and export enforcement. This is how identical behavior is verified instead of assumed.

---

## 6. The `.sl` Format

### 6.1 Naming

- Extension **`.sl`** on all systems.
- Naming rule: `<name>.sl`, with no platform prefix and no version suffix in the file name. The version lives in the metadata.
- Optionally, platform and architecture may be encoded in package names or in the metadata, not in the file name (for example `wsat_shim-x86_64.sl` only if explicitly desired for distribution).

### 6.2 Metadata header

Every `.sl` carries a standardized header. Today every project builds this itself; in both example projects it exists as `*_abi_version()`.

| Field | Meaning |
|---|---|
| `magic` / `container_version` | identifies the format and its revision |
| `name` | logical library name |
| `version` | library version (semantic versioning) |
| `abi_version` | version of the exported C interface |
| `targets` | list of platform/architecture payloads contained |
| `dependencies` | logical names with version ranges |
| `exports` | list of exported symbols (optionally with signature hints) |
| `runtime` | declared runtime requirement, embedded or external |
| `init` / `fini` | optional lifecycle entry points |

### 6.3 Container options

Two interpretations are possible and are discussed in section 14:

- **Naming convention only:** `name.sl` is an ordinary DLL/SO/dylib renamed, with the metadata in a sidecar section or file.
- **True container:** `name.sl` wraps one or more native payloads (a fat-binary approach) together with the metadata block.

Either way, the **loading procedure of section 5 is identical**.

---

## 7. Benefits

| Area | Today | With `.sl` and a standard loader |
|---|---|---|
| File names in code | case distinction per platform | one name |
| **Loading procedure** | **different API, search order, and lifecycle per OS** | **one specified procedure** |
| Export macros | per project, platform-dependent | one standard attribute |
| Search-path logic | `add_dll_directory`, `RPATH`, `@rpath` | one rule |
| Error messages | different and sometimes misleading | uniform, naming the missing dependency |
| Documentation | per platform | written once |
| Entry barrier | high | low |
| Test matrix | 3 formats x toolchains | one behavior, many targets |
| Language bindings (Python, Rust, Java, ...) | each with its own platform logic | written once per language |
| Security posture | depends on OS defaults | one hardened policy |

---

## 8. Objections and Honest Assessment

A sound proposal must know the counterarguments. Some of them are factually correct and determine how far unification can go.

### 8.1 "Same CPU architecture means same library"

This conclusion holds only partly. The CPU architecture defines the **instruction set**, but not the rest of what a library depends on:

- **Calling convention** (Windows x64 and System V x86-64 pass registers differently),
- **System calls**, **memory and thread model**, **runtime library** (MSVCRT/UCRT, glibc, libSystem),
- **Data types** (`long` is 32 bits wide on Windows and 64 bits on Linux),
- **Container format** (PE, ELF, Mach-O) and **symbol resolution**.

True unification of machine code is therefore not achievable by renaming alone. The goal of this proposal is a **uniform interface, a uniform container, and a uniform loading procedure**, not the claim that the same machine code runs unchanged everywhere.

### 8.2 "The problem is already solved by abstractions"

Partly. CMake generates the right file per platform, and `ctypes` and similar tools load it. But that only moves the work into tools, and each tool behaves slightly differently. Each project still has to think about export rules, paths, and runtime, as the two example projects show. Existing abstractions are **implementation conveniences, not standards**: nothing guarantees that `ctypes`, `libloading`, and a Java binding resolve the same library the same way. The proposal turns the abstraction into a specification.

### 8.3 Legacy and compatibility

Billions of existing libraries use today's formats. A new format must coexist, not replace. A realistic path is a container or loader that uses the existing formats internally (see section 9). The loader should also be able to open ordinary `.dll`/`.so`/`.dylib` files through the same API ("legacy mode") so that adoption can be incremental.

### 8.4 Who decides?

File formats and loaders belong to the operating system vendors and the respective ecosystems. A standard prevails only if it is implemented on all three sides or provided as a layer above the systems. This is why stage 1 and 2 of the roadmap deliberately do not depend on vendor cooperation.

### 8.5 "Another loader means another attack surface"

Valid. A new loading layer must be smaller and stricter than what it wraps. See section 10.

---

## 9. Implementation Paths

There are three graduated options.

**Stage 1: Convention and tooling (feasible immediately).**
A build tool (for example a CMake module) produces a file named `name.sl` on every system, internally an ordinary DLL, `.so`, or `.dylib`, plus metadata. A small runtime package per language provides `sl_open` and `sl_symbol`, which unifies search paths, export checks, and error messages **according to the standardized procedure of section 5**. This already reduces effort considerably without changing any operating system.

**Stage 2: Dedicated loader (medium effort).**
A user-space library loads a unified container format that holds the appropriate native payload for each platform, similar to a fat binary. This is proven by Apple Universal Binaries and by bundling formats such as APE (Actually Portable Executable). At this stage the loader may take over mapping itself, which makes behavior independent of OS quirks.

**Stage 3: Operating system support (long term).**
The vendors recognize `.sl` natively. This is politically and technically the most demanding step and depends on standardization.

**Related approaches that should be evaluated:**

- WebAssembly with WASI and the Component Model (one format, multiple runtimes, at the cost of performance and interface overhead).
- Portable C-ABI layers in languages such as Rust (`libloading`), as a source of lessons for API design.
- Existing plug-in standards (for example Python's stable ABI, JNI/Panama, Node-API), which have already standardized parts of the boundary.

---

## 10. Security Considerations

A unified loader is only acceptable if it is *more* secure than the status quo.

- **No implicit current-directory search.** Prevents DLL hijacking.
- **No dependence on mutable global environment** (`PATH`, `LD_LIBRARY_PATH`) for resolution. Only `SL_PATH`, and it can be disabled (hardened mode) for privileged processes.
- **Strict search roots.** Search directories must be checked for ownership and write permissions where the platform allows.
- **Optional signature and hash verification** of `.sl` containers, declared in the metadata.
- **Export enforcement** limits the reachable surface of a library to the declared interface.
- **Fail closed.** Any ambiguity (two candidates with conflicting metadata, an ABI mismatch) produces an error, not a silent choice.

---

## 11. Risks

- **Fragmentation:** Another standard next to three existing ones may enlarge the problem at first (the "xkcd 927" effect). Mitigation: a legacy mode that makes the new layer a superset rather than a competitor.
- **Security:** A uniform loader must regulate search paths strictly, otherwise reloading of manipulated libraries becomes possible. DLL hijacking is already a well-known Windows problem.
- **Performance:** Additional layers must not noticeably slow down loading or calls. For the cases considered here (few calls with large data volumes) this is uncritical. Symbol lookup returns plain function pointers, so there is no per-call overhead after binding.
- **Maintenance:** Someone must maintain specification, tools, conformance suite, and reference implementation.
- **Platform divergence over time:** Operating systems change their loader behavior. The platform adapter absorbs this, but it needs continuous testing in CI on all three systems.

---

## 12. Application to the Example Projects

With stage 1, the following could be removed or simplified in both projects:

- `library_filename()` and the MinGW special cases in `build_shim()`,
- the Windows block with `add_dll_directory`,
- the macro `CSUB_EXPORT` and the platform-dependent export lines,
- platform-specific parts of the README instructions (PowerShell backticks, four file names),
- the special handling of the static runtime for MinGW, provided the runtime is declared in the container.

Before:

```python
def library_filename() -> str:
    if sys.platform == "win32":
        return "wsat_shim.dll"
    if sys.platform == "darwin":
        return "libwsat_shim.dylib"
    return "libwsat_shim.so"
```

After:

```python
import sl
lib = sl.open("wsat_shim")      # same code on every system
```

---

## 13. Recommended Roadmap

1. **Sharpen the goal.** Unify naming, export, search path, metadata, and, above all, the **loading procedure and its API**. Do not unify machine code.
2. **Write the specification first.** Search order, lifecycle, error codes, metadata, and export attribute, as a versioned document open to external contribution.
3. **Build the reference loader (stage 1).** A small C core with platform adapters for Windows, Linux, and macOS, plus a CMake module. Start with the Python binding, since both projects use `ctypes`.
4. **Write the conformance suite alongside.** Run it in CI on all three systems and on both MSVC and MinGW toolchains.
5. **Migrate the two example projects** and measure how much platform code disappears and how many failure modes are eliminated.
6. **Only after demonstrated benefit,** pursue stage 2 (container, fat binaries) and stage 3 (OS support).

---

## 14. Open Questions

- Should `.sl` be its own container, or only a naming convention over existing formats?
- How is the C++ runtime handled (embedded, shipped alongside, assumed present)?
- How are multiple architectures (x86-64, ARM64) represented in one file?
- Which versioning and compatibility rules apply (ABI versioning, semantic version ranges for dependencies)?
- What exactly is the separator and escaping rule for `SL_PATH`, so that it is identical on every system?
- Should the loader support lazy binding and delayed loading, and if so with what guaranteed semantics?
- How is unloading handled for libraries that start threads or register callbacks?
- Who maintains the specification, the reference implementation, and the conformance suite?

---

## Appendix A: Example Metadata Sketch

```toml
[sl]
container_version = 1
name        = "wsat_shim"
version     = "1.4.0"
abi_version = 3

[[target]]
os   = "windows"
arch = "x86_64"
payload = "pe"

[[target]]
os   = "linux"
arch = "x86_64"
payload = "elf"

[[target]]
os   = "macos"
arch = "arm64"
payload = "macho"

[runtime]
cpp = "embedded"          # or "external" with a declared dependency

[[dependency]]
name = "cryptosolver"
version = ">=1.2,<2"

[exports]
symbols = ["wsat_abi_version", "wsat_solve", "wsat_free"]

[lifecycle]
init = "wsat_init"
fini = "wsat_fini"
```

## Appendix B: Resolution Flow (Informal)

```
sl_open("wsat_shim")
 |-- resolve name -> "wsat_shim.sl"
 |-- walk search order: explicit -> SL_PATH -> module dir -> app dir -> system
 |-- validate container (magic, platform, arch, abi)        -> SL_ERR_*
 |-- resolve dependencies recursively (same search order)   -> SL_ERR_DEPENDENCY_MISSING / SL_ERR_CYCLE
 |-- map payload via platform adapter
 |-- run init (dependencies first, once)                    -> SL_ERR_INIT_FAILED
 |-- bind export table (only declared symbols visible)
 `-- return reference-counted handle
```
