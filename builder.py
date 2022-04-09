#!/bin/python

import sys,os,subprocess,argparse,json,threading,time

RED = 1
GREEN = 2
YELLOW = 3
BLUE = 4
MAGENTA = 5
CYAN = 6
WHITE = 7

noColor = False

def ResetTextColor():
    global noColor
    if noColor:
        return ''

    return '\x1b[0m'

def TextColor(color,bold=0):
    global noColor
    if noColor:
        return ''

    return f'\x1b[{bold};{30+color}m'

def IsObjFileOutdated(srcFile,objFile):
    return GetFileTime(srcFile)>=GetFileTime(objFile)


def GetFileTime(filename):
    if not os.path.exists(filename):
        return 0
    
    return int(os.path.getmtime(filename))

def GetExtension(filename):
    return os.path.splitext(filename)[1][1:]

def SetExtension(filename,ext):
    return os.path.splitext(filename)[0]+'.'+ext

def GetPrefixAndName(path):
    if '/' in path:
        endLoc = path.rfind('/')
        prefix = path[:endLoc+1]
        filename = path[endLoc+1:]
    
    return prefix,filename

def CPPExtractIncludeFile(line):
    start = line.find('"')
    end = line.find('"',start+1)
    return line[start+1:end]

def CPPDeps(path):
    deps = set()

    prefix,filename = GetPrefixAndName(path)

    with open(prefix+filename,'r') as f:
        for line in f:
            if line.startswith('#include') and '"' in line:
                dep = CPPExtractIncludeFile(line)
                depprefix = os.path.normpath(prefix+dep)

                deps.add(depprefix)

    return deps

class Builder:
    def __init__(self,options,extractFunc):
        self.options = options
        self.depExtractFunc = extractFunc
        self.depdict = {}
        self.compileFiles = set()
        self.debug = False
        self.quiet = False

        self.commandFailed = False
        self.failLock = threading.Lock()
        self.printLock = threading.Lock()

    def DebugPrint(self,msg):
        if self.debug:
            self.InfoPrint(msg)

    def InfoPrint(self,msg):
        if not self.quiet:
            print(msg)

    def ThreadedPrint(self,msg):
        with self.printLock:
            self.InfoPrint(msg)

    def DirContainsObjects(self,mode):
        l = os.listdir(GetModeVar(self.options,mode,'objectDir'))
        for f in l:
            if GetExtension(f)==GetModeVar(self.options,mode,'objectExtension'):
                return True

        return False

    def FindFileDependencies(self,path):
        deps = self.depExtractFunc(path)
        self.depdict[path] = deps
        for d in deps:
            if d not in self.depdict: #if dependency not tracked, add it and recursively search for more deps
                self.FindFileDependencies(d)
    
    def FindAllDependenciesFrom(self,mainPath):
        self.depdict = {}
        self.FindFileDependencies(mainPath)
    
    def InvertDependencies(self):
        self.invdict = {}
        for file in self.depdict:
            for dep in self.depdict[file]:
                if dep not in self.invdict:
                    self.invdict[dep] = set()
                self.invdict[dep].add(file)
        return self.invdict

    def HeaderFileCascade(self,mode,headerFile,cascadeSet=None): #return all source files affected by a header file
        if cascadeSet == None:
            cascadeSet = set()

        children = self.invdict[headerFile]
        for child in children:
            if GetExtension(child)==GetModeVar(self.options,mode,'sourceExtension'):
                cascadeSet.add(child)
            elif GetExtension(child)==GetModeVar(self.options,mode,'headerExtension'):
                cascadeSet = self.HeaderFileCascade(mode,child,cascadeSet)

        return cascadeSet
        
                
    def CollectCompilables(self,srcDir,srcExt):
        files = os.listdir(srcDir)
        for file in files:
            path = os.path.join(srcDir,file)
            if os.path.isdir(path):
                self.CollectCompilables(path,srcExt)
            elif GetExtension(file)==srcExt:
                self.compileFiles.add(path)
                self.FindFileDependencies(path)
    
    def CollectAllCompilables(self,srcDir,srcExt):
        self.compileFiles = set()
        self.CollectCompilables(srcDir,srcExt)
        self.DebugPrint(f"Found {len(self.compileFiles)} source files.")
        self.DebugPrint(f"Found {len(self.depdict)} total files.")

    def GetRebuildSet(self,mode):
        self.rebuildSet = set()

        for srcFile in self.compileFiles:
            objFile = self.GetObjectFromSource(mode,srcFile)
            if IsObjFileOutdated(srcFile,objFile):
                self.rebuildSet.add(srcFile)
                self.DebugPrint(f"Adding source file {srcFile}\nReason: outdated object")

        outputPath = self.GetOutputPath(mode)
        outputAge = GetFileTime(outputPath)
        self.DebugPrint(f'Output ({outputPath}) has age {outputAge}')

        for headerFile in self.invdict:
            headerAge = GetFileTime(headerFile)
            if headerAge>=outputAge:
                self.DebugPrint(f'Cascading {headerFile}...')
                headerSet = self.HeaderFileCascade(mode,headerFile)
                for srcFile in headerSet:
                    objFile = self.GetObjectFromSource(mode,srcFile)
                    if headerAge>=GetFileTime(objFile):
                        self.rebuildSet.add(srcFile)
                        self.DebugPrint(f"Adding source file {srcFile}\nReason: found in outdated header cascade")

    def GetObjectsPath(self,mode):
        return os.path.join(GetModeVar(self.options,mode,'objectDir'),SetExtension('*',GetModeVar(self.options,mode,'objectExtension')))

    def GetObjectFromSource(self,mode,src):
        return os.path.join(GetModeVar(self.options,mode,'objectDir'),SetExtension(os.path.basename(src),GetModeVar(self.options,mode,'objectExtension')))

    def GetOutputPath(self,mode):
        return os.path.join(GetModeVar(self.options,mode,'outputDir'),GetModeVar(self.options,mode,'outputName'))

    def GetCompileCommand(self,mode,file):
        cmd = GetModeVar(self.options,mode,'compileCommand')
        filePlaced = False
        objVersion = self.GetObjectFromSource(mode,file)
        compileFlags = GetModeCompileFlags(self.options,mode)
        for flag in compileFlags:
            if flag == '':
                continue

            if flag[:2]=='%%': #escaped %
                flag = flag[1:]
            elif flag[0]=='%':
                if flag[1:] == 'output':
                    flag = objVersion
                elif flag[1:] == 'input':
                    filePlaced = True
                    flag = file
                else:
                    print(f"{TextColor(RED,1)}Unexpected special flag {flag}, valid options are %output and %input")
                    print(ExitingMsg())
                    quit()
            
            cmd += ' '+flag

        if not filePlaced:
            cmd += ' '+file

        return cmd

    def GetLinkCommand(self,mode):
        cmd = GetModeVar(self.options,mode,'linkCommand')
        inputFilesPlaced = False
        inputFiles = self.GetObjectsPath(mode)
        outputFile = self.GetOutputPath(mode)

        linkFlags = GetModeLinkFlags(self.options,mode)
        for flag in linkFlags: 
            if flag == '':
                continue

            if flag[:2]=='%%':
                flag = flag[1:]
            elif flag[0]=='%':
                if flag[1:] == 'output':
                    flag = outputFile
                elif flag[1:] == 'input':
                    inputFilesPlaced = True
                    flag = inputFiles
                else:
                    print(f"{TextColor(RED,1)}Unexpected special flag {flag}, valid options are %output and %input")
                    print(ExitingMsg())
                    quit()
            
            cmd += ' '+flag

        if not inputFilesPlaced:
            cmd += ' '+inputFiles

        return cmd
    
    def RunCommand(self,cmd):
        p = subprocess.Popen(cmd,stdout=sys.stdout,stderr=sys.stderr,shell=True)
        return p.wait()

    def Scan(self,mode):
        self.CollectAllCompilables(GetModeVar(self.options,mode,'sourceDir'),GetModeVar(self.options,mode,'sourceExtension'))
        self.InvertDependencies()
        self.GetRebuildSet(mode)

    def BuildObjectsFromList(self,l):
        code = 0
        threadName = threading.current_thread().name
        i = 1

        for src,obj,cmd in l:
            if self.debug:
                self.ThreadedPrint(f"{TextColor(BLUE)}{cmd}{ResetTextColor()}")
            else:
                self.ThreadedPrint(f'{TextColor(WHITE,1)}[{TextColor(CYAN,1)}{threadName}{TextColor(WHITE,1)}] {TextColor(GREEN)}Building ({i}/{len(l)}): {TextColor(YELLOW)}{src} {TextColor(WHITE,1)}-> {TextColor(BLUE)}{obj}{ResetTextColor()}')

            code = self.RunCommand(cmd)
            if code!=0:
                self.SetCommandFailed()
                break
            i += 1

        return code

    def HasCommandFailed(self):
        with self.failLock:
            return self.commandFailed

    def SetCommandFailed(self):
        with self.failLock:
            self.commandFailed = True

    def CommandFailedQuit(self):
        if self.HasCommandFailed():
            self.ThreadedPrint(f"{TextColor(RED,1)}Not all files were successfully compiled!\n{ExitingMsg()}")
            quit()


    def DispatchCommands(self,cmdList):
        cores = os.cpu_count()
        threads = []

        for i in range(cores):
            cmds = cmdList[i::cores]
            thread = threading.Thread(target=self.BuildObjectsFromList,args=(cmds,),name=str(i+1))
            thread.start()
            threads.append(thread)
        
        try:
            while threading.active_count()!=1:
                self.CommandFailedQuit()
                time.sleep(0.2)
        except KeyboardInterrupt:
            self.SetCommandFailed()

        self.CommandFailedQuit()

    def Build(self,mode):
        if mode=='':
            mode = self.options['defaultMode']
            self.InfoPrint(f"{TextColor(WHITE,1)}Using default mode {TextColor(CYAN,1)}{mode}{ResetTextColor()}")
        else:
            if mode not in self.options['modes']:
                self.InfoPrint(f"{TextColor(RED,1)}Mode {TextColor(CYAN,1)}{mode}{TextColor(RED,1)} not found!")
                self.InfoPrint(ExitingMsg())
                quit()
            
            self.InfoPrint(f"{TextColor(WHITE,1)}Using mode {TextColor(CYAN,1)}{mode}{ResetTextColor()}")

        self.Scan(mode)

        errored = False
        cmd = ''

        compileCount = len(self.rebuildSet)
        # compilation
        if compileCount!=0 and GetModeVar(self.options,mode,'compileCommand')!='':
            self.InfoPrint(f'{TextColor(WHITE,1)}Building {TextColor(CYAN,1)}{compileCount}{TextColor(WHITE,1)} files...')
            
            cmdList = [(file,self.GetObjectFromSource(mode,file),self.GetCompileCommand(mode,file)) for i,file in enumerate(self.rebuildSet)]
            
            self.DispatchCommands(cmdList)

##            for i,file in enumerate(self.rebuildSet):
  ##              cmd = self.GetCompileCommand(mode,file)
    ##            if self.debug:
      ##              self.InfoPrint(f'{TextColor(GREEN)}{i+1}/{compileCount}: {TextColor(BLUE)}{cmd}{ResetTextColor()}')
        ##        else:
          ##          src = file
            ##        obj = self.GetObjectFromSource(mode,src)
              ##      self.InfoPrint(f'{TextColor(GREEN)}Building ({i+1}/{compileCount}): {TextColor(YELLOW)}{src} {TextColor(WHITE,1)}-> {TextColor(BLUE)}{obj}{ResetTextColor()}')
                ##code = os.system(cmd)
                #if code!=0:
                 #   errored = True
                  #  break

            if errored:
                self.InfoPrint(f"{TextColor(RED,1)}Not all files were successfully compiled!{ResetTextColor()}")
                self.InfoPrint(f"{TextColor(RED)}Exiting...{ResetTextColor()}")
                return

        # linking
        if GetModeVar(self.options,mode,'linkCommand')!='':
            self.InfoPrint(f'{TextColor(WHITE,1)}Linking executable...{ResetTextColor()}')

            cmd = self.GetLinkCommand(mode)
            if self.debug:
                self.InfoPrint(f'{TextColor(BLUE)}{cmd}{ResetTextColor()}')
            else:
                src = self.GetObjectsPath(mode)
                dest = self.GetOutputPath(mode)
                self.InfoPrint(f'{TextColor(GREEN)}Linking: {TextColor(BLUE)}{src} {TextColor(WHITE,1)}-> {TextColor(GREEN,1)}{dest}{ResetTextColor()}')
            code = self.RunCommand(cmd)

            if code!=0:
                self.InfoPrint(f"{TextColor(RED,1)}Linker error!{ResetTextColor()}")

        self.InfoPrint(f'{TextColor(WHITE,1)}Done!')
    
    def Clean(self,mode):
        if mode not in self.options['modes']:
            self.InfoPrint(f"{TextColor(RED,1)}Mode {TextColor(CYAN,1)}{mode}{TextColor(RED,1)} not found!")
            self.InfoPrint(ExitingMsg())
            quit()
            
        self.InfoPrint(f"{TextColor(WHITE,1)}Using mode {TextColor(CYAN,1)}{mode}{ResetTextColor()}")
        self.InfoPrint(f"{TextColor(WHITE,1)}Cleaning up...{TextColor(YELLOW)}")
        if self.DirContainsObjects(mode):
            path = self.GetObjectsPath(mode)
            cmd = f"rm {path}"
            if self.debug:
                self.InfoPrint(cmd)
            else:
                self.InfoPrint(f"{TextColor(YELLOW)}Removing {path}")
            self.RunCommand(cmd)
        
        path = self.GetOutputPath(mode)
        if os.path.exists(path):
            cmd = f"rm {path}"
            if self.debug:
                self.InfoPrint(cmd)
            else:
                self.InfoPrint(f"{TextColor(YELLOW)}Removing {path}")

            self.RunCommand(cmd)

        self.InfoPrint(f'{TextColor(WHITE,1)}Done!')


def ExitingMsg():
    return f"{TextColor(RED)}Exiting...{ResetTextColor()}"

def GetModeCompileFlags(options,mode):
    flags = []
    if 'compileFlags' in options['modes'][mode]:
        flags += options['modes'][mode]['compileFlags']

    if 'compileFlags' in options:
        flags += options['compileFlags']

    return flags

def GetModeLinkFlags(options,mode):
    flags = []
    if 'linkFlags' in options['modes'][mode]:
        flags += options['modes'][mode]['linkFlags']

    if 'linkFlags' in options:
        flags += options['linkFlags']

    return flags

def GetModeVar(options,mode,varName): # return a mode var, falling back to the root dict if not available in mode
    if varName in options['modes'][mode]:
        return options['modes'][mode][varName]

    if varName in options:
        return options[varName]

    return None

def VarInOptions(options,mode,varName):
    if varName in options['modes'][mode]:
        return True
    
    if varName in options:
        return True

    return False

def VarNeverNull(options,varName): # is the var never undefined in any mode?
    if varName in options:
        return True

    for mode in options['modes']:
        if varName in options['modes'][mode]:
            return True

    return False

def GetUndefinedModes(options,varName): # get all modes for which this var is undefined
    modes = []
    for mode in options['modes']:
        if varName not in options['modes'][mode]:
            modes.append(mode)
    return modes

def VerifyModesTypes(modes):
    for mode in modes:
        if type(modes[mode])!=dict:
            print(f'{TextColor(RED,1)}Mode {TextColor(CYAN,1)}{mode}{TextColor(RED,1)} must be of type dict!')
            print(ExitingMsg())
            quit()
        
        error = False
        for key in modes[mode]:
            item = modes[mode][key]
            if type(item) not in [str,list]:
                print(f'{TextColor(RED,1)}Type of "{key}" in mode {TextColor(CYAN,1)}{mode}{TextColor(RED,1)} is not a string or a list!')
                error = True

        if error:
            print(ExitingMsg())
            quit()

def FixDirs(options):
    dirs = ['sourceDir','objectDir','outputDir']

    for d in dirs:
        modes = options['modes']
        for mode in modes:
            if d in modes[mode]:
                if modes[mode][d]=='':
                    modes[mode][d] = '.'
        if d in options:
            if options[d]=='':
                options[d] = '.'


def GetOptionsFromFile(file):
    if not os.path.exists(f"./{file}"):
        print(f"{TextColor(RED,1)}No {file} file found!{ResetTextColor()}")
        print(ExitingMsg())
        quit()

    s = ''
    with open(file,'r') as f:
        s = f.read()
    
    op = json.JSONDecoder().decode(s)

    error = False

    if 'modes' not in op:
        print(f'{TextColor(RED,1)}Builder file must specify "modes"!')
        print(ExitingMsg())
        quit()
    elif type(op['modes'])!=dict:
        print(f'{TextColor(RED,1)}Expected "modes" to be of type dict!')
        print(ExitingMsg())
        quit()
    elif len(op['modes'])==0:
        print(f'{TextColor(RED,1)}Builder file must specify at least one mode in "modes"!')
        print(ExitingMsg())
        quit()

    modes = op['modes']

    VerifyModesTypes(modes)

    if not VarNeverNull(op,'compileCommand'):
        for mode in GetUndefinedModes(op,'compileCommand'):
            print(f'{TextColor(RED,1)}Option "compileCommand" is unspecified in mode {TextColor(CYAN,1)}{mode}{TextColor(RED,1)}!')
        print(f'{TextColor(RED,1)}Builder file must specify "compileCommand"!')
        error = True

    if 'compileCommand' not in op:
        op['compileCommand'] = ''
    
    if not VarNeverNull(op,'linkCommand'):
        for mode in GetUndefinedModes(op,'linkCommand'):
            print(f'{TextColor(RED,1)}Option "linkCommand" is unspecified in mode {TextColor(CYAN,1)}{mode}{TextColor(RED,1)}!')
        print(f'{TextColor(RED,1)}Builder file must specify "linkCommand"!')
        error = True

    if 'linkCommand' not in op:
        op['linkCommand'] = ''

    if 'outputName' not in op:
        op['outputName'] = 'a'


    if 'defaultMode' not in op:
        op['defaultMode'] = list(op['modes'].keys())[0]

    if 'sourceExtension' not in op:
        op['sourceExtension'] = 'cpp'

    if 'headerExtension' not in op:
        op['headerExtension'] = 'h'

    if 'objectExtension' not in op:
        op['objectExtension'] = 'o'

    if not VarNeverNull(op,'sourceDir'):
        for mode in GetUndefinedModes(op,'sourceDir'):
            print(f'{TextColor(RED,1)}Option "sourceDir" is unspecified in mode {TextColor(CYAN,1)}{mode}{TextColor(RED,1)}!')

        print(f'{TextColor(RED,1)}Builder file must specify "sourceDir"!')
        error = True
    

    if 'objectDir' not in op:
        op['objectDir'] = '.'

    if 'outputDir' not in op:
        op['outputDir'] = '.'

    FixDirs(op)

    if not VarNeverNull(op,'compileFlags'):
        for mode in GetUndefinedModes(op,'compileFlags'):
            if GetModeVar(op,mode,'compileCommand')!='':
                # if compileCommand is specified for this mode it needs to have a list of compileFlags
                print(f'{TextColor(RED,1)}Option "compileFlags" is unspecified while "compileCommand" is non-empty in mode {TextColor(CYAN,1)}{mode}{TextColor(RED,1)}!')
                error = True

    if not VarNeverNull(op,'linkFlags'):
        for mode in GetUndefinedModes(op,'linkFlags'):
            if GetModeVar(op,mode,'linkCommand')!='':
                # if linkCommand is specified for this mode it needs to have a list of linkFlags
                print(f'{TextColor(RED,1)}Option "linkFlags" is unspecified while "linkCommand" is non-empty in mode {TextColor(CYAN,1)}{mode}{TextColor(RED,1)}!')
                error = True

    if error:
        print(ExitingMsg())
        quit()

    return op


def main():    
    global noColor
    name = 'builder'
    builderVersion = '0.0.1'

    parser = argparse.ArgumentParser(prog='builder',description="Only builds what needs to be built.")
    group = parser.add_mutually_exclusive_group()
    parser.add_argument("mode",default='',help="specify the set of flags to use",nargs='?')
    parser.add_argument("-b",metavar='FILE',default='builder.json',help="specify name of builder file to use (default builder.json)")
    parser.add_argument("-c","--clean",help="remove all object files and output",action="store_true")
    group.add_argument("-v","--verbose",help="print more info for debugging",action="store_true")
    group.add_argument('-q','--quiet',help='silence all output (from this program)',action='store_true')
    parser.add_argument("--log",metavar="FILE",default="",help="write all output to the specified log file")
    parser.add_argument("--nocolor",help="disables output of color escape sequences",action="store_true")
    parser.add_argument("--version",action="store_true",help='show program\'s version number and exit')
    args = parser.parse_args()

    if args.nocolor or not sys.stdout.isatty():
        noColor = True


    builderLog = ''

    if args.log:
        noColor = True
        sys.stdout.close()
        f = open(args.log,'w')
        sys.stdout = f
        sys.stderr = f

    if args.version:
        print(f'{TextColor(WHITE,1)}{name} {TextColor(CYAN,1)}{builderVersion}{ResetTextColor()}')
        quit()

    builderFile = args.b

    options = GetOptionsFromFile(builderFile)

    b = Builder(options,CPPDeps)

    if args.verbose:
        b.debug = True
    
    if args.quiet:
        b.quiet = True

    if args.clean:
        if args.mode=='' or args.mode=='all':
            for mode in options['modes']:
                b.Clean(mode)
        else:
            b.Clean(args.mode)
    else:
        if args.mode=='all':
            for mode in options['modes']:
                b.Build(mode)
        else:
            b.Build(args.mode)

    print(ResetTextColor(),end='')


if __name__=='__main__':
   main() 
