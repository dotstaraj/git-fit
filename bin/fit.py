from subprocess import Popen as popen, PIPE
from os import stat, path, chdir, getcwd
from json import load, dump
from paths import fitMapToTree, fitTreeToMap
import re

# Get the repo root directory if inside one, otherwise exit
_p = popen('git rev-parse --show-toplevel'.split(), stdout=PIPE)
repoDir = _p.communicate()[0].strip()
_p.returncode == 0 or exit(_p.returncode)

# Get some more directory/file paths we're interested in
selfDir = path.dirname(path.realpath(__file__))
gitDir = popen('git rev-parse --git-dir'.split(), stdout=PIPE).communicate()[0].strip()
fitDir = path.join(gitDir,'fit')
fitFile = path.join(repoDir, '.fit')
cacheDir = path.join(fitDir, 'objects')
syncDir = path.join(cacheDir, 'tosync')
statFile = path.join(fitDir, 'stat')
mergeMineFitFile = path.join(fitDir, 'merge-mine')
mergeOtherFitFile = path.join(fitDir, 'merge-other')
firstTimeFile = path.join(fitDir, 'first-time')
cacheLruFile = path.join(fitDir, 'cache-lru')
savedFile = path.join(fitDir, 'save')
tempDir = path.join(fitDir, 'temp')

_fitFileItemRgx = re.compile('([^:]+):\[([^,]+),(\d+)\],?')

# Parameterized decorator that will wrap the decoratee with a cd into the git directory
# before running the operation, and a cd back into the starting directory afterwards.
# The parameterized form should be used for methods that that are not class members or
# to tell the decorator to use a specific directory as the git directory. The basic
# form should be used only for class member methods where the class also has a
# string self.gitDir member.
def gitDirOperation(arg):
    # "arg" will be either a callable, or a string, depending on how the decorator is used.
    # If the decorator is used as @gitDirOperation, it is used in the basic way and is NOT
    # parameteried. It is parameterized if called with a string, such as
    # @gitDirOperatio('path/gitFolder'). How we get the git directory depends on which
    # form of the decorator is used.

    isParameterized = isinstance(arg, basestring)
    getDir = (lambda s: arg) if isParameterized else (lambda s: s[0].gitDir)

    # Assume non-parameterized form by default. If actually the parameterized form
    # is used, than wrapper() will set decoratee to the passed-in function, which
    # is the actual decoratee
    decoratee = [arg]

    def decorator(*args, **kwargs):
        cwd = getcwd()
        chdir(getDir(args))

        retval = decoratee[0](*args, **kwargs)

        chdir(cwd)
        return retval

    def wrapper(func):
        decoratee[0] = func
        return decorator

    return wrapper if isParameterized else decorator

def fitStats(filename):
    stats = stat(filename)
    return stats.st_size, stats.st_mtime, stats.st_ctime, stats.st_ino

def readFitFile(filePath=fitFile):
    if filePath in filterBinaryFiles([filePath]):
        from gzip import open as gz
        return load(gz(filePath)) if path.exists(filePath) and path.getsize(filePath) > 0 else {}
    else:
        fitFileIn = open(filePath)
        fitData = fitTreeToMap(_readFitFileRec(fitFileIn))
        fitFileIn.close()
        return fitData
    
def _readFitFileRec(fitFileIn):
    items = {}
    for l in fitFileIn:
        l = l.strip()
        if l.endswith('{'):
            items[l.split(':')[0]] = _readFitFileRec(fitFileIn)
        elif l in ('}', '},') :
            break
        else:
            parts = list(_fitFileItemRgx.match(l).groups())
            items[parts[0]] = [parts[1], int(parts[2])]
    return items

def writeFitFile(fitData, filePath=fitFile):
    fitFileOut = open(filePath, 'wb')
    _writeFitFileRec(fitFileOut, fitMapToTree(fitData))
    fitFileOut.close()

def _dictItemComparator(a,b):
    if type(a[1]) == type(b[1]):
        return -1 if a[0] < b[0] else (1 if a[0] > b[0] else 0)
    if type(a[1]) == type({}):
        return 1
    return -1

def _writeFitFileRec(fitFileOut, fitData):
    if len(fitData) == 0:
        return

    items = sorted(fitData.iteritems(), cmp=_dictItemComparator)
    for k,v in items[:-1]:
        _writeFitFileItem(fitFileOut, k, v)
    k,v = items[-1]
    _writeFitFileItem(fitFileOut, k, v, sep='')

def _writeFitFileItem(fitFileOut, k,v, sep=','):
    if type(v) == type({}):
        print >>fitFileOut, '%s:{'%k
        _writeFitFileRec(fitFileOut, v)
        print >>fitFileOut, '}'+sep
    else:
        print >>fitFileOut, ('%s:[%s,%s]'+sep)%(k,v[0],v[1])

def printAsText(fitData):
    items = sorted([(b[:7],a) for a,(b,c) in  fitData.iteritems()], key=lambda i:i[1])
    print '\n'.join(['%s %s'%(h,p) for h,p in items])

def readStatFile():
    return load(open(statFile)) if path.exists(statFile) else {}

def writeStatFile(stats):
    statOut = open(statFile, 'wb')
    dump(stats, statOut)
    statOut.close()

def readCacheFile():
    return load(open(cacheLruFile)) if path.exists(cacheLruFile) else []

def writeCacheFile(lru):
    cacheOut = open(cacheLruFile, 'wb')
    dump(lru, cacheOut)
    cacheOut.close()

def refreshStats(items):
    stats = readStatFile()
    for i in items:
        stats[i] = (items[i], fitStats(i))
    writeStatFile(stats)

def getFitSize(fitTrackedData):
    return sum(int(s) for p,(h,s) in fitTrackedData.iteritems())

def getHeadRevision():
    return popen('git rev-parse HEAD'.split(), stdout=PIPE).communicate()[0].strip()

def filterBinaryFiles(files):
    binaryFiles = []

    p = popen('file -f -'.split(), stdout=PIPE, stdin=PIPE)
    fileTypes = p.communicate('\n'.join(files))[0].strip().split('\n')

    for f in fileTypes:
        sepIdx = f.find(':')
        filepath = f[:sepIdx]
        if f.find('text', sepIdx) < 0:
            binaryFiles.append(filepath)

    return binaryFiles
