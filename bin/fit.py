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
    return path.exists(fitFile) and load(gz(fitFile)) or {}

def writeFitFile(fitData):
    fitFileOut = gz(fitFile, 'wb')
    dump(fitData, fitFileOut)
    fitFileOut.close()

def getChangedItems():
    cwd = getcwd()
    chdir(repoDir)
    
    # Get the list of files that fit is already tracking through a previous check-in
    # fitFile is gzipped python-pickled dictionary of this form: {filename -> hash,size}
    fitTrackedData = readFitFile()
    trackedItems = set(fitTrackedData)

    # From those already being tracked, get those that we should continue to track (as
    # indicated by currently read "fit" attributes that are set/unset)
    expectedItems = set()
    if len(fitTrackedData) > 0:
        p = popen('git check-attr --stdin fit'.split(), stdin=PIPE, stdout=PIPE)
        p_stdout = p.communicate('\n'.join(fitTrackedData))[0].split('\n')
        expectedItems = set([l[:-10] for l in p_stdout if l.endswith(' set')])
    
    # From all existing physical files under repo directory, get those that fit should be
    # tracking (as indicated by currently read "fit" attributes that are set/unset)
    p = popen(('git ls-files -co').split(), stdout=PIPE)
    p = popen('git check-attr --stdin fit'.split(), stdin=p.stdout, stdout=PIPE)
    foundItems = set([l[:-11] for l in p.stdout if l.endswith(' set\n')])

    
    # Use set difference and intersection to determine these four categories of changes
    addedItems = foundItems - trackedItems
    untrackedItems = trackedItems - expectedItems
    missingItems = trackedItems - (untrackedItems | foundItems)
    existingItems = trackedItems & foundItems

    # From the existing items, we're interested in only the modified ones
    # Use cached stats as the primary check to detect unchanged files, and only then do
    # checksum comparisons if needed (just like git does)
    modifiedItems = []
    if len(existingItems) > 0:
        fitStatNew = [(f,stat(f)) for f in existingItems]
        fitStatNew = dict([(f,(s.st_size, s.st_mtime, s.st_ctime, s.st_ino)) for f,s in fitStatNew])
        fitStatOld = path.exists(statFile) and load(open(statFile, 'rb')) or {}
        touchedItems = [f for f in fitStatNew if fitStatNew[f][0] > 0 and (f not in fitStatOld or fitStatOld[f][1] != fitStatNew[f])]
        p = popen('git hash-object --stdin-paths'.split(), stdin=PIPE, stdout=PIPE)
        touchedItems = dict(zip(touchedItems, p.communicate('\n'.join(touchedItems))[0].strip().split('\n')))
        modifiedItems = {}
        for i in existingItems:
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
        if len(existingItems) != len(fitStatOld):
            writeStatCache = True
            for f in fitStatOld.keys():
                if f not in existingItems:
                    del fitStatOld[f]

        if writeStatCache:
            statOut = open(statFile, 'wb')
            dump(fitStatOld, statOut)
            statOut.close()
    
    chdir(cwd)
    return (addedItems, missingItems, untrackedItems, modifiedItems, fitTrackedData)


def getStagedOffenders():
    cwd = getcwd()
    chdir(repoDir)

    fitConflict = []
    binaryFiles = []
    largeTextFiles = []

    fitStaged = []
    p = popen('git diff --name-only --diff-filter=A --cached'.split(), stdout=PIPE)
    p = popen('git check-attr --stdin fit'.split(), stdin=p.stdout, stdout=PIPE)
    for l in p.stdout:
        filepath = l[:l.find(':')]
        if l.endswith(' set\n'):
            fitConflict.append(filepath)
        elif l.endswith(' unspecified\n'):
            fitStaged.append(filepath)

    if len(fitStaged) > 0:
        p = popen('file -f -'.split(), stdout=PIPE, stdin=PIPE)
        fileTypes = p.communicate('\n'.join(fitStaged))[0].strip().split('\n')

        for f in fileTypes:
            sepIdx = f.find(':')
            filepath = f[:sepIdx]
            if f.find('text', sepIdx) < 0:
                binaryFiles.append(filepath)
            elif path.getsize(filepath) > 102400:
                largeTextFiles.append(filepath)

    chdir(cwd)
    return (fitConflict, binaryFiles, largeTextFiles)

