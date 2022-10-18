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
- halt build process after non-zero return code
- single JSON description file


### Usage

Execute `MODE` in `builder.json`:

```./builder.py MODE```

Execute modes `MODE1/SUBMODE1` and `MODE2` in sequence:

```./builder.py MODE1/SUBMODE1 MODE2```

Execute `MODE` in builder file `FILE`:

```./builder.py -b FILE MODE```


### Examples

Example builder.json for a C++ project:

```json
{
    "compileCmd": [
        "g++ -c",
        "%compileFlags"
    ],
    "linkCmd": [
        "g++",
        "%linkFlags"
    ],
    
    "outputName": "a.out",
    "headerExt": ["h", "hpp"],
    "sourceExt": ["c", "cpp"],
    "objectExt": "o",
    
    "compileFlags": [
        "-std=c++20",
        "-o",
        "%out",
        "%in"
    ],
    "linkFlags": [
        "-o",
        "%out",
        "%in"
    ],
    
    "sourceDir": "src",
    "includeDir": "include",
    "objectDir": [
        "build",
        "%modePath"
    ],
    "outputDir": [
        "bin",
        "%modePath"
    ],
    
    "modes": {
        "debug": {
            "compileFlags": [
                "%compileFlags",
                "-g"
            ]
        },
        "release": {
            "compileFlags": [
                "%compileFlags",
                "-O3",
                "-DNDEBUG"
            ],
            "linkFlags": [
                "%linkFlags",
                "-s"
            ]
        }
    }
}
```

Multiplatform example targeting both Linux and Windows:

```json
{
    "compileCmd": [
        "g++ -c",
        "%compileFlags"
    ],
    "linkCmd": [
        "g++",
        "%linkFlags"
    ],
    
    "outputName": "a.out",
    "headerExt": ["h", "hpp"],
    "sourceExt": ["c", "cpp"],
    "objectExt": "o",
    
    "compileFlags": [
        "-std=c++20",
        "-o",
        "%out",
        "%in"
    ],
    "linkFlags": [
        "-o",
        "%out",
        "%in"
    ],
    
    "sourceDir": "src",
    "includeDir": "include",
    "objectDir": [
        "build",
        "%modeLast"
    ],
    "outputDir": [
        "bin",
        "%modeLast"
    ],
    
    "platformModes":{
        "debug": {
            "compileFlags": [
                "%compileFlags",
                "-g"
            ]
        },
        "release": {
            "compileFlags": [
                "%compileFlags",
                "-O3",
                "-DNDEBUG"
            ],
            "linkFlags": [
                "%linkFlags",
                "-s",
                "%libs"
            ]
        }
    },
    
    "modes": {
        "linux": {
            "libs": [
                "-lX11",
                "-lncurses"
            ],
            "modes": "%platformModes"
        },
        "windows": {
            "libs": [
                "-lshlwapi"
            ],
            "modes": "%platformModes"
        }
    }
}
```

A builder file is made up of a dictionary of variables and modes.
When running builder with `./builder.py MODE` the mode dictionary `MODE` 
will be run. Variables inside of the mode's dictionary will
override any variables in an outer scope when that mode is run. The only time this
rule is broken is when a variable refers to itself, in which case it will refer to
that variable in the next innermost scope.
In the first example when the mode `debug` is run, the source files inside `src`
will all be compiled with the command 

    g++ -c -std=c++20 -o build/debug/some_file.cpp.o src/some_file.cpp -g

and linked with the command

    g++ -o bin/debug/a.out build/debug/*.o

Modes can be recursively nested by supplying further `modes` dicts.
This can be used for finer compilation granularity or for targeting 
multiple platforms such as in the second example.

When a command is a list of strings instead of just a single string, it will be
concatenated into a single string to form the final command. Any command fragment that starts with
a `%` will be interpreted as a variable.
Any variable name passed in will be replaced by its entry within the builder.json file 
with the exception of a few context-specific variables, such as `%out` and `%in`. A literal `%` can be
escaped by writing `\\%`.
Directories can also be specified as a list of fragments which will be concatenated together
and undergo variable substitution to form the final path.
Here are a few more special variables:


| Special variable | Replaced with                                    |
|------------------|--------------------------------------------------|
| `%out`           | output file path                                 |
| `%in`            | input file path                                  |
| `%mode`          | full name of current mode                        |
| `%modeFirst`     | current top level mode                           |
| `%modeLast`      | lowest submode of current mode                   |
| `%modePath`      | `mode/submode` becomes `mode\submode` on Windows |
| `%utime`         | Unix time                                        |
| `%self`          | path to builder executable                       |
| `%platform`      | `linux`, `windows`, `macOS`, or sys.platform     |


Any fragment, special or not, can be prefixed with a `#` to concatenate it 
with the previous fragment, bypassing the default separator.

#### Directories

The directories `sourceDir`, `includeDir`, `objectDir`, and `outputDir` can be 
specified which will tell builder where to find source, global header, object, 
and output files respectively. They can be specified by either
a string with the directory name `"example/path/to/dir"`, or a list of fragments 
that will be joined together to form the path `["example", "path", "to", "dir"]`.
The list approach supports the resolving of `%` variables.

#### Commands

    preCmds -> compileCmd -> linkCmd -> postCmds

Aside from `compileCmd` and `linkCmd` there are also the lists `preCmds` and
`postCmds` that are run before compilation and after linking respectively.
Any command that returns a non-zero error code will halt the build process.

### Installation

Builder can be ran with `./builder.py` or `python ./builder.py`.  
On Linux systems `sudo ./install.sh` 
will install builder at `/usr/local/bin/builder`.

