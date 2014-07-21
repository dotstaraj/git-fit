from . import lruFile, objectsDir
from json import load,dump
from os import remove, makedirs
from os.path import exists
from shutil import copyfile
from sys import stdout

def _cacheIO(decoratee):
    def decorator(*a, **k):
        loaded = False

        if k.get('data') == None:
            loaded = True
            k['data'] = load(open(lruFile)) if exists(lruFile) else {'lru':{'size':0,'count':0,'items':{}},'map':{'size':0,'items':{}}}

        updated, r = decoratee(*a, **k)

        if loaded and updated:
            f = open(lruFile, 'w')
            dump(k['data'], f)
            f.close()

        return r
    return decorator

def _unpack(data):
    l = data['lru']
    m = data['map']
    return l['size'], l['count'], l['items'], m['size'], m['items']

def _pack(data, ls, lc, ms):
    l = data['lru']
    m = data['map']
    l['size'], l['count'], m['size'] = ls, lc, ms

@_cacheIO
def insert(keys, inLru=False, progressMsg=None, data=None):
    ls, lc, li, ms, mi = _unpack(data)

    inserted = {}
    inOther = []
    if inLru:
        for k,(s,f) in keys.iteritems():
            lc += 1
            if k in mi:
                inOther.append(k)
                del mi[k]
                ms -= s
                ls += s
            elif k not in li:
                inserted[k] = f
                ls += s
            li[k] = (s,lc)
    else:
        for k,(s,f) in keys.iteritems():
            if k in li:
                inOther.append(k)
                lc += 1
                li[k] = (s,lc)
            elif k not in mi:
                inserted[k] = f
                mi[k] = (s, False)
                ms += s

    n = len(inserted)
    for i,(k,f) in enumerate(inserted.iteritems()):
        dstDir = '%s/%s'%(objectsDir, k[:2])
        dst = '%s/%s'%(dstDir, k[2:])
        exists(dstDir) or makedirs(dstDir)
        copyfile(f, dst)
        if progressMsg:
            print '\r%s...%6.2f%%  %s/%s           '%(progressMsg,(i+1)*100./n, i+1, n),
            stdout.flush()

    if progressMsg and len(inserted) > 0:
        print

    _pack(data, ls, lc, ms)
    return True, (inserted, inOther, ls, ms)

@_cacheIO
def commit(keys, data=None):
    ls, lc, li, ms, mi = _unpack(data)

    commited = {}
    for k in keys:
        if k in mi and not mi[k][1]:
            s = mi[k][0]
            mi[k] = (s, True)
            commited[k] = s

    _pack(data, ls, lc, ms)
    return len(commited) > 0, commited

@_cacheIO
def enque(keys, data=None):
    ls, lc, li, ms, mi = _unpack(data)

    enqued = {}
    fromMap = {}
    for k in keys:
        val = None
        if k in li:
            val = li[k][0]
        elif k in mi:
            val = mi.pop(k)
            fromMap[k] = val
            val = val[0]
            ms -= val
            ls += val

        if val:
            enqued[k] = val
            lc += 1
            li[k] = (val, lc)

    _pack(data, ls, lc, ms)
    return len(enqued) > 0, (enqued, fromMap)

@_cacheIO
def find(keys, inMap=False, update=True, data=None):
    ls, lc, li, ms, mi = _unpack(data)
    if inMap:
        return False, {k:'%s/%s/%s'%(objectsDir, k[:2], k[2:]) for k in keys if k in mi}

    inLru = False
    found = {}
    for k in keys:
        if k in li:
            inLru = True
            lc += 1
            val = li[k][0]
            li[k] = (val, lc)
            found[k] = '%s/%s/%s'%(objectsDir, k[:2], k[2:])
        elif k in mi:
            found[k] = '%s/%s/%s'%(objectsDir, k[:2], k[2:])

    _pack(data, ls, lc, ms)
    return inLru and update, found

@_cacheIO
def delete(keys, commits=False, data=None):
    ls, lc, li, ms, mi = _unpack(data)
    deleted = {}
    for k in keys:
        if k in mi:
            s,c = mi.pop(k)
            if commits == c:
                deleted[k] = s
                ms -= s
                remove('%s/%s/%s'%(objectsDir, k[:2], k[2:]))

    _pack(data, ls, lc, ms)
    return len(deleted) > 0, (deleted, ls, ms)

@_cacheIO
def prune(size, data=None):
    ls, lc, li, ms, mi = _unpack(data)
    
    i = 0
    items = sorted(li.iteritems(), key=lambda (i,(j,k)): k)
    while ls > size and i < len(items):
        k, (s, c) = items[i]
        remove('%s/%s/%s'%(objectsDir, k[:2], k[2:]))
        ls -= s
        i += 1

    for k,(s,c) in items[:i]:
        del li[k]

    lc = 0
    for k,(s,c) in items[i:]:
        lc += 1
        li[k] = (s,lc)

    _pack(data, ls, lc, ms)
    return True,ls

@_cacheIO
def size(data=None):
    return False, (data['lru']['size'], data['map']['size'])

@_cacheIO
def getCommittedObjects(data=None):
    return False, {h for h,(s,c) in data['map']['items'].iteritems() if c}
