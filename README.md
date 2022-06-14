# builder

Builder is a Python build tool specialized for C/C++ codebases.

### Features

- header file dependency tracking
- recompiling out of date objects
- multithreaded compilation
- cancel build after non-zero return code
- single JSON build file

### Examples

Example builder.json for a C++ project:

```json
{
	"compileCmd": "g++ -c",
	"linkCmd": "g++",
	
	"outputName": "a.out",
	"headerExt": "h",
	"sourceExt": "cpp",
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
	"objectDir": [
		"build",
		"%mode"
	]
	
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
When running builder with `./builder.py MODE` the mode with name MODE 
will be found and run. Variables inside of a mode dictionary will
override any global variables when that mode is run, with the exception 
of the flags variables which will be concatenated together.

In this example when the mode `debug` is run, the source files inside `src`
will be compiled with the command 

`g++ -c -std=c++20 -o build/debug/some_file.cpp.o -g src/some_file.cpp`

where `%out` was replaced with build/debug/some_file.cpp.o, the auto-generated 
object name of the source file. This was constructed from `%buildDir + some_file.cpp + %objectExt`.
There was a corresponding `%in` flag (src/some_file.cpp) that was implicitly placed at the end 
of the command since it was not included in `compileFlags`.

When the flags are joined together to form the compile/link command, any flags that
start with a `%` will be parsed as variables. Any variable
name passed in will be replaced by its entry within the builder.json file 
with the exception of a few context-specific flags, such as `%out` and `%in`.  
Here are a few more special flags:


| Name         | Replaced with                            |
|--------------|------------------------------------------|
| %out         | output file path                         |
| %in          | input file path                          |
| %mode        | current mode                             |
| %utime       | current Unix time                        |
| %self        | path to builder executable               |
| %platform    | platform string returned by sys.platform |


Directories can be specified which will tell builder where to look for
source, object, and output files. They can be specified by either
a string with the directory name, or a list of strings that will be joined
together to form the path. The list approach supports resolving of `%` flags.

### Installation

Builder can be ran with `./builder.py`.  
On Linux systems `sudo ./install.sh` 
will install builder at `/usr/local/bin/builder`.

### Usage

Execute MODE in builder.json:

```./builder.py MODE```

Execute MODE in builder file FILE:

```./builder.py -b FILE MODE```


