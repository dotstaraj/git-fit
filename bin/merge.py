from fit import gitDirOperation, repoDir, readFitFile, writeFitFile
from fit import mergeOtherFitFile, mergeConflictFile
from os import path, remove
from shutil import move
from subprocess import Popen as popen, PIPE
import re

conflictMsg = '''
************ git-fit found conflicts during the merge ************
Either a merge, rebase, or other merge-based operation caused
conflicts in fit-tracked items. Fit has already merged in the non-
conflicting changes. However, the conflicts need to be manually
resolved. A "FIT_MERGE" file has been created in the root of your
project directory to facilitate this process, so take a look at
that file for instructions on how to proceed. A commit will not be
possible until all conflicts have been resolved as instructed in
this "FIT_MERGE" file.
************ git-fit found conflicts during the merge ************
'''

conflictIntructions = '''\
# Each row below indicates an item conflict and consists of the following three columns:
#
#      <SELECTION_ENTRY_BOX>  <"MINE"-CHANGE><"OTHER"-CHANGE>  <ITEM>
#
# Example:
# (symbol meanings: "*" = modified, "+" = added, "-" = removed)
#
#   []  *-  someDirectory/file1
#   []  ++  directory2/file2
#
# Make your selections inside the [] boxes in the first column for EACH and EVERY row
# by entering only a SINGLE letter inside []:
# 
#  - Enter [M] to select MINE change. This is equivalent to deleting the entire row.
#  - Enter [O] to select OTHER change.
#  - Enter [W] to select WORKING tree version of the item.
#      If the item does not exist in the working tree, the resolution amounts to REMOVING the item
#      from fit. When choosing [W], git-fit may be run to verify an item's status if needed.
#
# REMEMBER:
# If these conflicts resulted from a git REBASE operation, then "mine" and "other" refer to the
# OPPOSITE versions than what may intuitively make sense from your point of view. In other words,
# for rebase, "mine" refers to the version that you'd be bringing INTO your current branch. And, 
# likewise, "other" actually refers to YOUR version that's already in the current branch itself.

# ==> 1. Make your selections (M or O or W) below.
# ==> 2. Run "git-fit save".
# ==> 3. Proceed with the merge process in git as normal.

'''.split('\n')

_conflictLine_re = re.compile('\s*\[([MOW]?)\]\s+(\*\*|\+\+|\*-|-\*)\s+(.+)\s*$')

def mergeDriver(common, mine, other):
    merged, conflicts = getMergedFit(readFitFile(common), readFitFile(mine), readFitFile(other))

    if not conflicts:
        writeFitFile(merged, mine)
        exit(0)

    writeFitFile(merged)
    writemergeConflictFile(conflicts)
    move(other, mergeOtherFitFile)
    print conflictMsg
    exit(1)

def fitDiff(old, new):
    oldItems = set(old)
    newItems = set(new)

    added = newItems - oldItems
    removed = oldItems - newItems
    modified = {i for i in (oldItems & newItems) if old[i] != new[i]}

    return added,removed,modified

@gitDirOperation(repoDir)
def writemergeConflictFile(conflicts):
    lines =  [('++', c) for c in conflicts['add']]
    lines += [('**', c) for c in conflicts['mod']]
    lines += [('*-', c) for c in conflicts['modRem']]
    lines += [('-*', c) for c in conflicts['remMod']]

    lines.sort(key=lambda a: a[1])

    fileout = open(mergeConflictFile, 'w')
    fileout.write('\n'.join(conflictIntructions))
    fileout.write('\n'.join(["[]  %s  %s"%l for l in lines]))
    fileout.close()

@gitDirOperation(repoDir)
def resolve(fitTrackedData):
    removed = []
    added = []
    working = []
    changes = False

    other = readFitFile(mergeOtherFitFile)

    for n,l in enumerate(open(mergeConflictFile).readlines()):
        if l.startswith('#'):
            continue
        l = l.strip()
        if l == '':
            continue

        match = _conflictLine_re.match(l)
        if not match:
            print 'error: Line %d in the FIT_MERGE file has an error. Cannot continue...'%(n + 1)
            return

        resolution, change, item = match.groups()
        if resolution == '':
            print 'error: No selection has been made for item on line %d in the FIT_MERGE file. Cannot continue...'%(n + 1)
            return

        resolution = resolution.upper()
        change = change[1]

        if resolution == 'O':
            if change == '-':
                removed.append(item)
            else:
                added.append((item, other[item]))
            changes = True
        elif resolution == 'W':
            working.append(item)

    for i in removed:
        del fitTrackedData[i]
    fitTrackedData.update(added)

    cleanupMergeArtifacts()

    print added[0]
    print fitTrackedData[added[0][0]]
    return changes, working

def cleanupMergeArtifacts():
    if path.exists(mergeConflictFile):
        remove(mergeConflictFile)
    if path.exists(mergeOtherFitFile):
        remove(mergeOtherFitFile)

@gitDirOperation(repoDir)
def isMergeInProgress():
    if not path.exists(mergeConflictFile):
        return False
    fitFileStatus = popen('git status --porcelain .fit'.split(), stdout=PIPE).communicate()[0].strip().split()[0]
    merging = 'U' in fitFileStatus or fitFileStatus in ('AA', 'DD')

    if not merging and path.exists(mergeConflictFile):
        cleanupMergeArtifacts()

    return merging

def getMergedFit(common, mine, other):
    mineAdd,mineRem,mineMod = fitDiff(common, mine)
    otherAdd,otherRem,otherMod = fitDiff(common, other)

    addCon = {i for i in (mineAdd & otherAdd) if mine[i] != other[i]}
    modCon = {i for i in (mineMod & otherMod) if mine[i] != other[i]}
    modRemCon = mineMod & otherRem
    remModCon = mineRem & otherMod

    allCon = addCon | modCon | modRemCon | remModCon
    
    for i in (otherAdd | otherMod) - allCon:
        mine[i] = other[i]
    for i in (otherRem - mineRem) - allCon:
        del mine[i]

    conflicts = None
    
    if len(allCon) > 0:
        conflicts = {
            'add': addCon,
            'mod': modCon,
            'modRem': modRemCon,
            'remMod': remModCon
        }

    return mine, conflicts
