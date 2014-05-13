from subprocess import Popen as popen, PIPE
from os import stat, path, chdir, getcwd
from gzip import open as gz
from json import load, dump
from sys import argv

# Get the repo root directory if inside one, otherwise exit
_p = popen('git rev-parse --show-toplevel'.split(), stdout=PIPE)
repoDir = _p.communicate()[0].strip()
_p.returncode == 0 or exit(_p.returncode)

# Get some more directory/file paths we're interested in
selfDir = path.dirname(path.realpath(__file__))
gitDir = popen('git rev-parse --git-dir'.split(), stdout=PIPE).communicate()[0].strip()
fitDir = path.join(gitDir,'fit')
fitFile = path.join(repoDir, '.fit')
fitFileCopy = path.join(fitDir, 'fitFileCopy')
cacheDir = path.join(fitDir, 'objects')
syncDir = path.join(cacheDir, 'tosync')
statFile = path.join(fitDir, 'stat')

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

def _fitStats(filename):
    stats = stat(filename)
    return stats.st_size, stats.st_mtime, stats.st_ctime, stats.st_ino

# The fit file is gzipped Python-pickled dictionary of this form:
#   {filename --> hash,size}
#
def readFitFile(fileToRead=fitFile):
    return load(gz(fitFile)) if path.exists(fitFile) else {}

def writeFitFile(fitData):
    fitFileOut = gz(fitFile, 'wb')
    dump(fitData, fitFileOut)
    fitFileOut.close()

    popen(['cp', fitFile, fitFileCopy]).wait()

# Returns a dictionary of modified items, mapping filename to (hash, filesize).
# Uses cached stats as the primary check to detect unchanged files, and only then
# does checksum comparisons if needed (just like git does)
def getModifiedItems(existingItems, fitTrackedData):
    # get current stats info of all existing items
    statsNew = {f: _fitStats(f) for f in existingItems}

    # The stat file is a Python-pickled dictionary of the following form:
    #   {filename --> (st_size, st_mtime, st_ctime, st_ino, checksum_hash)}
    #
    statsOld = load(open(statFile)) if path.exists(statFile) else {}

    # An item is "touched" if its cached stats don't match its new stats.
    # "Touched" is a necessary but not sufficient condition for an item to
    # be considered "modified". Modified items are those that are touched
    # AND whose checksums are different, so we do checksum comparisons next
    touchedItems = [f for f in statsNew if statsNew[f][0] > 0 and (f not in statsOld or tuple(statsOld[f][1]) != statsNew[f])]

    # Basically the next two lines make "touchedItems" a dictionary mapping filenames to their hash sums.
    # Hashes are re-computed ONLY for touched items. 
    p = popen('git hash-object --stdin-paths'.split(), stdin=PIPE, stdout=PIPE)
    touchedItems = dict(zip(touchedItems, p.communicate('\n'.join(touchedItems))[0].strip().split('\n')))

    # Check all existing items for modification by comparing their expected
    # hash sums (those stored in the .fit file) to their new, actual hash sums.
    # The new hash sums come from either the touched items determined above, or,
    # if not touched, from cached hash values computed from a previous run of this
    # same code
    modifiedItems = {}
    for i in existingItems:  # loop "existing" instead of touched items to update cached stats
                             # for everything, not just touched items
        trackedHash = fitTrackedData[i][0]
        size = statsNew[i][0]
        if i in touchedItems and touchedItems[i] != trackedHash:
            modifiedItems[i] = (touchedItems[i], size)
        elif size > 0 and i in statsOld and statsOld[i][0] != trackedHash:
            modifiedItems[i] = (statsOld[i][0], size)

    # Update our cached stats if necessary
    writeStatCache = False
    if len(touchedItems) > 0:
        writeStatCache = True
        for f in touchedItems:
            statsOld[f] = (touchedItems[f], statsNew[f])

    # By this point we should have new stats for all existing items, stored in
    # "statsOld". If we don't, it means some items have been deleted and can
    # be removed from the cached stats
    if len(existingItems) != len(statsOld):
        writeStatCache = True
        for f in statsOld.keys():
            if f not in existingItems:
                del statsOld[f]

    if writeStatCache:
        statOut = open(statFile, 'wb')
        dump(statsOld, statOut)
        statOut.close()

    return modifiedItems

# From all existing physical files under repo directory NOT tracked by
# git, get those that fit is being asked to track, as indicated by current
# state of set/unset "fit" attributes. These are the foundItems.
@gitDirOperation(repoDir)
def getTrackedItems():
    p = popen(('git ls-files -o').split(), stdout=PIPE)
    p = popen('git check-attr --stdin fit'.split(), stdin=p.stdout, stdout=PIPE)
    return {l[:-11] for l in p.stdout if l.endswith(' set\n')}

@gitDirOperation(repoDir)
def getChangedItems(fitTrackedData):

    # These are the items fit is currently tracking
    expectedItems = set(fitTrackedData)

    foundItems = getTrackedItems()

    # Use set difference and intersection to determine some info about changes
    # to the status of our items
    existingItems = expectedItems & foundItems
    newItems = foundItems - expectedItems
    missingItems = expectedItems - foundItems

    # An item could be in missingItems for one of two reasons: either it
    # has been deleted from the working directory, or it has been marked
    # to not be tracked by fit anymore. We separate out these two sets
    # of missing items:
    untrackedItems = {i for i in missingItems if path.exists(i)}
    removedItems = missingItems - untrackedItems

    # From the existing items, we're interested in only the modified ones
    modifiedItems = getModifiedItems(existingItems, fitTrackedData) if len(existingItems) else []
    
    return (modifiedItems, newItems, removedItems, untrackedItems)

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

@gitDirOperation(repoDir)
def getStagedOffenders():
    fitConflict = []
    binaryFiles = []

    staged = []
    p = popen('git diff --name-only --diff-filter=A --cached'.split(), stdout=PIPE)
    p = popen('git check-attr --stdin fit'.split(), stdin=p.stdout, stdout=PIPE)
    for l in p.stdout:
        filepath = l[:l.find(':')]
        if l.endswith(' set\n'):
            fitConflict.append(filepath)
        elif l.endswith(' unspecified\n'):
            staged.append(filepath)

    if len(staged) > 0:
        binaryFiles = filterBinaryFiles(staged)

    return fitConflict, binaryFiles

