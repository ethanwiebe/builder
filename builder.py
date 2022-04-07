#!/bin/python

import os,argparse


def IsFileModified(time,filename):
    ftime = GetFileTime(filename)
    return time<=ftime

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

def GoUpNLevels(path,n):
    for i in range(n):
        index = path.rfind('/')
        path = path[:index+1]
    return path

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

    cppOptionsTemplate = {
            'outputName': 'a',
            'compileCommand': 'g++',
            'flags':[
                '-std=c++20',
                '-Wall',
                '-g',
                '-o',
                '$outputName'
                ],
            'sourceExtension': 'cpp',
            'headerExtension': 'h',
            'objectExtension': 'o',
            'sourceDir': 'src',
            'objectDir': '',
            'outputDir': 'bin',
    }

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
    
    def Build(self,mode=''):
        self.CollectAllCompilables(self.options['sourceDir'])
        self.InvertDependencies()
        self.GetRebuildSet()
 
        if mode=='' and 'defaultMode' in self.options:
            mode = self.options['defaultMode']
            self.InfoPrint(f"Using default mode {mode}")

        if mode not in self.options['compileFlags']:
            raise ValueError(f"Mode {mode} is missing from the compile flags!")
        
        if mode not in self.options['linkFlags']:
            raise ValueError(f"Mode {mode} is missing from the link flags!")


        errored = False
        cmd = ''

        compileCount = len(self.rebuildSet)
        if compileCount!=0 and self.options['compileCommand']!='':
            self.InfoPrint(f'Building {compileCount} files...')
            

            for i,file in enumerate(self.rebuildSet):
                cmd = self.GetCompileCommand(file,mode)
                self.InfoPrint(f'{i+1}/{compileCount} {cmd}')
                code = os.system(cmd)
                if code!=0:
                    errored = True
                    break

            if errored:
                self.InfoPrint("Not all files were successfully compiled!")
                self.InfoPrint("Exiting...")
                return

        if self.options['linkCommand']!='':
            self.InfoPrint('Linking...')

            cmd = self.GetLinkCommand(mode)
            self.InfoPrint(cmd)
            code = os.system(cmd)

            if code!=0:
                self.InfoPrint("Linker error!")

        self.InfoPrint('Done!')

if __name__=='__main__':
    options = {
            'outputName': 'context',
            'compileCommand': 'g++ -c',
            'linkCommand': 'g++',
            'defaultMode': 'release',
            'compileFlags':{
                'debug':[
                    '%input',
                    '-std=c++20',
                    '-Wall',
                    '-ggdb3',
                    '-Og',
                    '-DCURSES_INTERFACE',
                    '-o',
                    '%output'
                ],
                'release':[
                    '%input',
                    '-std=c++20',
                    '-DCURSES_INTERFACE',
                    '-DNDEBUG',
                    '-Wall',
                    '-O3',
                    '-o',
                    '%output'
                ]
            },
            'linkFlags':{
                'debug':[
                    '%input',
                    "-o",
                    "%output",
                    '-lncurses'
                ],
                'release':[
                    '%input',
                    '-s',
                    "-o",
                    "%output",
                    '-lncurses'
                ]
            },
            'sourceExtension': 'cpp',
            'headerExtension': 'h',
            'objectExtension': 'o',
            'sourceDir': '../../cpp/context2/src',
            'objectDir': '../../cpp/context2/build',
            'outputDir': '../../cpp/context2/bin',
    }

    parser = argparse.ArgumentParser(description="Only builds what needs to be built.")
    group = parser.add_mutually_exclusive_group()
    parser.add_argument("mode",default='',help="specify the set of flags to use",nargs='?')
    group.add_argument("-v","--verbose",help="print more info for debugging",action="store_true")
    group.add_argument('-q','--quiet',help='silence all output (from this program)',action='store_true')
    args = parser.parse_args()


    b = Builder(options,CPPDeps)
    if args.verbose:
        b.debug = True
    
    if args.quiet:
        b.quiet = True


    b.Build(args.mode)

