from . import gitDirOperation, repoDir, savesDir, getCommitFile
from . import getFitManifestChanges, dirtyGitItemsFilter, readFitFile
from changes import getStagedOffenders, saveItems, restoreItems, restoreMissingMessage
from merge import getMergedFit
from subprocess import PIPE, Popen as popen
from textwrap import fill as wrapline
from os import remove, mkdir, devnull
from os.path import join as joinpath, exists
from shutil import move

# This msg string should be left exactly as it is in the multi-line string
infoMsg='''
********** git-fit has aborted this commit **********
The commit was aborted because the following items are staged in git:

<files-will-be-output-here>

F = explicitly included for git-fit through "fit" attribute
B = auto-detected binary file

This repository is configured to use git-fit. Any binary files that fit \
has not been told about will abort the commit.
********** git-fit has aborted this commit **********
'''.split('\n')

def _getWorkingTreeStateForLastHead(fitData, fitManifestChanges):
    if not fitManifestChanges:
        return fitData

    if '.fit' in fitManifestChanges:
        fitManifestChanges.remove('.fit')

    if fitManifestChanges:
        popen('git checkout HEAD@{1}'.split() + list(fitManifestChanges), stdout=open(devnull, 'wb'), stderr=open(devnull, 'wb')).wait()
    try:
        saveItems(fitData, quiet=True)
    except:
        raise
    finally:
        if fitManifestChanges:
            popen('git checkout HEAD'.split() + list(fitManifestChanges), stdout=open(devnull, 'wb'), stderr=open(devnull, 'wb')).wait()
    return fitData

@gitDirOperation(repoDir)
def postCheckout():
    fitfileChanged = False
    fitManifestChanges = set(getFitManifestChanges())
    fitManifestChanges = fitManifestChanges - set(dirtyGitItemsFilter(fitManifestChanges))

    if len(fitManifestChanges) == 0:
        return

    mergeOld = readFitFile(rev='HEAD@{1}')
    mergeNew = readFitFile()
    mergeWorking = _getWorkingTreeStateForLastHead(dict(mergeOld), fitManifestChanges)
    mergeWorking, modified, added, removed, conflicts = getMergedFit(mergeOld, mergeWorking, mergeNew)

    # important, it might seem confusing and wrong, but the order of the 
    # "remove" and "added" arguments below is actually right, so do not
    # swap them
    missing = restoreItems(mergeNew, modified, removed, added, quiet=True)
    if missing > 0:
        print restoreMissingMessage%missing

@gitDirOperation(repoDir)
def postCommit():
    fitFileHash = popen('git ls-tree HEAD .fit'.split(), stdout=PIPE).communicate()[0].strip()
    if not fitFileHash:
        return

    fitFileHash = fitFileHash.split()[2]
    savesFile = joinpath(savesDir, fitFileHash)
    if exists(savesFile):
        move(savesFile, getCommitFile())

    # 1 notify warning if un-committed changes exist
    # 2 Notify warning to unignore items that were untracked in the commit

@gitDirOperation(repoDir)
def preCommit():
    offenders = getStagedOffenders()

    if sum(len(l) for l in offenders) == 0:
        exit(0)

    conflict = [('F ', i) for i in offenders[0]]
    binary = [('B ', i) for i in offenders[1]]
    
    print '\n'.join([wrapline(l) for l in infoMsg[:4]])
    for c,f in sorted(conflict+binary, key=lambda i: i[1]):
        print '   ', c, f
    print '\n'.join([wrapline(l) for l in infoMsg[5:]])

    exit(1)
