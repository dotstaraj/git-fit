from . import gitDirOperation, repoDir, fitFile, readFitFile, writeFitFile
from . import mergeOtherFitFile, mergeMineFitFile, filterBinaryFiles, getFitFileStatus
import changes
from os import path, remove
from shutil import move
from subprocess import Popen as popen, PIPE
import re

conflictMsg = '''
************ git-fit found conflicts during the merge ************
Either a merge, rebase, or other merge-based git operation caused
conflicts in fit. Fit has already auto-merged in the
non-conflicting changes. However, there exist conflicts that need
to be manually resolved before git-fit can resume usual operation.

The .fit file has been replaced with a Conflict Resolution Form.
Open it in a text editor for quick instructions or run
'git-fit --merge-help' for more comprehensive instructions. A
commit will not be possible until the .fit file is fully resolved.
************ git-fit found conflicts during the merge ************
'''

crfHeader = '''\
# Conflict Resolution Form (DO NOT remove this line)
#
# ==> 1. Make your selections (M or T or W) below, either individually, or in batch.
# ==> 2. Run "git-fit save" (without any PATH arguments).
# ==> 3. Proceed with the git merge process as usual.
#
# Run 'git-fit --merge-help' for more details on how to make valid and proper selections.
==========================

'''.split('\n')

instructions = '''\
=================================================
 Conflict Resolution Form FORMAT
=================================================
During a merge, a fit-related conflict causes the .fit file to be replaced by a human-editable
Conflict Resolution Form (CRF). For each conflicted item, the CRF contains a row consisting of
the following three columns:

     <CHOICE>  <MINE><THEIRS>  <ITEM>

- CHOICE: entry box where you enter your choice of resolution for this conflict
- MINE:   symbol indicating how CURRENT version of item changed from the common ancestor
- THEIRS: symbol indicating how INCOMING version of item changed from the common ancestor
- ITEM:   path of the item for this conflict

Here is an example:

  []  **  foo.jar
  []  ++  bar.png
  []  *-  bin/runBaz
  []  -*  lib/libQux.so

Here, four conflicting fit changes resulted from a merge. Note that the four variations of
conflicts shown in this example are the ONLY variations possible: modified/modified,
added/added, modified/removed, and removed/modified.

=================================================
 How to MAKE SELECTIONS to resolve conflicts
=================================================
For each conflict, you need to decide whether to resolve it with "my" change or "their" change. A
third possibility is to accept neither change and use the working-tree status of the item instead.
This allows you to put an arbitrary version of the item in the working-tree and use that as the
resolution. You can also use the working-tree resolution to mark the item for removal, by removing
it from the working tree. At any time during the merge, you may run git-fit to check the status
all conflicts and resolutions.

There are TWO basic ways to make these selections and both may be used together in the same CRF.
EACH and EVERY item in the list must be given a choice of resolution, using any combination of
these two methods:

1. Individual selections:

    Enter a SINGLE letter inside the [] entry box for a given conflict.

     - Enter [M] to select MY change.
     - Enter [T] to select THEIR change.
     - Enter [W] to select WORKING tree version of the item.

2. Batch selections:

    The conflict rows are alphanumerically sorted by the item path, making it easier to group
    consecutive conflict lines and apply the same resolution choice to them in batch. To make
    such a batch selection, surround the group of consecutive lines with open- and close-
    parentheses and enter a resolution choice for the FIRST item in the batch. In this case, the
    rest of the items in the group are implicitly given the same choice as the first item. It is
    also possible to nest batch selections. However, for ANY item, if a choice is explicitly given
    in its entry box, then that is how that item will be resolved, regardless of whether it is in
    a batch selection or not. The columns are whitespace-insensitive (i.e. the last line in the
    example below is valid), so it's safe to pad them as much or as little as desired.

        [W]  **  foo.jar
       ([T]  ++  bar.png
        [W]  *-  bin/runBaz
       ([M]  *-  bin/runCorge
        [])  -*  lib/libQux.so
        [])**lib/libQuux.so

    In this example, the item foo.jar has been individually selected with [W]. The bar.png and
    lib/libQuux.so items are batch-selected with bar.png's [T]. The choice for bin/runBaz
    explicitly overrides bar.png's batch-selection of [T] with [W]. Finally, the nested batch
    started by bin/runCorge applies the [M] choice to lib/libQux.so as well.

=================================================
 REBASE versus MERGE
=================================================
REMEMBER:
If these conflicts resulted from a git REBASE operation, then "mine" and "theirs" refer to the
OPPOSITE versions than what may intuitively make sense from your point of view. In other words,
for rebase, "mine" refers to the version that you'd be bringing INTO your current branch. And, 
likewise, "theirs" actually refers to YOUR version that's already in the current branch itself.
'''

_conflictLine_re = re.compile('\s*([(]?)\s*\[([MOW]?)\]\s*([)]?)\s*(\*\*|\+\+|\*-|-\*)\s*(.+)\s*$')

def mergeDriver(common, mine, other):
    mergedFit, modified, added, removed, conflicts = getMergedFit(readFitFile(common), readFitFile(mine), readFitFile(other))

    if not conflicts:
        writeFitFile(mergedFit, mine)
        exit(0)

    writeFitFile(mergedFit, mergeMineFitFile)
    move(other, mergeOtherFitFile)
    prepareResolutionForm(conflicts, mine)
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
def prepareResolutionForm(conflicts, filePath):
    lines =  [('++', c) for c in conflicts['add']]
    lines += [('**', c) for c in conflicts['mod']]
    lines += [('*-', c) for c in conflicts['modRem']]
    lines += [('-*', c) for c in conflicts['remMod']]

    lines.sort(key=lambda a: a[1])

    fileout = open(filePath, 'w')
    fileout.write('\n'.join(crfHeader))
    fileout.write('\n'.join(["[]  %s  %s"%l for l in lines]))
    fileout.close()

@gitDirOperation(repoDir)
def resolve():
    resolutions = getResolutions()
    if resolutions == None:
        return False

    mergedFitData, mine, theirs, working, unresolved = resolutions
    if len(unresolved) > 0:
        print 'You are in the middle of a merge and the following fit items are yet unresolved:'
        for u in unresolved:
            print 'Line %s: %s'%u
        return False

    if not changes.save(mine, paths=working, quiet=True):
        return False
        
    cleanupMergeArtifacts()
    return True

@gitDirOperation(repoDir)
def getResolutions():
    mineFitData = readFitFile(mergeMineFitFile)
    otherFitData = readFitFile(mergeOtherFitFile)

    mine = []
    theirs = []
    working = []
    unresolved = []

    stack = []
    batchResolution = ''

    for n,l in enumerate(open(fitFile).readlines()):
        if l.startswith('#'):
            continue
        l = l.strip()
        if l == '':
            continue

        match = _conflictLine_re.match(l)
        if not match:
            print 'merge error: Line %d in the .fit file has an error. Cannot continue...'%(n + 1)
            return None

        batchOpen, resolution, batchClose, change, item = match.groups()
        resolution = resolution.upper()

        if batchOpen:
            stack.append(resolution)
            batchResolution = resolution

        if batchClose:
            if len(stack) == 0:
                print 'merge error: Line %d in the .fit file has an unmatched close parenthesis. Cannot continue...'%(n + 1)
                return None
            stack.pop()
            batchResolution = '' if len(stack) == 0 else stack[-1]

        resolution = resolution or batchResolution
        
        if resolution == 'T':
            if change[1] == '-':
                del mineFitData[item]
            else:
                mineFitData[item] = otherFitData[item]
            theirs.append(item)
        elif resolution == 'M':
            mine.append(item)
        elif resolution == 'W':
            working.append(item)
        else:
            unresolved.append((item, n+1))

    if len(stack) > 0:
        print 'merge error: Line %d in the .fit file has an unmatched open parenthesis. Cannot continue...'%(n + 1)
        return None

    return mergedFitData, mine, theirs, working, unresolved

@gitDirOperation(repoDir)
def isMergeInProgress():
    fitFileStatus = getFitFileStatus()
    if fitFileStatus:
        fitFileStatus = fitFileStatus.split()[0]

    merging = (
        ('U' in fitFileStatus or fitFileStatus in ('AA', 'DD'))
        and path.exists(mergeMineFitFile) and path.exists(mergeOtherFitFile)
        and path.exists(fitFile) and fitFile not in filterBinaryFiles([fitFile])
        and open(fitFile).next().strip() == crfHeader[0]
    )

    if not merging:
        cleanupMergeArtifacts()

    return merging

def cleanupMergeArtifacts():
    if path.exists(mergeMineFitFile):
        remove(mergeMineFitFile)
    if path.exists(mergeOtherFitFile):
        remove(mergeOtherFitFile)

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
