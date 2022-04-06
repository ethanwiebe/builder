import os


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

    def __init__(self,options):
        self.options = options
        self.prefixPath = ''
        self.depdict = {}
        self.compileFiles = set()

    def SetExtractFunc(self,func):
        self.depExtractFunc = func

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

    def GetRebuildSet(self,objDir):
        self.rebuildSet = set()

        for file in self.compileFiles:
            objFile = SetExtension(os.path.join(objDir,os.path.basename(file)),self.options['objectExtension'])
            if IsObjFileOutdated(file,objFile):
                self.rebuildSet.add(file)

        outputAge = GetFileTime(os.path.join(self.options['outputDir'],self.options['outputName']))
        for headerFile in self.invdict:
            if GetFileTime(headerFile)>=outputAge:
                print(f'cascading {headerFile}...')
                self.rebuildSet = self.rebuildSet.union(self.HeaderFileCascade(headerFile))

    def GetBuildCommand(self,file):
        cmd = self.options['compileCommand']
        filePlaced = False
        for flag in self.options['debugFlags']:
            if flag[0]=='%':
                if flag[1:] == 'outputName':
                    flag = self.options['outputName']
                elif flag[1:] == 'inputFile':
                    filePlaced = True
                    flag = file
                else:
                    raise ValueError(f"Unexpected special flag {flag}, options are %outputName and %inputFile")
            
            cmd += ' '+flag

        if not filePlaced:
            cmd += ' '+file

        return cmd
    
    def Build(self):
        self.CollectAllCompilables(self.options['sourceDir'])
        self.InvertDependencies()
        self.GetRebuildSet(self.options['objectDir'])

        print(f'Building {len(self.rebuildSet)} files...')



        print('Done!')

if __name__=='__main__':
    options = {
            'outputName': 'context2',
            'compileCommand': 'g++ -c',
            'linkCommand': 'g++',
            'debugFlags':[
                '%inputFile',
                '-std=c++20',
                '-Wall',
                '-g',
                '-o',
                '%outputName'
            ],
            'releaseFlags':[
                '-std=c++20',
                '-Wall',
                '-O3',
                '-s',
                '-o',
                '%outputName'
            ],
            'sourceExtension': 'cpp',
            'headerExtension': 'h',
            'objectExtension': 'o',
            'sourceDir': '../../cpp/context2/src',
            'objectDir': '../../cpp/context2/build',
            'outputDir': '../../cpp/context2/bin',
    }

    b = Builder(options)
    b.SetExtractFunc(CPPDeps)

