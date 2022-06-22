# builder

builder is a Python build tool specialized for building C/C++ projects.

### Features

- header file dependency tracking
    - modification of a header file will cause all
      source files that depend on it to be recompiled
- recompiling out of date objects
    - any source file that is older than its corresponding
      object file will be recompiled
- multithreaded compilation
- halt after non-zero return code
- single JSON description file


### Usage

Execute `MODE` in `builder.json`:

```./builder.py MODE```

Execute `MODE` in builder file `FILE`:

```./builder.py -b FILE MODE```


### Examples

Example builder.json for a C++ project:

```json
{
    "compileCmd": "g++ -c",
    "linkCmd": "g++",
    
    "outputName": "a.out",
    "headerExt": ["h", "hpp"],
    "sourceExt": ["c", "cpp"],
    "objectExt": "o",
    
    "compileFlags": [
        "-std=c++20",
        "-o",
        "%out"
    ],
    "linkFlags": [
        "-o",
        "%out"
    ],
    
    "sourceDir": "src",
    "includeDir": "include",
    "objectDir": [
        "build",
        "%mode"
    ],
    
    "modes": {
        "debug": {
            "compileFlags": [
                "-g",
            ]
        },
        "release": {
            "compileFlags": [
                "-O3",
                "-DNDEBUG"
            ],
            "linkFlags": [
                "-s"
            ]
        }
    }
}
```

A builder file is made up of a dictionary of variables and modes.
When running builder with `./builder.py MODE` the mode dictionary `MODE` 
will be run. Variables inside of the mode's dictionary will
override any global variables when that mode is run with the exception 
of the flags variable which will be concatenated with the global flags variable.

In this example when the mode `debug` is run, the source files inside `src`
will all be compiled with the command 

    g++ -c -std=c++20 -o build/debug/some_file.cpp.o -g src/some_file.cpp

where `%out` was replaced with `build/debug/some_file.cpp.o`, the auto-generated 
object name of the source file. This was constructed from `%buildDir + some_file.cpp + %objectExt`.
There was a corresponding `%in` special flag (`src/some_file.cpp`) that was implicitly placed at the end 
of the command since it was not included in `compileFlags`.

When the flags are joined together to form the compile/link command, any flags that
start with a `%` are special flags that will be parsed as variables. Any variable
name passed in will be replaced by its entry within the builder.json file 
with the exception of a few context-specific special flags, such as `%out` and `%in`.  
Here are a few more special flags:


| Special flag | Replaced with                            |
|--------------|------------------------------------------|
| `%out`       | output file path                         |
| `%in`        | input file path                          |
| `%mode`      | name of current mode                     |
| `%utime`     | Unix time                                |
| `%self`      | path to builder executable               |
| `%platform`  | platform string returned by sys.platform |


Any flag, special or not, can be prefixed with a `#` to concatenate it 
with the previous flag. This also works with directories.

#### Directories

The directories `sourceDir`, `includeDir`, `objectDir`, and `outputDir` can be 
specified which will tell builder where to find source, global header, object, 
and output files respectively. They can be specified by either
a string with the directory name `"example/path/to/dir"`, or a list of strings 
that will be joined together to form the path `["example", "path", "to", "dir"]`.
The list approach supports the resolving of `%` flags.

#### Commands

Aside from `compileCmd` and `linkCmd` there are also `preCmds` and
`postCmds` that are run before compilation and after linking respectively.
These commands are either a list of strings, each of which will be run as is, or a
list of lists of strings, each of which will be concatenated into a final string and run.
Any command that returns a non-zero error code will halt the build process.

#### Runtime Settings

By specifying a `set` dictionary within an mode, each key will be set to its corresponding
value. This can be useful when running several modes after one another because these
changes persist across a run. For example, in the case of multiplatform compilation:

```js
    ...
    "somePlatform": {
        "set": {
            "libs": ["-llib1","-llib2"]
        }
    },
    "someMode": {
        "linkerFlags": ["-s","%libs","-o","%out"],
        ...
    },
    ...
```

will set the `libs` variable that `someMode` later uses to choose which
libraries to link against. This builder config could be called like this:

    ./builder.py somePlatform someMode

### Installation

Builder can be ran with `./builder.py` or `python ./builder.py`.  
On Linux systems `sudo ./install.sh` 
will install builder at `/usr/local/bin/builder`.


