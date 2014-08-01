from fitlib import gitDirOperation, repoDir, fitFile, readFitFile, writeFitFile
from fitlib import mergeOtherFitFile, mergeMineFitFile, filterBinaryFiles
from os import path, remove
from shutil import move
from subprocess import Popen as popen, PIPE
import re

conflictMsg = '''
************ git-fit found conflicts during the merge ************
Either a merge, rebase, or other merge-based git operation caused
conflicts in fit. Fit has already merged in the non-conflicting
changes. However, the conflicts need to be manually resolved
before git-fit can resume usual operation. Open the .fit file in a
text editor for instructions on how to proceed. A commit will not
be possible until all conflicts have been resolved as instructed
in the .fit file and git-fit save is run without any arguments.
************ git-fit found conflicts during the merge ************
'''

conflictIntructions = '''\
# Conflict Resolution Form (DO NOT remove this line & make ONLY the changes described below)
# ==========================
# Each row below indicates an item conflict and consists of the following three columns:
#
#      <SELECTION_ENTRY_BOX>  <"MINE"_CHANGE_SYMBOL><"OTHER"_CHANGE_SYMBOL>  <ITEM_PATH>
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
    mergedFit, conflicts, modified, added, removed = getMergedFit(readFitFile(common), readFitFile(mine), readFitFile(other))

    if not conflicts:
        writeFitFile(mergedFit, mine)
        exit(0)

    writeFitFile(mergedFit, mergeMineFitFile)
    move(other, mergeOtherFitFile)
    prepareResolutionForm(conflicts)
    print conflictMsg
    exit(1)

def fitDiff(old, new):
    oldItems = set(old)
    newItems = set(new)

    modified = {i for i in (oldItems & newItems) if old[i] != new[i]}
    added = newItems - oldItems
    removed = oldItems - newItems

    return modified,added,removed

@gitDirOperation(repoDir)
def prepareResolutionForm(conflicts):
    lines =  [('++', c) for c in conflicts['add']]
    lines += [('**', c) for c in conflicts['mod']]
    lines += [('*-', c) for c in conflicts['modRem']]
    lines += [('-*', c) for c in conflicts['remMod']]

    lines.sort(key=lambda a: a[1])

    fileout = open(fitFile, 'w')
    fileout.write('\n'.join(conflictIntructions))
    fileout.write('\n'.join(["[]  %s  %s"%l for l in lines]))
    fileout.close()

@gitDirOperation(repoDir)
def resolve(fitTrackedData):
    removed = []
    added = []
    working = []

    other = readFitFile(mergeOtherFitFile)

    for n,l in enumerate(open(fitFile).readlines()):
        if l.startswith('#'):
            continue
        l = l.strip()
        if l == '':
            continue

        match = _conflictLine_re.match(l)
        if not match:
            print 'merge error: Line %d in the .fit file has an error. Cannot continue...'%(n + 1)
            return

        resolution, change, item = match.groups()
        if resolution == '':
            print 'merge error: No selection has been made for item on line %d in the .fit file. Cannot continue...'%(n + 1)
            return

        resolution = resolution.upper()
        change = change[1]

        if resolution == 'O':
            if change == '-':
                removed.append(item)
            else:
                added.append((item, other[item]))
        elif resolution == 'W':
            working.append(item)

    for i in removed:
        del fitTrackedData[i]
    fitTrackedData.update(added)

    cleanupMergeArtifacts()

    return len(added)+len(removed) > 0, working

def cleanupMergeArtifacts():
    if path.exists(mergeMineFitFile):
        move(mergeMineFitFile, fitFile)
    if path.exists(mergeOtherFitFile):
        remove(mergeOtherFitFile)

@gitDirOperation(repoDir)
def isMergeInProgress():
    fitFileStatus = popen('git status --porcelain .fit'.split(), stdout=PIPE).communicate()[0].strip()
    if fitFileStatus:
        fitFileStatus = fitFileStatus.split()[0]
    merging = 'U' in fitFileStatus or fitFileStatus in ('AA', 'DD')
    merging &= path.exists(fitFile) and fitFile not in filterBinaryFiles([fitFile]) and open(fitFile).next().strip() == conflictIntructions[0]

    if not merging:
        cleanupMergeArtifacts()

    return merging

def getMergedFit(common, mine, other):
    mineMod,mineAdd,mineRem = fitDiff(common, mine)
    otherMod,otherAdd,otherRem = fitDiff(common, other)

    addCon = {i for i in (mineAdd & otherAdd) if mine[i] != other[i]}
    modCon = {i for i in (mineMod & otherMod) if mine[i] != other[i]}
    modRemCon = mineMod & otherRem
    remModCon = mineRem & otherMod

    allCon = addCon | modCon | modRemCon | remModCon
    
    modified = otherMod - allCon
    added = otherAdd - allCon
    removed = (otherRem - mineRem) - allCon

    for i in modified | added:
        mine[i] = other[i]
    for i in removed:
        del mine[i]

    conflicts = None
    
    if len(allCon) > 0:
        conflicts = {
            'add': addCon,
            'mod': modCon,
            'modRem': modRemCon,
            'remMod': remModCon
        }

    return mine, modified, added, removed, conflicts
