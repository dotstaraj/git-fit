from fit import getStagedOffenders, getChangedItems, fitFile, writeFitFile
from fit import PIPE, popen, stat, path
from textwrap import fill as wrapline
from os import mkdir
from shutil import copyfile

def postCheckout(fitTrackedData):
    for filePath,(objHash, size) in fitTrackedData.iteritems():
        objPath = path.join(cacheDir, objHash[:2], objHash[2:])
        path.exists(objPath) and copyfile(objPath, filePath) or open(filePath, 'w').close()

def postCommit(fitTrackedData):
    for filePath,(objHash, size) in fitTrackedData.iteritems():
        objDir = path.join(cacheDir,objHash[:2])
        objPath = path.join(cacheDir, objDir, objHash[2:])
        path.exists(objDir) or mkdir(objDir)
        path.exists(objPath) or path.getsize(filePath) == 0 or copyfile(filePath, objPath)

# This msg string should be left exactly as it is in the multi-line string
infoMsg='''\
********** git-fit has aborted this commit **********
The commit was aborted due to the following items in the staging area:

<files-will-be-output-here>

F = explicitly included for git-fit through "fit" attribute
B = auto-detected binary file
L = auto-detected large text file (>100K)

This repository is configured to use git-fit. Any large and/or binary files that fit has \
not been told about will abort the commit.
********** git-fit has aborted this commit **********\
'''.split('\n')

def preCommit(fitTrackedData):
    offenders = getStagedOffenders()
    if any(len(l) > 0 for l in offenders):
        if __name__ == '__main__':
            conflict = [('F', i) for i in offenders[0]]
            binary = [('B', i) for i in offenders[1]]
            large = [('L', i) for i in offenders[2]]
            
            print '\n'.join([wrapline(l) for l in infoMsg[:3]])
            for c,f in sorted(conflict+binary+large, key=lambda i: i[1]):
                print '   ', c, f
            print '\n'.join([wrapline(l) for l in infoMsg[4:]])

        exit(1)

    added, missing, untracked, modified = getChangedItems()

    sizes = [s.st_size for s in [stat(f) for f in added]]
    p = popen('git hash-object --stdin-paths'.split(), stdin=PIPE, stdout=PIPE)
    added =  zip(added, zip(p.communicate('\n'.join(added))[0].strip().split('\n'), sizes))

    for i in missing:
        del fitTrackedData[i]
    for i in untracked:
        del fitTrackedData[i]
    fitTrackedData.update(modified)
    fitTrackedData.update(added)

    writeFitFile(fitTrackedData)
    popen('git add -f'.split()+[fitFile])

