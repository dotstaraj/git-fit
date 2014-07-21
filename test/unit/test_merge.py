
import unittest

from fitlib import merge
from uuid import uuid4 as uid

def getRandomDict(numItems = 1):
    return {u.hex: u.int for u in [uid() for i in range(numItems)]}

def getStandardDict(numItems = 1):
    return {chr(ord('a')+i):i+1 for i in range(numItems)}

class TestFitDiff(unittest.TestCase):
    def setUp(self):
        self.longMessage = True

    def diff(self, old, new, expected):
        actual = merge.fitDiff(old, new)

        self.assertEqual(expected[0], actual[0], '\n\nerror: "modified" not as expected')
        self.assertEqual(expected[1], actual[1], '\n\nerror: "added" not as expected')
        self.assertEqual(expected[2], actual[2], '\n\nerror: "removed" not as expected')

    def testAllEmpty(self):
        old, new = {}, {}
        expected = set(), set(), set()
        self.diff(old, new, expected)

    def testOldEmpty(self):
        old, new = {}, getRandomDict()
        expected = set(), set(new), set()
        self.diff(old, new, expected)

    def testNewEmpty(self):
        old, new = getRandomDict(), {}
        expected = set(), set(), set(old)
        self.diff(old, new, expected)

    def testExaclySame(self):
        old = getRandomDict(5)
        new = dict(old)
        expected = set(), set(), set()
        self.diff(old, new, expected)

    def testSomeAdded(self):
        old = getRandomDict(2)
        new = getRandomDict(2)
        new.update(old)
        expected = set(), set(new)-set(old), set()
        self.diff(old, new, expected)

    def testSomeRemoved(self):
        old = getRandomDict(2)
        new = getRandomDict(2)
        old.update(new)
        expected = set(), set(), set(old)-set(new)
        self.diff(old, new, expected)

    def testSomeModified(self):
        old = getRandomDict(4)
        new = dict(old)

        modified = old.keys()[:2]
        for k in modified:
            new[k] = uid().int

        expected = set(modified), set(), set()
        self.diff(old, new, expected)

    def testMixedChanges(self):
        modified = {'a':1, 'b':2}
        added = {'c':3, 'd':4}
        removed = {'e':5, 'f':6}

        old = dict(removed)
        new = dict(added)
        old.update(modified)
        new.update({u:i+1 for u,i in modified.iteritems()})

        expected = set(modified), set(added), set(removed)
        self.diff(old, new, expected)

class TestGetMergedFit(unittest.TestCase):
    def setUp(self):
        self.longMessage = True

    def merge(self, common, mine, other, expected):
        actual = merge.getMergedFit(common, mine, other)

        self.assertEqual(expected[0], actual[0], '\n\nerror: "merged" not as expected')
        self.assertEqual(expected[1], actual[1], '\n\nerror: "modified" not as expected')
        self.assertEqual(expected[2], actual[2], '\n\nerror: "added" not as expected')
        self.assertEqual(expected[3], actual[3], '\n\nerror: "removed" not as expected')
        self.assertEqual(expected[4]['add'], actual[4]['add'], '\n\nerror: "addConflicts" not as expected')
        self.assertEqual(expected[4]['mod'], actual[4]['mod'], '\n\nerror: "modConflicts" not as expected')
        self.assertEqual(expected[4]['modRem'], actual[4]['modRem'], '\n\nerror: "modRemConflicts" not as expected')
        self.assertEqual(expected[4]['remMod'], actual[4]['remMod'], '\n\nerror: "remModConflicts" not as expected')

    def testSomeOfEach(self):
        #{"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6, "g": 7, "h": 8, "i": 9, "j": 10, "k": 11, "l": 12, "m": 13, "n": 14}
        common = getStandardDict(10)
        mine =  {'a': 1, 'b': 1, 'k': 11, 'd': 3, 'e': 5, 'l': 12, 'g': 7, 'h': 7, 'n': 13, 'i': 8}
        other = {'a': 1, 'b': 1, 'k': 11, 'd': 4, 'e': 4, 'm': 13, 'f': 6, 'h': 9, 'n': 15, 'j': 9}
        expected = (
            {'a': 1, 'b': 1, 'k': 11, 'd': 3, 'e': 4, 'l': 12, 'm': 13, 'h': 7, 'n': 13, 'i': 8},
            set(['e']),
            set(['m']),
            set(['g']),
            {
                'add': set(['n']),
                'mod': set(['h']),
                'modRem': set(['i']),
                'remMod': set(['j']),
            }
        )

        self.merge(common, mine, other, expected)

'''
class TestResolve(unittest.TestCase):
    def setUp(self):
        self.longMessage = True

    def resolve(self, common, mine, other, expected):
        actual = merge.getMergedFit(common, mine, other)

        self.assertEqual(expected[0], actual[0], '\n\nerror: "merged" not as expected')
        self.assertEqual(expected[1], actual[1], '\n\nerror: "modified" not as expected')
        self.assertEqual(expected[2], actual[2], '\n\nerror: "added" not as expected')
        self.assertEqual(expected[3], actual[3], '\n\nerror: "removed" not as expected')
        self.assertEqual(expected[4]['add'], actual[4]['add'], '\n\nerror: "addConflicts" not as expected')
        self.assertEqual(expected[4]['mod'], actual[4]['mod'], '\n\nerror: "modConflicts" not as expected')
        self.assertEqual(expected[4]['modRem'], actual[4]['modRem'], '\n\nerror: "modRemConflicts" not as expected')
        self.assertEqual(expected[4]['remMod'], actual[4]['remMod'], '\n\nerror: "remModConflicts" not as expected')

    def testSomeOfEach(self):
        #{"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6, "g": 7, "h": 8, "i": 9, "j": 10, "k": 11, "l": 12, "m": 13, "n": 14}
        common = getStandardDict(10)
        mine =  {'a': 1, 'b': 1, 'k': 11, 'd': 3, 'e': 5, 'l': 12, 'g': 7, 'h': 7, 'n': 13, 'i': 8}
        other = {'a': 1, 'b': 1, 'k': 11, 'd': 4, 'e': 4, 'm': 13, 'f': 6, 'h': 9, 'n': 15, 'j': 9}
        expected = (
            {'a': 1, 'b': 1, 'k': 11, 'd': 3, 'e': 4, 'l': 12, 'm': 13, 'h': 7, 'n': 13, 'i': 8},
            set(['e']),
            set(['m']),
            set(['g']),
            {
                'add': set(['n']),
                'mod': set(['h']),
                'modRem': set(['i']),
                'remMod': set(['j']),
            }
        )

        self.merge(common, mine, other, expected)
'''