#!/usr/bin/env python2.7

from fit import repoDir
from os.path import dirname, realpath, relpath

class FitNode:
    def __init__(self, path, nodes):
        self.parentPath = path
        self.children = nodes

# Returns a tree constructred from given list of paths
def getPathTree(paths):
    tree = {}
    for p in paths:
        parts = p.split('/')
        node = tree.setdefault(parts[0], {})
        for c in parts[1:]:
            node = node.setdefault(c, {})
    return tree

def addFitItemsToList(path, node, items):
    # keep a queue of nodes, adding all leafs to fitPaths
    nodes = [FitNode(path, node)]
    while len(nodes) > 0:
        node = nodes.pop(0)
        if len(node.children) == 0:
            items.append(node.parentPath)
        else:
            nodes.extend([FitNode(node.parentPath + '/' + k, v) for k,v in node.children.iteritems()])            

def getValidFitPaths(given, available):
    if not given:
        return None

    # Normalize the user-entered paths into canonical paths
    # relative to repo root
    given = {relpath(realpath(p), repoDir) for p in given}

    if '.' in given:
        return available        

    fitPathTree = getPathTree(available)

    # Generate list of individual fit items under user-given paths
    validPaths = []
    for p in given:
        if p.startswith('../'):
            print '(...skipping path not under repo: %s)'%p
            continue

        # Determine if normalized user-given path is one that
        # is tracked by fit by traversing fitPathTree
        isFit = True
        node = fitPathTree
        parts = p.split('/')
        for part in parts:
            node = node.get(part)
            if node == None:
                isFit = False
                break

        if not isFit:
            print '(...path not currently tracked by fit: %s)'%p
            continue

        addFitItemsToList(p, node, validPaths)

    return validPaths

