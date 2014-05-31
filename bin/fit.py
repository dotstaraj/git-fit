from subprocess import Popen as popen, PIPE
from os import stat, path, chdir, getcwd
from gzip import open as gz
from json import load, dump

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
conflictFile = path.join(repoDir, 'FIT_MERGE')
theirFitFile = path.join(fitDir, 'merge-their')
firstTimeFile = path.join(fitDir, 'first-time')
savedFile = path.join(fitDir, 'save')

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

# The fit file is gzipped Python-pickled dictionary of this form:
#   {filename --> hash,size}
#
def readFitFile(filePath=fitFile):
    return load(gz(filePath)) if path.exists(filePath) and path.getsize(filePath) > 0 else {}

def writeFitFile(fitData, filePath=fitFile):
    fitFileOut = gz(filePath, 'wb')
    dump(fitData, fitFileOut)
    fitFileOut.close()

def readStatFile():
    return load(open(statFile)) if path.exists(statFile) else {}

def writeStatFile(stats):
    statOut = open(statFile, 'wb')
    dump(stats, statOut)
    statOut.close()

def refreshStats(items):
    stats = readStatFile()
    for i in items:
        stats[i] = (items[i], fitStats(i))
    writeStatFile(stats)
