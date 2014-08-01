from . import gitDirOperation, repoDir, savesDir, commitsDir
from . import readFitFileForRevision, getHeadRevision
from changes import getStagedOffenders, saveItems, restoreItems
from merge import getMergedFit
from subprocess import PIPE, Popen as popen
from textwrap import fill as wrapline
from os import remove
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


@gitDirOperation(repoDir)
def postCheckout(fitTrackedData, oldRev):
    mergeOld = readFitFileForRevision(oldRev)
    mergeNew = fitTrackedData
    mergeWorking = dict(mergeOld)
    saveItems(mergeWorking, quiet=True)
    mergeWorking, conflicts, modified, added, removed = getMergedFit(mergeOld, mergeWorking, mergeNew)
    restoreItems(mergeWorking, modified, added, removed, quiet=True)

@gitDirOperation(repoDir)
def postCommit(fitTrackedData):
    fitFileHash = popen('git ls-tree HEAD .fit'.split(), stdout=PIPE).communicate()[0].strip().split()[2]
    savesFile = joinpath(savesDir, fitFileHash)
    if exists(savesFile):
        move(savesFile, joinpath(commitsDir, getHeadRevision()))

    # 1 notify warning if un-committed changes exist
    # 2 Notify warning to unignore items that were untracked in the commit

@gitDirOperation(repoDir)
def preCommit(fitTrackedData):
    offenders = getStagedOffenders()

    if sum(len(l) for l in offenders) == 0:
        exit()

    conflict = [('F ', i) for i in offenders[0]]
    binary = [('B ', i) for i in offenders[1]]
    
    print '\n'.join([wrapline(l) for l in infoMsg[:4]])
    for c,f in sorted(conflict+binary, key=lambda i: i[1]):
        print '   ', c, f
    print '\n'.join([wrapline(l) for l in infoMsg[5:]])

    exit(1)
