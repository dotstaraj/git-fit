from subprocess import Popen as popen, PIPE
from os import stat, path, chdir, getcwd
from gzip import open as gz
from cPickle import load, dump
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
cacheDir = path.join(fitDir, 'objects')
statFile = path.join(fitDir, 'stat')

def readFitFile():
    return load(gz(fitFile)) if path.exists(fitFile) else {}

def writeFitFile(fitData):
    fitFileOut = gz(fitFile, 'wb')
    dump(fitData, fitFileOut)
    fitFileOut.close

# Returns a dictionary of modified items, mapping filename to (hash, filesize).
# Uses cached stats as the primary check to detect unchanged files, and only then
# does checksum comparisons if needed (just like git does)
def getModifiedItems(existingItems):
    # get current stats info of all existing items
    fitStatNew = [(f,stat(f)) for f in existingItems]
    fitStatNew = dict([(f,(s.st_size, s.st_mtime, s.st_ctime, s.st_ino)) for f,s in fitStatNew])

    # The stat file is a Python-pickled dictionary of the following form:
    #   {filename -> hash, stat_info}
    fitStatOld = load(open(statFile, 'rb')) if path.exists(statFile) else {}

    # An item is "touched" if its cached stats don't match its new stats.
    # That doesn't necessarily mean its contents have been modified, so we
    # check for modification next
    touchedItems = [f for f in fitStatNew if fitStatNew[f][0] > 0 and (f not in fitStatOld or fitStatOld[f][1] != fitStatNew[f])]

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
        size = fitStatNew[i][0]
        if i in touchedItems and touchedItems[i] != trackedHash:
            modifiedItems[i] = (touchedItems[i], size)
        elif size > 0 and i in fitStatOld and fitStatOld[i][0] != trackedHash:
            modifiedItems[i] = (fitStatOld[i][0], size)

    # Update our cached stats if necessary
    writeStatCache = False
    if len(touchedItems) > 0:
        writeStatCache = True
        for f in touchedItems:
            fitStatOld[f] = (touchedItems[f], fitStatNew[f])

    # By this point we should have new stats for all existing items, stored in
    # "fitStatOld". If we don't, it means some items have been deleted and can
    # be removed from the cached stats
    if len(existingItems) != len(fitStatOld):
        writeStatCache = True
        for f in fitStatOld.keys():
            if f not in existingItems:
                del fitStatOld[f]

    if writeStatCache:
        statOut = open(statFile, 'wb')
        dump(fitStatOld, statOut)
        statOut.close()

    return modifiedItems

def getChangedItems():
    cwd = getcwd()
    chdir(repoDir)
    
    # Get the list of files that fit is already tracking through a previous check-in.
    # The fit file is gzipped python-pickled dictionary of this form:
    #   {filename -> hash,size}
    fitTrackedData = readFitFile()
    itemsExpectedBefore = set(fitTrackedData)

    # From those already being tracked, get those that we should continue to track (as
    # indicated by currently read "fit" attributes that are set/unset)
    itemsExpectedNow = set()
    if len(itemsExpectedBefore) > 0:
        p = popen('git check-attr --stdin fit'.split(), stdin=PIPE, stdout=PIPE)
        p_stdout = p.communicate('\n'.join(itemsExpectedBefore))[0].split('\n')
        itemsExpectedNow = set([l[:-10] for l in p_stdout if l.endswith(' set')])
    
    # From all existing physical files under repo directory, get those that fit should be
    # tracking (as indicated by currently read "fit" attributes that are set/unset)
    p = popen(('git ls-files -co').split(), stdout=PIPE)
    p = popen('git check-attr --stdin fit'.split(), stdin=p.stdout, stdout=PIPE)
    itemsActual = set([l[:-11] for l in p.stdout if l.endswith(' set\n')])

    # Use set difference and intersection to determine these four categories of changes
    untrackedItems = itemsExpectedBefore - itemsExpectedNow
    addedItems = itemsActual - itemsExpectedNow
    removedItems = itemsExpectedNow - itemsActual
    existingItems = itemsExpectedNow & itemsActual

    # From the existing items, we're interested in only the modified ones
    modifiedItems = getModifiedItems(existingItems) if len(existingItems) else []
    
    chdir(cwd)
    return (addedItems, removedItems, modifiedItems, untrackedItems)


def getStagedOffenders():
    cwd = getcwd()
    chdir(repoDir)

    fitConflict = []
    binaryFiles = []
    largeTextFiles = []

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
        p = popen('file -f -'.split(), stdout=PIPE, stdin=PIPE)
        fileTypes = p.communicate('\n'.join(staged))[0].strip().split('\n')

        for f in fileTypes:
            sepIdx = f.find(':')
            filepath = f[:sepIdx]
            if f.find('text', sepIdx) < 0:
                binaryFiles.append(filepath)
            elif path.getsize(filepath) > 102400:
                largeTextFiles.append(filepath)

    chdir(cwd)
    return (fitConflict, binaryFiles, largeTextFiles)

