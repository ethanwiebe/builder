#!/bin/python

import os,argparse,json

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

    def DebugPrint(self,msg):
        if self.debug:
            self.InfoPrint(msg)

    def InfoPrint(self,msg):
        if not self.quiet:
            print(msg)

    def DirContainsObjects(self):
        l = os.listdir(self.options['objectDir'])
        for f in l:
            if GetExtension(f)==self.options['objectExtension']:
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

    def HeaderFileCascade(self,headerFile,cascadeSet=None): #return all source files affected by a header file
        if cascadeSet == None:
            cascadeSet = set()

        children = self.invdict[headerFile]
        for child in children:
            if GetExtension(child)==self.options['sourceExtension']:
                cascadeSet.add(child)
            elif GetExtension(child)==self.options['headerExtension']:
                cascadeSet = self.HeaderFileCascade(child,cascadeSet)

        return cascadeSet
        
                
    def CollectCompilables(self,srcdir):
        files = os.listdir(srcdir)
        for file in files:
            path = os.path.join(srcdir,file)
            if os.path.isdir(path):
                self.CollectCompilables(path)
            elif GetExtension(file)==self.options['sourceExtension']:
                self.compileFiles.add(path)
                self.FindFileDependencies(path)
    
    def CollectAllCompilables(self,srcdir):
        self.compileFiles = set()
        self.CollectCompilables(srcdir)
        self.DebugPrint(f"Found {len(self.compileFiles)} source files.")
        self.DebugPrint(f"Found {len(self.depdict)} total files.")

    def GetRebuildSet(self):
        self.rebuildSet = set()

        for srcFile in self.compileFiles:
            objFile = SetExtension(os.path.join(self.options['objectDir'],os.path.basename(srcFile)),self.options['objectExtension'])
            if IsObjFileOutdated(srcFile,objFile):
                self.rebuildSet.add(srcFile)
                self.DebugPrint(f"Adding source file {srcFile}\nReason: outdated object")

        outputPath = os.path.join(self.options['outputDir'],self.options['outputName'])
        outputAge = GetFileTime(outputPath)
        self.DebugPrint(f'Output ({outputPath}) has age {outputAge}')

        for headerFile in self.invdict:
            headerAge = GetFileTime(headerFile)
            if headerAge>=outputAge:
                self.DebugPrint(f'Cascading {headerFile}...')
                headerSet = self.HeaderFileCascade(headerFile)
                for srcFile in headerSet:
                    objFile = SetExtension(os.path.join(self.options['objectDir'],os.path.basename(srcFile)),self.options['objectExtension'])
                    if headerAge>=GetFileTime(objFile):
                        self.rebuildSet.add(srcFile)
                        self.DebugPrint(f"Adding source file {srcFile}\nReason: found in outdated header cascade")

    def GetObjectsPath(self):
        return os.path.join(self.options['objectDir'],SetExtension('*',self.options['objectExtension']))

    def GetObjectFromSource(self,src):
        return os.path.join(self.options['objectDir'],SetExtension(os.path.basename(src),self.options['objectExtension']))

    def GetCompileCommand(self,file,mode):
        cmd = self.options['compileCommand']
        filePlaced = False
        objVersion = self.GetObjectFromSource(file)
        for flag in self.options['compileFlags'][mode]:
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
        cmd = self.options['linkCommand']
        inputFilesPlaced = False
        inputFiles = self.GetObjectsPath()
        outputFile = os.path.join(self.options['outputDir'],self.options['outputName'])

        for flag in self.options['linkFlags'][mode]:
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
    
    def Scan(self):
        self.CollectAllCompilables(self.options['sourceDir'])
        self.InvertDependencies()
        self.GetRebuildSet()

    def Build(self,mode):
        self.Scan()
 
        if mode=='':
            mode = self.options['defaultMode']
            self.InfoPrint(f"{TextColor(WHITE,1)}Using default mode {TextColor(CYAN,1)}{mode}{ResetTextColor()}")


        errored = False
        cmd = ''

        compileCount = len(self.rebuildSet)
        if compileCount!=0 and self.options['compileCommand']!='':
            self.InfoPrint(f'{TextColor(WHITE,1)}Building {TextColor(CYAN,1)}{compileCount}{TextColor(WHITE,1)} files...')
            

            for i,file in enumerate(self.rebuildSet):
                cmd = self.GetCompileCommand(file,mode)
                if self.debug:
                    self.InfoPrint(f'{TextColor(GREEN)}{i+1}/{compileCount}: {TextColor(BLUE)}{cmd}{ResetTextColor()}')
                else:
                    src = file
                    obj = self.GetObjectFromSource(src)
                    self.InfoPrint(f'{TextColor(GREEN)}Building ({i+1}/{compileCount}): {TextColor(YELLOW)}{src} {TextColor(WHITE,1)}-> {TextColor(BLUE)}{obj}{ResetTextColor()}')
                code = os.system(cmd)
                if code!=0:
                    errored = True
                    break

            if errored:
                self.InfoPrint(f"{TextColor(RED,1)}Not all files were successfully compiled!{ResetTextColor()}")
                self.InfoPrint(f"{TextColor(RED)}Exiting...{ResetTextColor()}")
                return

        if self.options['linkCommand']!='':
            self.InfoPrint(f'{TextColor(WHITE,1)}Linking executable...{ResetTextColor()}')

            cmd = self.GetLinkCommand(mode)
            if self.debug:
                self.InfoPrint(f'{TextColor(BLUE)}{cmd}{ResetTextColor()}')
            else:
                src = self.GetObjectsPath()
                dest = os.path.join(self.options['outputDir'],self.options['outputName'])
                self.InfoPrint(f'{TextColor(GREEN)}Linking: {TextColor(BLUE)}{src} {TextColor(WHITE,1)}-> {TextColor(GREEN,1)}{dest}{ResetTextColor()}')
            code = os.system(cmd)

            if code!=0:
                self.InfoPrint(f"{TextColor(RED,1)}Linker error!{ResetTextColor()}")

        self.InfoPrint(f'{TextColor(WHITE,1)}Done!')
    
    def Clean(self):
        self.InfoPrint(f"{TextColor(WHITE,1)}Cleaning up...{TextColor(YELLOW)}")
        if self.DirContainsObjects():
            path = SetExtension(os.path.join(self.options['objectDir'],'*'),self.options['objectExtension'])
            cmd = f"rm {path}"
            if self.debug:
                self.InfoPrint(cmd)
            else:
                self.InfoPrint(f"{TextColor(YELLOW)}Removing {path}")
            os.system(cmd)
        
        
        path = os.path.join(self.options['outputDir'],self.options['outputName'])
        if os.path.exists(path):
            cmd = f"rm {path}"
            if self.debug:
                self.InfoPrint(cmd)
            else:
                self.InfoPrint(f"{TextColor(YELLOW)}Removing {path}")
            os.system(cmd)

        self.InfoPrint(f'{TextColor(WHITE,1)}Done!')


def ExitingMsg():
    return f"{TextColor(RED)}Exiting...{ResetTextColor()}"

def GetOptionsFromFile():
    if not os.path.exists('./builder.json'):
        print(f"{TextColor(RED,1)}No builder.json file found!{ResetTextColor()}")
        print(ExitingMsg())
        quit()

    s = ''
    with open('builder.json','r') as f:
        s = f.read()
    
    op = json.JSONDecoder().decode(s)

    error = False

    cc = False
    lc = False

    if 'compileCommand' not in op:
        print(f'{TextColor(RED,1)}builder.json must specify "compileCommand"!')
        error = True
    else:
        cc = op['compileCommand']!=''

    if 'linkCommand' not in op:
        print(f'{TextColor(RED,1)}builder.json must specify "linkCommand"!')
        error = True
    else:
        lc = op['linkCommand']!=''

    if 'outputName' not in op:
        op['outputName'] = 'a'

    if 'modes' not in op:
        print(f'{TextColor(RED,1)}builder.json must specify "modes"!')
        error = True
    elif len(op['modes'])==0:
        print(f'{TextColor(RED,1)}builder.json must specify at least one mode in "modes"!')
        error = True

    if 'defaultMode' not in op:
        if 'modes' in op and len(op['modes'])!=0:
            op['defaultMode'] = op['modes'][0]

    if 'sourceExtension' not in op:
        op['sourceExtension'] = 'cpp'

    if 'headerExtension' not in op:
        op['headerExtension'] = 'h'

    if 'objectExtension' not in op:
        op['objectExtension'] = 'o'

    if 'sourceDir' not in op:
        print(f'{TextColor(RED,1)}builder.json must specify "sourceDir"!')
        error = True

    if 'objectDir' not in op:
        op['objectDir'] = '.'

    if 'outputDir' not in op:
        op['outputDir'] = '.'

    if cc:
        if 'compileFlags' not in op:
            print(f'{TextColor(RED,1)}builder.json must specify "compileFlags" in order to compile!')
            error = True
        else:
            for mode in op['modes']:
                if mode not in op['compileFlags']:
                    print(f'{TextColor(RED,1)}Mode {TextColor(CYAN,1)}{mode}{TextColor(RED,1)} not included in "compileFlags"!')
                    error = True

    if lc:
        if 'linkFlags' not in op:
            print(f'{TextColor(RED,1)}builder.json must specify "linkFlags" in order to link!')
            error = True
        else:
            for mode in op['modes']:
                if mode not in op['linkFlags']:
                    print(f'{TextColor(RED,1)}Mode {TextColor(CYAN,1)}{mode}{TextColor(RED,1)} not included in "linkFlags"!')
                    error = True


    if error:
        print(ExitingMsg())
        quit()

    return op


def main():    
    global noColor

    parser = argparse.ArgumentParser(description="Only builds what needs to be built.")
    group = parser.add_mutually_exclusive_group()
    parser.add_argument("mode",default='',help="specify the set of flags to use",nargs='?')
    parser.add_argument("--clean",help="remove all object files and output",action="store_true")
    group.add_argument("-v","--verbose",help="print more info for debugging",action="store_true")
    group.add_argument('-q','--quiet',help='silence all output (from this program)',action='store_true')
    parser.add_argument("--nocolor",help="disables output of color (turn this on if redirecting to a file)",action="store_true")
    args = parser.parse_args()

    if args.nocolor:
        noColor = True

    options = GetOptionsFromFile()

    b = Builder(options,CPPDeps)
    if args.verbose:
        b.debug = True
    
    if args.quiet:
        b.quiet = True

    if args.clean:
        b.Clean()
    else:
        b.Build(args.mode)

    print(ResetTextColor(),end='')


if __name__=='__main__':
   main() 
