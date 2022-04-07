#!/bin/python

import os,argparse,json

RED = 1
GREEN = 2
YELLOW = 3
BLUE = 4
MAGENTA = 5
CYAN = 6
WHITE = 7

def ResetTextColor():
    return '\x1b[0m'

def TextColor(color,bold=0):
    return f'\x1b[{bold};{30+color}m'

def IsObjFileOutdated(srcFile,objFile):
    return GetFileTime(srcFile)>=GetFileTime(objFile)

def DirContainsObjects(dirName,objExt):
    l = os.listdir(dirName)
    for f in l:
        if GetExtension(f)==objExt:
            return True

    return False

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

    def GetCompileCommand(self,file,mode):
        cmd = self.options['compileCommand']
        filePlaced = False
        objVersion = os.path.join(self.options['objectDir'],os.path.basename(SetExtension(file,self.options['objectExtension'])))
        for flag in self.options['compileFlags'][mode]:
            if flag[0]=='%':
                if flag[1:] == 'output':
                    flag = objVersion
                elif flag[1:] == 'input':
                    filePlaced = True
                    flag = file
                else:
                    raise ValueError(f"Unexpected special flag {flag}, options are %output and %input")
            
            cmd += ' '+flag

        if not filePlaced:
            cmd += ' '+file

        return cmd

    def GetLinkCommand(self,mode):
        cmd = self.options['linkCommand']
        inputFilesPlaced = False
        inputFiles = os.path.join(self.options['objectDir'],SetExtension("*",self.options['objectExtension']))
        outputFile = os.path.join(self.options['outputDir'],self.options['outputName'])


        for flag in self.options['linkFlags'][mode]:
            if flag[0]=='%':
                if flag[1:] == 'output':
                    flag = outputFile
                elif flag[1:] == 'input':
                    inputFilesPlaced = True
                    flag = inputFiles
                else:
                    raise ValueError(f"Unexpected special flag {flag}, options are %output and %input")
            
            cmd += ' '+flag

        if not inputFilesPlaced:
            cmd += ' '+inputFiles

        return cmd
    
    def Scan(self):
        self.CollectAllCompilables(self.options['sourceDir'])
        self.InvertDependencies()
        self.GetRebuildSet()

    def Build(self,mode=''):
        self.Scan()
 
        if mode=='' and 'defaultMode' in self.options:
            mode = self.options['defaultMode']
            self.InfoPrint(f"{TextColor(WHITE,1)}Using default mode {TextColor(CYAN,1)}{mode}{ResetTextColor()}")

        if mode not in self.options['compileFlags']:
            raise ValueError(f"Mode {mode} is missing from the compile flags!")
        
        if mode not in self.options['linkFlags']:
            raise ValueError(f"Mode {mode} is missing from the link flags!")


        errored = False
        cmd = ''

        compileCount = len(self.rebuildSet)
        if compileCount!=0 and self.options['compileCommand']!='':
            self.InfoPrint(f'{TextColor(WHITE,1)}Building {TextColor(CYAN,1)}{compileCount}{TextColor(WHITE,1)} files...')
            

            for i,file in enumerate(self.rebuildSet):
                cmd = self.GetCompileCommand(file,mode)
                self.InfoPrint(f'{TextColor(GREEN,0)}{i+1}/{compileCount}: {TextColor(BLUE,0)}{cmd}')
                code = os.system(cmd)
                if code!=0:
                    errored = True
                    break

            self.InfoPrint(f'{ResetTextColor()}')

            if errored:
                self.InfoPrint(f"{TextColor(RED,1)}Not all files were successfully compiled!{ResetTextColor()}")
                self.InfoPrint(f"{TextColor(RED)}Exiting...{ResetTextColor()}")
                return

        if self.options['linkCommand']!='':
            self.InfoPrint(f'{TextColor(WHITE,1)}Linking executable...{ResetTextColor()}')

            cmd = self.GetLinkCommand(mode)
            self.InfoPrint(f'{TextColor(BLUE)}{cmd}{ResetTextColor()}')
            code = os.system(cmd)

            if code!=0:
                self.InfoPrint(f"{TextColor(RED,1)}Linker error!{ResetTextColor()}")

        self.InfoPrint(f'{TextColor(WHITE,1)}Done!')
    
    def Clean(self):
        self.InfoPrint(f"{TextColor(WHITE,1)}Cleaning up...{TextColor(YELLOW)}")
        if DirContainsObjects(self.options['objectDir'],self.options['objectExtension']):
            path = SetExtension(os.path.join(self.options['objectDir'],'*'),self.options['objectExtension'])
            cmd = f"rm {path}"
            self.InfoPrint(cmd)
            os.system(cmd)
        
        
        path = os.path.join(self.options['outputDir'],self.options['outputName'])
        if os.path.exists(path):
            cmd = f"rm {path}"
            self.InfoPrint(cmd)
            os.system(cmd)

        self.InfoPrint(f'{TextColor(WHITE,1)}Done!')


    
def GetOptionsFromFile():
    s = ''
    with open('builder.json','r') as f:
        s = f.read()
    
    return json.JSONDecoder().decode(s)


def main():
    if not os.path.exists('./builder.json'):
        print(f"{TextColor(RED,1)}No builder.json file found!{ResetTextColor()}")
        print("{TextColor(RED)}Exiting...{ResetTextColor()}")
        quit()

    options = GetOptionsFromFile()

    parser = argparse.ArgumentParser(description="Only builds what needs to be built.")
    group = parser.add_mutually_exclusive_group()
    parser.add_argument("mode",default='',help="specify the set of flags to use",nargs='?')
    parser.add_argument("--clean",help="remove all object files and output",action="store_true")
    group.add_argument("-v","--verbose",help="print more info for debugging",action="store_true")
    group.add_argument('-q','--quiet',help='silence all output (from this program)',action='store_true')
    args = parser.parse_args()

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
