#from pymel.core import factories
#from pymel.all import mayautils
import pprint
import os.path
import re
import copy
import fnmatch
import inspect
import logging

import pymel.core as pm
import pymel.internal.factories as factories
#import pymel.internal.mayautils as mayautils
import pymel.internal.startup as startup
import pymel.internal.cmdcache as cmdcache
import pymel.internal.apicache as apicache
import pymel.util as util
import pymel.util.picklezip as picklezip

def separateExampleCache():
    examples = {}
    succ = fail = 0
    for cmdName, cmdInfo in factories.cmdlist.iteritems():
        try:
            examples[cmdName] = cmdInfo.pop('example')
            succ += 1
        except KeyError:
            fail += 1
            pass
    print "succeeded", succ
    print "failed   ", fail

    mayautils.writeCache( (factories.cmdlist,
                          factories.nodeHierarchy,
                          factories.uiClassList,
                          factories.nodeCommandList,
                          factories.moduleCmds),
                          'mayaCmdsList', 'the list of Maya commands', compressed=False )

    mayautils.writeCache( examples,
                          'mayaCmdsExamples', 'the list of Maya command examples',compressed=False )

def separateApiDocs():
    data = list(mayautils.loadCache('mayaApi',compressed=True))
    apiClassInfo = data[7]
    newApiDocs = {}
    for mfn, mfnInfo in apiClassInfo.iteritems():
        #print mfn, type(mfnInfo)
        if isinstance(mfnInfo, dict):
            #print mfn
            newAllMethodsInfo = {}
            for method, methodInfoList in mfnInfo['methods'].iteritems():
                newMethodInfoList = []
                for i, methodInfo in enumerate(methodInfoList):
                    newMethodInfo = {}
                    if 'doc' in methodInfo:
                        newMethodInfo['doc'] = methodInfo.pop('doc')
                    newArgInfo = {}
                    for arg, argInfo in methodInfo['argInfo'].iteritems():
                        if 'doc' in argInfo:
                            newArgInfo[arg] = {'doc': argInfo.pop('doc')}
                    if newArgInfo:
                        newMethodInfo['argInfo'] = newArgInfo
                    newMethodInfoList.append(newMethodInfo)
                if newMethodInfoList:
                    newAllMethodsInfo[method] = newMethodInfoList
            if newAllMethodsInfo:
                newApiDocs[mfn] = {'methods': newAllMethodsInfo }
        else:
            pass
            #print mfn, type(mfnInfo)
    #pprint.pprint(newApiDocs['MFnTransform'])
    data[7] = apiClassInfo

    mayautils.writeCache( tuple(data),
                          'mayaApi', compressed=True )

    mayautils.writeCache( newApiDocs,
                          'mayaApiDocs',compressed=True )

def upgradeCmdCaches():
    import pymel.internal.cmdcache as cmdcache

    data = list(mayautils.loadCache('mayaCmdsList',compressed=False))
    cmdlist = data[0]
    nodeHierarchy = data[1]
    cmdDocList = {}
    examples = {}
    succ = fail = 0
    for cmdName, cmdInfo in cmdlist.iteritems():

        flags = cmdcache.getCallbackFlags(cmdInfo)
        if flags:
            cmdlist[cmdName]['callbackFlags'] = flags

        try:
            examples[cmdName] = cmdInfo.pop('example')
        except KeyError:
            pass

        newCmdInfo = {}
        if 'description' in cmdInfo:
            newCmdInfo['description'] = cmdInfo.pop('description')
        newFlagInfo = {}
        if 'flags' in cmdInfo:
            for flag, flagInfo in cmdInfo['flags'].iteritems():
                newFlagInfo[flag] = { 'docstring' : flagInfo.pop('docstring') }
            newCmdInfo['flags'] = newFlagInfo

        if newCmdInfo:
            cmdDocList[cmdName] = newCmdInfo

        if 'shortFlags' in cmdInfo:
            d = {}
            #print cmdName
            for flag, flagInfo in cmdInfo['shortFlags'].iteritems():
                if isinstance(flagInfo, dict):
                    d[flag] = flagInfo['longname']
                elif isinstance(flagInfo, basestring):
                    d[flag] = flagInfo
                else:
                    raise TypeError
            cmdInfo['shortFlags'] = d

    hierarchy = [ (x.key, tuple( [y.key for y in x.parents()]), tuple( [y.key for y in x.childs()] ) ) \
                   for x in nodeHierarchy.preorder() ]

    data[0] = cmdlist
    data[1] = hierarchy

    mayautils.writeCache( tuple(data),
                          'mayaCmdsList', 'the list of Maya commands',compressed=True )

    mayautils.writeCache( cmdDocList,
                          'mayaCmdsDocs', 'the Maya command documentation',compressed=True )

    mayautils.writeCache( examples,
                          'mayaCmdsExamples', 'the list of Maya command examples',compressed=True )

#    for cache, useVersion in [ ('mayaApiMelBridge',False), ('mayaApi',True) ]:
#        data = mayautils.loadCache(cache, useVersion=useVersion, compressed=False)
#        mayautils.writeCache(data, cache, useVersion=useVersion, compressed=True)

def addCallbackFlags():
    data = list(mayautils.loadCache('mayaCmdsList',compressed=True))
    cmdlist = data[0]
    succ = 0
    for cmdName, cmdInfo in cmdlist.iteritems():
        flags = factories.getCallbackFlags(cmdInfo)
        if flags:
            cmdlist[cmdName]['callbackFlags'] = flags
            succ += 1

    data[0] = cmdlist
    mayautils.writeCache( tuple(data),
                          'mayaCmdsList', 'the list of Maya commands',compressed=True )

def reduceShortFlags():
    succ = 0
    for cmdName, cmdInfo in factories.cmdlist.iteritems():
        if 'shortFlags' in cmdInfo:
            d = {}
            print cmdName
            for flag, flagInfo in cmdInfo['shortFlags'].iteritems():
                if isinstance(flagInfo, dict):
                    d[flag] = flagInfo['longname']
                elif isinstance(flagInfo, basestring):
                    d[flag] = flagInfo
                else:
                    raise TypeError
            cmdInfo['shortFlags'] = d
            succ += 1
    print "reduced", succ
    mayautils.writeCache( (factories.cmdlist,
                          factories.nodeHierarchy,
                          factories.uiClassList,
                          factories.nodeCommandList,
                          factories.moduleCmds),
                          'mayaCmdsList', 'the list of Maya commands' )

def flattenNodeHier():

    hierarchy = [ (x.key, tuple( [y.key for y in x.parents()]) ) for x in factories.nodeHierarchy.preorder() ]
    factories.nodeHierarchy = hierarchy
    mayautils.writeCache( (factories.cmdlist,
                          factories.nodeHierarchy,
                          factories.uiClassList,
                          factories.nodeCommandList,
                          factories.moduleCmds),
                          'mayaCmdsList', 'the list of Maya commands' )

caches = [ ('mayaCmdsList', True), ('mayaApiMelBridge',False), ('mayaApi',True) ]
def mergeAll():
    data = []
    for cache, useVersion in caches:
        data.append( mayautils.loadCache(cache, useVersion=useVersion))

    mayautils.writeCache( tuple(data), 'mayaAll' )


import time
def mergedTest():
    s1 = time.time()
    for cache, useVersion in caches:
        mayautils.loadCache(cache, useVersion=useVersion)
    print time.time()-s1

    s2 = time.time()
    mayautils.loadCache('mayaAll')
    print time.time() - s2


def compressAll():
    for cache, useVersion in caches + [('mayaCmdsListAll', True), ('mayaCmdsDocs', True) ]:
        compress(cache, useVersion)

def compress(cache, useVersion=True):
    useVersion = dict(caches).get(cache,useVersion)
    data = mayautils.loadCache(cache, useVersion=useVersion, compressed=False)
    mayautils.writeCache(data, cache, useVersion=useVersion, compressed=True)

def decompress():
    caches2 = [ ('mayaCmdsListAll', True), ('mayaApiMelBridge',False), ('mayaApi',True) ]

    num = 3

    s = time.time()
    for i in range(num):
        for cache, useVersion in caches2:
            data = mayautils.loadCache(cache, useVersion=useVersion, compressed=False)
    print "compress=0, docstrings=1:", time.time()-s

    s1 = time.time()
    for i in range(num):
        for cache, useVersion in caches:
            data = mayautils.loadCache(cache, useVersion=useVersion, compressed=False)
    print "compress=0, docstrings=0:", time.time()-s1

    s1 = time.time()
    for i in range(num):
        for cache, useVersion in caches2:
            data = mayautils.loadCache(cache, useVersion=useVersion, compressed=True)
    print "compress=1, docstrings=1:", time.time()-s1

    s1 = time.time()
    for i in range(num):
        for cache, useVersion in caches:
            data = mayautils.loadCache(cache, useVersion=useVersion, compressed=True)
    print "compress=1, docstrings=0:", time.time()-s1

def prepdiff(cache, outputDir='' ):
    pprintCache(cache, True, outputDir)
    pprintCache(cache, False, outputDir)

def pprintCache(cache, compressed, outputDir):
    useVersion = dict(caches).get(cache,True)
    data = mayautils.loadCache(cache, useVersion=useVersion, compressed=compressed)
    fname = os.path.realpath(os.path.join('', cache+ ('_zip.txt' if compressed else '_bin.txt') ) )
    print "writing to", fname
    f = open(fname, 'w')

    pprint.pprint( data, f)
    f.close()

def compareDicts(dict1, dict2, showDiff=True, showOnlys=False, indent=0):
    if isinstance(dict1, (list, tuple)):
        dict1 = dict(enumerate(dict1))
    if isinstance(dict2, (list, tuple)):
        dict2 = dict(enumerate(dict2))
    v1 = set(dict1)
    v2 = set(dict2)
    both = v1 & v2
    only1 = v1 - both
    only2 = v2 - both
    print "\t" * indent, "both:", len(both)
    print "\t" * indent, "only1:", len(only1)
    print "\t" * indent, "only2:", len(only2)

    differences = {}
    for mayaType in both:
        if dict1[mayaType] != dict2[mayaType]:
            differences[mayaType] = (dict1[mayaType], dict2[mayaType])
    print "\t" * indent, "differences:", len(differences)

    #print "\t" * indent, "*" * 60
    if showDiff and differences:
        print "\t" * indent, "different: (%d)" % len(differences)
        for key in sorted(differences):
            print "\t" * indent, key, ':',
            diff1, diff2 = differences[key]
            subDict1 = subDict2 = None
            if type(diff1) == type(diff2) and isinstance(diff1, (dict, list, tuple)):
                print
                compareDicts(diff1, diff2, showDiff=showDiff, showOnlys=showOnlys, indent=indent+1)
            else:
                print diff1, '-', diff2
        #print "\t" * indent, "*" * 60
    if showOnlys:
        if only1:
            print "\t" * indent, "only1: (%d)" % len(only1)
            for x in only1:
                print "\t" * indent, x
            #print "\t" * indent, "*" * 60
        if only2:
            print "\t" * indent, "only2: (%d)" % len(only2)
            for x in only2:
                print "\t" * indent, x
    #print "\t" * indent, "*" * 60
    return both, only1, only2, differences


def compareTrees(tree1, tree2):
    def convertTree(oldTree):
        if isinstance(oldTree, dict):
            return oldTree
        newTree = {}
        for key, parents, children in oldTree:
            newTree[key] = [parents, set(children)]
        return newTree
    tree1 = convertTree(tree1)
    tree2 = convertTree(tree2)
    t1set = set(tree1)
    t2set = set(tree2)
    both = t1set & t2set
    only1 = t1set - both
    only2 = t2set - both
    diff = {}
    for nodeType in both:
        n1 = tree1[nodeType]
        n2 = tree2[nodeType]
        if n1 != n2:
            if n1[0] == n2[0]:
                parentDiff = 'same'
            else:
                parentDiff = (n1[0], n2[0])
            if n1[1] == n2[1]:
                childDiff = 'same'
            else:
                childDiff = (n1[1] - n2[1], n2[1] - n1[1])
        diff[nodeType] = (parentDiff, childDiff)
    return only1, only2, diff

def _getClassEnumDicts(pickleData, parser):
    classInfos = pickleData[-1]
    classEnums = {}; classPyEnums = {}
    for className, classInfo in classInfos.iteritems():
        enums = classInfo.get('enums')
        if enums:
            enums = dict( (enumName, data['values']) for enumName, data in enums.iteritems())
            classEnums[className] = enums
        pyEnums = classInfo.get('pymelEnums')
        if pyEnums:
            classPyEnums[className] = pyEnums
    assert(set(classEnums.keys()) == set(classPyEnums.keys()))
    return classEnums, classPyEnums

def checkEnumConsistency(pickleData, docLocation=None, parser=None):
    '''Check that the pymelEnums and enums have consistent index mappings
    '''
    class NotFound(object):
        def __repr__(self):
            return ':NOTFOUND:'
    notFound = NotFound()

    if parser is None:
        import pymel.internal.parsers as parsers
        import maya.OpenMaya as om
        parser = parsers.ApiDocParser(om, docLocation=docLocation)
    classEnums, classPyEnums = _getClassEnumDicts(pickleData, parser)

    badByEnum = {}

    for className, enums in classEnums.iteritems():
        for enumName, enum in enums.iteritems():
            fullEnumName = "%s.%s" % (className, enumName)
            badThisEnum = {}
            try:
                #print fullEnumName
                #print enum
                pyEnum = classPyEnums[className][enumName]
                #print pyEnum
                enumToPyNames = parser._apiEnumNamesToPymelEnumNames(enum)
                for apiName, val in enum._keys.iteritems():
                    pyName = enumToPyNames[apiName]
                    try:
                        pyIndex = pyEnum.getIndex(pyName)
                    except ValueError:
                        pyIndex = notFound
                    try:
                        apiIndex = enum.getIndex(apiName)
                    except ValueError:
                        apiIndex = notFound
                    if pyIndex != apiIndex:
                        badThisEnum.setdefault('mismatch', []).append(
                                    {'api':(apiName, apiIndex),
                                     'py':(pyName, pyIndex)})
                    if pyIndex is None:
                        badThisEnum.setdefault('badPyIndex', []).append((pyName, pyIndex))
                    if apiIndex is None:
                        badThisEnum.setdefault('badApiIndex', []).append((apiName, apiIndex))

            except Exception:
                import traceback
                badThisEnum['exception'] = traceback.format_exc()
            if badThisEnum:
                badByEnum[fullEnumName] = badThisEnum
    return classEnums, classPyEnums, badByEnum
#    if bad:
#        print
#        print "!" * 80
#        print "Bad results:"
#        print '\n'.join(bad)
#        print "!" * 80
#        raise ValueError("inconsistent pickled enum data")

# made a change to enums in apiClassInfo[apiClassName]['pymelEnums'] such that
# they now have as keys BOTH the api form (kSomeName) and the python form
# (someName) - this method converts over old caches on disk to the new format
def convertPymelEnums(docLocation=None):
    # Compatibility for pre-2012 caches... see note after ApiEnum def in
    # apicache
    import pymel.api
    pymel.api.Enum = apicache.ApiEnum
    apicache.Enum = apicache.ApiEnum

    import pymel.internal.parsers as parsers
    import maya.OpenMaya as om
    parser = parsers.ApiDocParser(om, docLocation=docLocation)

    dummyCache = apicache.ApiCache()
    dummyCache.version = '[0-9.]+'
    cachePattern = pm.Path(dummyCache.path())
    caches = sorted(cachePattern.parent.files(re.compile(cachePattern.name)))
    rawCaches = {}
    badByCache = {}
    enumsByCache = {}
    for cachePath in caches:
        print "checking enum data for: %s" % cachePath
        raw = picklezip.load(unicode(cachePath))
        rawCaches[cachePath] = raw
        classEnums, classPyEnums, bad = checkEnumConsistency(raw, parser=parser)
        if bad:
            badByCache[cachePath] = bad
        enumsByCache[cachePath] = {'api':classEnums, 'py':classPyEnums}
    if badByCache:
        pprint.pprint(badByCache)
        print "Do you want to continue converting pymel enums? (y/n)"
        print "(Pymel values will be altered to match the api values)"
        answer = raw_input().lower().strip()
        if not answer or answer[0] != 'y':
            print "aborting cache update"
            return
    fixedKeys = []
    deletedEnums = []
    for cachePath, raw in rawCaches.iteritems():
        print '=' * 60
        print "Fixing: %s" % cachePath
        apiClassInfo = raw[-1]
        apiEnums = enumsByCache[cachePath]['api']
        pyEnums = enumsByCache[cachePath]['py']
        assert(set(apiEnums.keys()) == set(pyEnums.keys()))
        for className, apiEnumsForClass in apiEnums.iteritems():
            pyEnumsForClass = pyEnums[className]
            assert(set(apiEnumsForClass.keys()) == set(pyEnumsForClass.keys()))
            for enumName, apiEnum in apiEnumsForClass.iteritems():
                fullEnumName = '%s.%s' % (className, enumName)
                print fullEnumName

                # first, find any "bad" values - ie, values whose index is None
                # - and delete them
                badKeys = [key for key, index in apiEnum._keys.iteritems()
                           if index is None]
                if badKeys:
                    print "!!!!!!!!"
                    print "fixing bad keys in %s - %s" % (fullEnumName, badKeys)
                    print "!!!!!!!!"
                    assert(None in apiEnum._values)
                    valueDocs =  apiClassInfo[className]['enums'][enumName]['valueDocs']
                    for badKey in badKeys:
                        valueDocs.pop(badKey, None)
                        del apiEnum._keys[badKey]
                    del apiEnum._values[None]

                    if not apiEnum._keys:
                        print "enum empty after removing bad keys - deleting..."
                        del apiClassInfo[className]['enums'][enumName]
                        del apiClassInfo[className]['pymelEnums'][enumName]
                        deletedEnums.append(fullEnumName)
                        continue
                    else:
                        fixedKeys.append(fullEnumName)
                else:
                    assert(None not in apiEnum._values)

                try:
                    pyEnums[className] = parser._apiEnumToPymelEnum(apiEnum)
                except Exception:
                    globals()['rawCaches'] = rawCaches
                    globals()['apiEnum'] = apiEnum
                    raise

    # After making ALL changes, if there were NO errors, write them all out...
    for cachePath, raw in rawCaches.iteritems():
        picklezip.dump(raw, unicode(cachePath))

def apiPymelWrapData(keepDocs=False, keepReturnQualifiers=True):
    '''
    Return a dict with info about which api methods were actually wrapped

    Supposed to help detect if changes to the api wraps (or api parsing, etc)
    have affected something that "matters" - ie, a class which is actually
    warpped by pymel, and a method overload that is actually used.

    ***WARNING***
    To work, you will first have to edit factories.py and set _DEBUG_API_WRAPS
    to True
    '''
    # make sure we trigger loading of all dynamic modules, and all their
    # members...
    import pymel.all

    apiClassInfo = factories.apiClassInfo
    usedMethods = {}
    for apiClassName, classMethods in factories._wrappedApiMethods.iteritems():
        for methodName, methodWraps in classMethods.iteritems():
            for methodWrapInfo in methodWraps:
                func = methodWrapInfo['funcRef']
                if func is None:
                    continue
                index = methodWrapInfo['index']
                usedClassMethods = usedMethods.setdefault(apiClassName, {})
                methodInfo = apiClassInfo[apiClassName]['methods'][methodName][index]
                usedClassMethods.setdefault(methodName, {})[index] = methodInfo
    return usedMethods

def findApiWrapRegressions(oldWraps, newWraps, docs=False,
                           returnQualifiers=True, typeConversions=None,
                           verbose=True):
    '''Given api wrap data from apiPymelWrapData for an old and new version,
    tries to find changes that would cause backwards-compatibility problems /
    regressions.
    '''
    if docs or returnQualifiers or typeConversions:
        # make copies, as we'll be modifying
        oldWraps = copy.deepcopy(oldWraps)
        newWraps = copy.deepcopy(newWraps)

        for wraps in oldWraps, newWraps:
            for cls, methodsDict in wraps.iteritems():
                for method, overloadsDict in methodsDict.iteritems():
                    for overloadIndex, methodInfo in overloadsDict.iteritems():
                        if not docs:
                            methodInfo.pop('doc', None)
                            for argData in methodInfo.get('argInfo', {}).itervalues():
                                argData.pop('doc', None)
                            methodInfo.get('returnInfo', {}).pop('doc', None)
                        if not returnQualifiers:
                            methodInfo.get('returnInfo', {}).pop('qualifiers', None)
                        if typeConversions:
                            # argInfo
                            for argInfo in methodInfo.get('argInfo', {}).itervalues():
                                argType = argInfo.get('type')
                                if argType in typeConversions:
                                    argInfo['type'] = typeConversions[argType]
                            # args
                            args = methodInfo.get('args', [])
                            for i, theseArgs in enumerate(args):
                                argType = theseArgs[1]
                                if argType in typeConversions:
                                    theseArgs = list(theseArgs)
                                    theseArgs[1] = typeConversions[argType]
                                    args[i] = tuple(theseArgs)
                            # returnInfo
                            returnInfo = methodInfo.get('returnInfo', {})
                            returnInfoType = returnInfo.get('type')
                            if returnInfoType in typeConversions:
                                returnInfo['type'] = typeConversions[returnInfoType]
                            # returnType
                            returnType = methodInfo.get('returnType')
                            if returnType in typeConversions:
                                methodInfo['returnType'] = typeConversions[returnType]
                            # types
                            types = methodInfo.get('types', {})
                            for argName, argType in types.iteritems():
                                if argType in typeConversions:
                                    types[argName] = typeConversions[argType]

    def setClassProblem(className, issue):
        problems[className] = issue

    def getClassProblems(className):
        return problems.setdefault(className, {})

    def setMethodProblem(className, methodName, issue):
        getClassProblems(className)[methodName] = issue

    def getMethodProblems(className, methodName):
        return getClassProblems(className).setdefault(methodName, {})

    def setIndexProblem(className, methodName, index, issue):
        getMethodProblems(className, methodName)[index] = issue

    problems = {}
    for className, oldMethodNames in oldWraps.iteritems():
        if className not in newWraps:
            setClassProblem(className, '!!!Class missing!!!')
            continue
        newMethodNames = newWraps[className]

        for methodName, oldMethodWraps in oldMethodNames.iteritems():
            if methodName not in newMethodNames:
                setMethodProblem(className, methodName, '!!!Method missing!!!')
                continue
            newMethodWraps = newMethodNames[methodName]

            for i, oldWrap in oldMethodWraps.iteritems():
                try:
                    newWrap = newMethodWraps[i]
                except KeyError:
                    setIndexProblem(className, methodName, i, '!!!Overload index missing!!!')
                    continue
                if newWrap == oldWrap:
                    continue
                else:
                    diff = util.compareCascadingDicts(oldWrap, newWrap)
                    setIndexProblem(className, methodName, i, ('Overload differed',
                                                               diff[1:]))

    if verbose:
        printAllProblems(problems, oldWraps, newWraps)
    return problems

def printAllProblems(problems, oldWraps, newWraps):
    for cls, clsInfo in problems.iteritems():
        if isinstance(clsInfo, basestring):
            print '#' * 80
            print '%s:' % cls
            print clsInfo
            continue
        for method in clsInfo:
            printMethProblems(cls, method, problems, oldWraps, newWraps)

def printMethProblems(cls, method, problems, oldWraps, newWraps):
    clsProb = problems[cls]
    if isinstance(clsProb, basestring):
        print clsProb
        return
    methProb = clsProb[method]
    if isinstance(methProb, basestring):
        print methProb
        return

    for overloadIndex, overloadDiff in problems[cls][method].iteritems():
        print '#' * 80
        print '%s.%s[%d]:' % (cls, method, overloadIndex)
        print
        for wraps, wrapName in (oldWraps, 'old'), (newWraps, 'new'):
            print '%s:' % wrapName
            clsInfo = wraps.get(cls)
            if clsInfo is None:
                print '!! class %s missing on %s !!' % (cls, wrapName)
                continue
            methInfo = clsInfo.get(method)
            if methInfo is None:
                print '!! method %s missing on %s !!' % (method, wrapName)
                continue
            overloadInfo = methInfo.get(overloadIndex)
            if overloadInfo is None:
                print '!! overload %s missing on %s !!' % (overloadIndex, wrapName)
                continue
            wrapSparse = getSparseFromDelta(overloadDiff[1][2], overloadInfo)
            pprint.pprint(wrapSparse)

def getSparseFromDelta(delta, orig):
    #print "delta:", delta
    #print "orig:", orig
    results = {}
    for key, deltaSub in delta.iteritems():
        #print "deltaSub:", deltaSub
        try:
            origSub = orig[key]
        except (KeyError, IndexError):
            results[key] = '<Missing key %r>' % key
        else:
            if isinstance(deltaSub, dict):
                results[key] = getSparseFromDelta(deltaSub, origSub)
            else:
                results[key] = orig[key]
    #print "results:", results
    return results

# apiToPyData used to be indexed by (pyNodeName, basePyMethodName)
# where basePyMethodName was the 'pymelName' stored in
#    apiClassInfo[apiClassName]['methods'][apiMethodName]
# Using this as a key was bad, though, both because one of the things the
# apiToPyData is supposed to store is what pymelName api methods map to (so
# indexing based on an 'intermediate' pymel name is strange), and because it
# can result in key conflicts - ie, both MTransformationMatrix.rotation and
# MTransformationMatrix.getRotation map to the 'standard' pymel name of
# 'getRotation'... so using the old key system, there was no way to store
# information about both.
#
# This class was used to translate the apiMelData to using
# (pyNodeName, apiMethodName) indices.
# May seem strange to use a combination of pymel / api names, but this makes
# sense because for classes, we want to use pynode names, since this allows us
# to make overrides on a per-pynode basis (ie, if both myAwesomeNode and
# myOtherNode have as their apicls MFnDependencyNode, we can make it so one
# wraps MFnDependencyNode.addAttribute and the other doesn't, or change the
# pymel name for only one)... and we need to use api method names for the
# reasons outlined above.

class WrapTranslateError(Exception): pass
class WrapTranslateNewKeyError(WrapTranslateError): pass
class WrapTranslateOldKeyError(WrapTranslateError): pass

# old possible parameters in apiToMelData:
# ========================================
# keys:
# -----
# clsName - the name of the PyNode class we will be putting the methods on
# pyMethodName - the "intermediate" name of the method, shared for both cmds
#     and api wraps; for api, it is the value stored in the 'pymelName' field
#     in apiClassInfo (else the api method name); for cmds, it is the
#     converted flag name (ie, the flag with 'get' or 'set' possibly in front)
# data:
# -----
# enabled - whether the api wrap was enabled (but also had an inverse enabling
#     of the cmds wrap - ie, if 'melEnabled' is True OR 'enabled' is
#     False, the cmd wrap will be done... meaning there was no
#     "permanent" way to disable BOTH the api and cmd wrap (you could
#     "temporarily" disable both by setting 'overloadIndex' to None, but
#     see the note for that
# melEnabled - whether the cmd wrap was enabled (but this could also be
#     controlled by enabled - see above); defaults to False
# melName - the name of the associated cmd wrap - in practice, is only used
#     for determining the name of wrapped method, if 'useName' is API
# overloadIndex - which api overload to use for the wrap; if None, then no api
#     method wrap is made, effectively disabling it; however, as opposed to the
#     'enabled' flag, this will be re-calculated every time pymelControlPanel is
#     run, effectively making it mean "i don't know", and the disabling
#     (potentially) temporary; defaults to None
# useName - controls what pymel name to map this method to - if API, it uses
#     the value stored in the 'pymelName' from apiClassInfo; if MEL, it uses the
#     value in melName; otherwise, it is a custom name that is used directly
#
###############################################################################
# new parameters for apiToPyData
# ==============================
# keys:
# -----
# clsName - the name of the PyNode class we will be putting the methods on
# apiMethodName - the un-modified name of the api method we will be wrapping
#
# data:
# -----
# enabled - whether this api method wrap should be applied for this PyNode; if
#     True, a new wrap will always be done for the node (even if an
#     ancestor PyNode already wrapped it); if False, it will not be
#     wrapped for this class (though it may inherit a wrap from an
#     ancestor PyNode); and if None, it will be wrapped if no ancestor
#     has wrapped it, otherwise it will not be wrapped; defaults to None
# overloadIndex - which api overload to use for the wrap; if None, then no api
#     method wrap is made, effectively disabling it; however, as opposed to the
#     'enabled' flag, this will be re-calculated every time the api cache is
#     rebuilt OR pymelControlPanel is run, effectively making it mean "i don't
#     know", and the disabling (potentially) temporary; defaults to None
# useName - controls what pymel name to map this method to - if None, it uses
#     the value stored in the 'pymelName' from apiClassInfo; otherwise, it
#     is a custom name that is used directly; defaults to None
# notes - list of notes on why changes were made, etc; informational only

# new parameters for cmdsToPyData
# ===============================
# keys:
# -----
# clsName - the name of the PyNode class we will be putting the methods on
# flagName - the un-modified name of the mel cmd flag we will be wrapping
# cmdType - what "sort" of wrap of the flag this is - ie, "get", "set", or
#    "other"
# data:
# -----
# enabled - whether this cmd flag wrap should be applied for this PyNode;
#     if set to True/False, then the method is wrapped; if None, then it is
#     wrapped if the name is not present on the class, or if it is, but it was
#     from another mel cmd wrap; defaults to None
# useName - controls what pymel name to map this method to - if None, it uses
#     the default name, generated from _MetaMayaCommandWrapper.flagToMethodName;
#     otherwise, it is a custom name that is used directly; defaults to None
# notes - list of notes on why changes were made, etc; informational only
#
# Additonally, there is a new TwoWayDict apiCmdsEquivalents which stores
# information about equivalent cmd/api wraps; it has no functional effect on
# how things are wrapped, and is only used within the pymelControlPanel gui
# to provide an easier way to link the setting of data for similar methods


class WrapDataTranslator(object):
    TO_DELETE_CLASSES = set([
                             'Angle',
                            ])
    TO_DELETE_METHODS = set([
                             ('TransformationMatrix', 'getRotation'),
                             ('TransformationMatrix', 'rotation'),
                             # these are just the unTranslated items... tested,
                             # and they never seem to be accessed...
                             #('AnimCurve', 'setTangentTypes'), ('AttrHierarchyTest', 'enableDGTiming'), ('AttrHierarchyTest', 'getIcon'), ('AttrHierarchyTest', 'setIcon'), ('Attribute', 'asMDataHandle'), ('AttributeDefaults', 'getParent'), ('AttributeDefaults', 'setParent'), ('Camera', 'getEyeOffset'), ('Camera', 'isParallelView'), ('Camera', 'isStereo'), ('Camera', 'setEyeOffset'), ('Camera', 'setParallelView'), ('Camera', 'setStereo'), ('CameraSet', 'getLayerClearDepthValue'), ('CameraSet', 'setLayerClearDepthValue'), ('DagNode', 'activeColor'), ('DagNode', 'dormantColor'), ('DagNode', 'drawOverrideColor'), ('DagNode', 'drawOverrideEnabled'), ('DagNode', 'drawOverrideIsReference'), ('DagNode', 'drawOverrideIsTemplate'), ('DagNode', 'hiliteColor'), ('DagNode', 'usingHiliteColor'), ('DataBlockTest', 'enableDGTiming'), ('DataBlockTest', 'getIcon'), ('DataBlockTest', 'setIcon'), ('DependNode', 'enableDGTiming'), ('DependNode', 'getIcon'), ('DependNode', 'setIcon'), ('Distance', 'as'), ('Distance', 'asCentimeters'), ('Distance', 'asFeet'), ('Distance', 'asInches'), ('Distance', 'asKilometers'), ('Distance', 'asMeters'), ('Distance', 'asMiles'), ('Distance', 'asMillimeters'), ('Distance', 'asUnits'), ('Distance', 'asYards'), ('Distance', 'className'), ('Distance', 'getInternalUnit'), ('Distance', 'getUnit'), ('Distance', 'getValue'), ('Distance', 'internalToUI'), ('Distance', 'internalUnit'), ('Distance', 'setInternalUnit'), ('Distance', 'setUIUnit'), ('Distance', 'setUnit'), ('Distance', 'setValue'), ('Distance', 'uiToInternal'), ('Distance', 'uiUnit'), ('Entity', 'addAttribute'), ('Entity', 'allocateFlag'), ('Entity', 'attribute'), ('Entity', 'attributeClass'), ('Entity', 'attributeCount'), ('Entity', 'canBeWritten'), ('Entity', 'classification'), ('Entity', 'create'), ('Entity', 'deallocateAllFlags'), ('Entity', 'deallocateFlag'), ('Entity', 'dgCallbackIds'), ('Entity', 'dgCallbacks'), ('Entity', 'dgTimer'), ('Entity', 'dgTimerOff'), ('Entity', 'dgTimerOn'), ('Entity', 'dgTimerQueryState'), ('Entity', 'dgTimerReset'), ('Entity', 'enableDGTiming'), ('Entity', 'findAlias'), ('Entity', 'findPlug'), ('Entity', 'getAffectedAttributes'), ('Entity', 'getAffectedByAttributes'), ('Entity', 'getAliasAttr'), ('Entity', 'getAliasList'), ('Entity', 'getConnections'), ('Entity', 'getIcon'), ('Entity', 'getName'), ('Entity', 'getPlugsAlias'), ('Entity', 'hasAttribute'), ('Entity', 'hasUniqueName'), ('Entity', 'isDefaultNode'), ('Entity', 'isFlagSet'), ('Entity', 'isFromReferencedFile'), ('Entity', 'isLocked'), ('Entity', 'isNewAttribute'), ('Entity', 'isShared'), ('Entity', 'parentNamespace'), ('Entity', 'pluginName'), ('Entity', 'plugsAlias'), ('Entity', 'removeAttribute'), ('Entity', 'reorderedAttribute'), ('Entity', 'setAlias'), ('Entity', 'setDoNotWrite'), ('Entity', 'setFlag'), ('Entity', 'setIcon'), ('Entity', 'setLocked'), ('Entity', 'setName'), ('Entity', 'typeId'), ('Entity', 'typeName'), ('Entity', 'userNode'), ('HierarchyTestNode1', 'enableDGTiming'), ('HierarchyTestNode1', 'getIcon'), ('HierarchyTestNode1', 'setIcon'), ('HierarchyTestNode2', 'enableDGTiming'), ('HierarchyTestNode2', 'getIcon'), ('HierarchyTestNode2', 'setIcon'), ('HierarchyTestNode3', 'enableDGTiming'), ('HierarchyTestNode3', 'getIcon'), ('HierarchyTestNode3', 'setIcon'), (u'Joint', u'getRelative'), (u'Joint', u'setRelative'), ('LightSet', 'addMember'), ('LightSet', 'addMembers'), ('LightSet', 'className'), ('LightSet', 'clear'), ('LightSet', 'create'), ('LightSet', 'getAnnotation'), ('LightSet', 'getIntersection'), ('LightSet', 'getMembers'), ('LightSet', 'getUnion'), ('LightSet', 'hasRestrictions'), ('LightSet', 'intersectsWith'), ('LightSet', 'isMember'), ('LightSet', 'removeMember'), ('LightSet', 'removeMembers'), ('LightSet', 'restriction'), ('LightSet', 'setAnnotation'), ('LightSet', 'type'), ('MFnSet', 'getIntersection'), ('MFnSet', 'getIntersectn'), ('MatteSet', 'addMember'), ('MatteSet', 'addMembers'), ('MatteSet', 'className'), ('MatteSet', 'clear'), ('MatteSet', 'create'), ('MatteSet', 'getAnnotation'), ('MatteSet', 'getIntersection'), ('MatteSet', 'getMembers'), ('MatteSet', 'getUnion'), ('MatteSet', 'hasRestrictions'), ('MatteSet', 'intersectsWith'), ('MatteSet', 'isMember'), ('MatteSet', 'removeMember'), ('MatteSet', 'removeMembers'), ('MatteSet', 'restriction'), ('MatteSet', 'setAnnotation'), ('MatteSet', 'type'), ('Mesh', 'addHoles'), ('Mesh', 'copyUVSet'), ('Mesh', 'createColorSet'), ('Mesh', 'createUVSet'), ('Mesh', 'getDisplayColors'), ('Mesh', 'polyTriangulate'), ('Mesh', 'setDisplayColors'), ('OldBlindDataBase', 'enableDGTiming'), ('OldBlindDataBase', 'getIcon'), ('OldBlindDataBase', 'setIcon'), ('RadialField', 'getRadialType'), ('RadialField', 'setRadialType'), ('SimpleTestNode', 'enableDGTiming'), ('SimpleTestNode', 'getIcon'), ('SimpleTestNode', 'setIcon'), ('SwitchColorSet', 'addMember'), ('SwitchColorSet', 'addMembers'), ('SwitchColorSet', 'className'), ('SwitchColorSet', 'clear'), ('SwitchColorSet', 'create'), ('SwitchColorSet', 'getAnnotation'), ('SwitchColorSet', 'getIntersection'), ('SwitchColorSet', 'getMembers'), ('SwitchColorSet', 'getUnion'), ('SwitchColorSet', 'hasRestrictions'), ('SwitchColorSet', 'intersectsWith'), ('SwitchColorSet', 'isMember'), ('SwitchColorSet', 'removeMember'), ('SwitchColorSet', 'removeMembers'), ('SwitchColorSet', 'restriction'), ('SwitchColorSet', 'setAnnotation'), ('SwitchColorSet', 'type'), ('TextureToGeom', 'enableDGTiming'), ('TextureToGeom', 'getIcon'), ('TextureToGeom', 'setIcon'), ('Time', '__add__'), ('Time', '__div__'), ('Time', '__eq__'), ('Time', '__mul__'), ('Time', '__neq__'), ('Time', '__radd__'), ('Time', '__rdiv__'), ('Time', '__rmult__'), ('Time', '__rsub__'), ('Time', '__sub__'), ('Time', 'as'), ('Time', 'getUnit'), ('Time', 'getValue'), ('Time', 'setUIUnit'), ('Time', 'setUnit'), ('Time', 'setValue'), ('Time', 'uiUnit')
                             ('Mesh', 'copyUVSet'),
                            ])
    TO_DELETE_METHODNAMES = set(['enum', 'className'])

    def __init__(self, logLevel=logging.WARNING, apiClassInfo=None, apiToPyData=None,
                 fromCache=True):
        # make sure we trigger loading of all dynamic modules, and all their
        # members...
        import pymel.all

        if apiClassInfo is None:
            if fromCache:
                #apiCache = picklezip.load('/Volumes/sv-dev01/devRepo/paulm/python/pymel/pymel/cache/mayaApi%s.zip' % mayaVer)
                apiCache = apicache.ApiCache().read()
                apiClassInfo = apiCache[4]
            else:
                apiClassInfo = factories.apiClassInfo
        if apiToPyData is None:
            if fromCache:
                # for translation, want to get most raw form of the cache
                # possible...
                #apiBridge = picklezip.load('/Volumes/sv-dev01/devRepo/paulm/python/pymel/pymel/cache/mayaApiMelBridge.zip')
                apiBridge = apicache.ApiMelBridgeCache().read()
                apiToPyData = apiBridge[0]
            else:
                apiToPyData = factories.apiToPyData

        self.apiClassInfo = apiClassInfo
        self.apiToPyData = apiToPyData
        self.logger = logging.getLogger('.'.join([__name__, 'WrapDataTranslator']))
        self.logger.setLevel(logLevel)

        self.newApiToPyData = {}
        self.apiOldToNewKey = {}
        self.apiNewToOldKey = {}
        self.apiTranslationSources = {}

        self.newCmdsToPyData = {}
        self.cmdsOldToNewKey = {}
        self.cmdsNewToOldKey = {}
        self.cmdsTranslationSources = {}

        self.newApiCmdsEquivalents = {}

        # old keys which were not used, and will be removed in the new map
        self.deleted = set()

    def debug(self, msg):
        self.logger.debug(msg)

    def info(self, msg):
        self.logger.info(msg)

    def warn(self, msg):
        self.logger.warn(msg)

    def error(self, msg):
        self.logger.debug(msg)

    def translateAll(self):
        self.translateKeys()
        self.translateData()

    def translateKeys(self):
        import pymel.api.plugins as plugins
        # want to get as many maya nodes as possible...
        plugins.loadAllMayaPlugins()

        print "num nonTranslated (start)  :", len(self.nonTranslated())

        for apiClsName in self.apiClassInfo:
        #for apiClsName, clsInfo in [('MFnLattice', apiClassInfo['MFnLattice'])]:
            try:
                pyNodeName = factories.apiClassNamesToPyNodeNames[apiClsName]
            except KeyError:
                continue
            self.doApiHierKeyTranslation(apiClsName, pyNodeName)
            #self.doApiClsKeyTranslation(apiClsName, pyNodeName)

        print "num nonTranslated (mfns)   :", len(self.nonTranslated())

        #for pyNode in fac.mayaTypesToApiTypes:
        #for pyNode in [pm.nt.Airfield]:
        #for pyNode in [pm.nt.Lattice]:
        #for pyNode in [pm.nt.AnimBlendNodeAdditiveI16]:
        for mayaType, apiEnumName in factories.mayaTypesToApiTypes.iteritems():
            pyNodeName = pm.util.capitalize(mayaType)
            pyNode = factories.pyNodeNamesToPyNodes[pyNodeName]
            apiCls = factories.apiTypesToApiClasses[apiEnumName]
            apiClsName = apiCls.__name__
            self.doApiHierKeyTranslation(apiClsName, pyNodeName)
            #self.doApiClsKeyTranslation(apiClsName, pyNodeName)

            pyMethods = factories.classToCmdMap.get(pyNode)
            if pyMethods is not None:
                for pyMethod, (cmd, flag, cmdType) in pyMethods.iteritems():
                    self.doCmdsKeyTranslation(cmd, pyNodeName, flag, cmdType,
                                              pyMethod)

        print "num nonTranslated (pynodes):", len(self.nonTranslated())

        for pyNodeName, pyNode in factories.pyNodeNamesToPyNodes.iteritems():
            cmd, isInfoCmd = pyNode.__metaclass__.getMelCmd(pyNode.__dict__)
            if cmd not in factories.cmdlist:
                continue
            for flag, flagInfo in factories.cmdlist[cmd]['flags'].iteritems():
                for pyMethod, cmdType in factories._MetaMayaCommandWrapper.flagToMethods(flag, flagInfo, isInfoCmd):
                    self.doCmdsKeyTranslation(cmd, pyNodeName, flag, cmdType,
                                              pyMethod)

        print "num nonTranslated (cmdlist):", len(self.nonTranslated())

        # there's some classes that have info in apiToPyData that, as far
        # as I can tell, is never actually used anymore... use manual mappings
        # to get the api names for these...
        manualMaps = {'Angle':pm.api.MAngle}

        for oldKey in self.nonTranslated():
            pyNodeName = oldKey[0]
            apiCls = manualMaps.get(pyNodeName)
            if apiCls is None:
                continue
            apiClsName = apiCls.__name__
            #self.doApiHierKeyTranslation(apiClsName, pyNodeName)
            self.doApiClsKeyTranslation(apiClsName, pyNodeName)

        print "num nonTranslated (manual) :", len(self.nonTranslated())

        for oldKey in self.nonTranslated():
            pyNodeName, pyMethodName = oldKey
            try:
                pyNode = factories.pyNodeNamesToPyNodes[pyNodeName]
            except KeyError:
                pass
            if not hasattr(pyNode, pyMethodName):
                #print "%s.%s was missing..." % oldKey
                #self.deleted.add(oldKey)
                if (oldKey[0] in self.TO_DELETE_CLASSES
                        or oldKey in self.TO_DELETE_METHODS
                        or oldKey[1] in self.TO_DELETE_METHODNAMES):
                    self.deleted.add(oldKey)

        print "num nonTranslated (del)    :", len(self.nonTranslated())

        for oldKey in self.nonTranslated():
            pyNodeName, pyMethodName = oldKey
            data = self.apiToPyData[oldKey]
            if (self.apiMelDataEqual(data, {}, oldKey[1])
                    or self.apiMelDataEqual(data, {'overloadIndex':0},
                                            oldKey[1])
                    or self.apiMelDataEqual(data, {'overloadIndex':None},
                                            oldKey[1])):
                self.deleted.add(oldKey)

        print "num nonTranslated (default):", len(self.nonTranslated())


    def nonTranslated(self):
        return sorted(set(self.apiToPyData) - set(self.apiOldToNewKey)
                      -set(self.cmdsOldToNewKey) - self.deleted)

    def doApiHierKeyTranslation(self, apiClsName, pyNodeName):
        self.info("translating hierarchy for %s / %s" % (apiClsName, pyNodeName))
        leafApiCls = getattr(pm.api, apiClsName)
        for apiCls in leafApiCls.mro():
            apiClsName = apiCls.__name__
            if apiClsName not in self.apiClassInfo:
                continue
            self.doApiClsKeyTranslation(apiClsName, pyNodeName)

    def doApiClsKeyTranslation(self, apiClsName, pyNodeName):
        self.info("translating %s / %s" % (apiClsName, pyNodeName))
        clsInfo = self.apiClassInfo[apiClsName]
        for apiMethodName, methodInfo in clsInfo['methods'].iteritems():
            self.doApiMethodKeyTranslation(apiClsName, pyNodeName, apiMethodName, methodInfo=methodInfo)

    def doApiMethodKeyTranslation(self, apiClsName, pyNodeName, apiMethodName, methodInfo=None):
        if methodInfo is None:
            methodInfo = self.apiClassInfo[apiClsName]['methods'][apiMethodName]

        # want to try both the "translated" pymelName, and using the
        # untranslated apiMethodName, because sometimes there's old data stored
        # for both...
        pyMethodNames = set([apiMethodName])
        try:
            pyMethodNames.add(methodInfo[0]['pymelName'])
        except KeyError:
            pass

        for pyMethodName in pyMethodNames:
            self.doApiKeyTranslation(apiClsName, pyNodeName, apiMethodName, pyMethodName)

        # also try the fully-translated pymel name, because it seems data
        # sometimes got mistakenly stored in apiToPyData using these
        # fully-translated names...
        fullyTranslatedName = factories._getApiOverrideNameAndData(apiClsName, pyNodeName, apiMethodName)[0]
        if fullyTranslatedName not in pyMethodNames:
            try:
                self.doApiKeyTranslation(apiClsName, pyNodeName, apiMethodName, pyMethodName)
            except WrapTranslateNewKeyError:
                # ...however, if there's a new-key conflict that arises when
                # doing this, it may be because there's actually another api
                # method with the translated name, so ignore it...
                pass


    def _doKeyTranslation(self, rootName, pyClsName, subName, pyMethodName,
                          oldData, sources, oldToNew, newToOld, deciders):
        # rootName is either the api class name, or the mel cmd name
        # subName is either the api method name, or the mel flag name
        oldKey = (pyClsName, pyMethodName)
        if isinstance(subName, tuple):
            newKey = (pyClsName,) + subName
        else:
            newKey = (pyClsName, subName)

        if pyClsName in self.TO_DELETE_CLASSES or oldKey in self.TO_DELETE_METHODS:
            self.deleted.add(oldKey)
            return

        self.info("checking %s[%s] (oldKey: %s)" % (rootName, subName, oldKey))

        if oldKey not in oldData:
            self.info("found no old key... skipping method...")
            return
        source = (rootName, subName)

        doAdd = False
        if oldKey in oldToNew:
            self.info("old key was already translated...")

            oldRoot, oldSub = sources[oldKey]

            better = self.preferred(pyClsName, oldRoot, oldSub, rootName, subName, deciders)
            if better is not None:
                # if one pick is clearly better, it doesn't matter if the newKey
                # has changed or not - update to use the better option
                if better == 2:
                    self.info("...and new source %s was preferred" % (source,))
                    # we only need to update if the better one is the new one
                    doAdd = True
                else:
                    self.info("...and old source %s was preferred" % (sources[oldKey],))
            else:
                self.info("...and no preferred key could be found...")
                #assert apiOldToNewKey[oldKey] == newKey, "oldKey: %s - orig newKey: %s - new newKey: %s - old source: %s - new source: %s" % (oldKey,
                #    apiOldToNewKey[oldKey], newKey, sources[oldKey], source)

                # nothing could be preferred... check that the new key has not
                # changed...
                if oldToNew[oldKey] != newKey:
                    oldSource = sources[oldKey]
                    print "old key conflict for %s" % (oldKey,)
                    print "orig newKey: %s - new newKey: %s" % (oldToNew[oldKey], newKey)
                    print "old source: %s - new source: %s" % (oldSource, source)

                    raise WrapTranslateOldKeyError('old key conflict')
                else:
                    self.info("...but new keys matched, so no conflict")

        else:
            self.info("...no old translation found")
            doAdd = True


        if doAdd:
            self._addKeyTranslation(oldKey, newKey, source, oldData, sources,
                                    oldToNew, newToOld)

    def doApiKeyTranslation(self, apiClsName, pyNodeName, apiMethodName,
                            pyMethodName):
        self._doKeyTranslation(apiClsName, pyNodeName, apiMethodName,
                               pyMethodName, self.apiToPyData,
                               self.apiTranslationSources, self.apiOldToNewKey,
                               self.apiNewToOldKey,
                               (self.apiWrappable, self.notDeprecated, self.apiWrapped))

    def doCmdsKeyTranslation(self, cmdName, pyNodeName, flag, cmdType,
                             pyMethodName):
        self._doKeyTranslation(cmdName, pyNodeName, (flag, cmdType),
                               pyMethodName, self.apiToPyData,
                               self.cmdsTranslationSources,
                               self.cmdsOldToNewKey, self.cmdsNewToOldKey,
                               (self.cmdWrapped,))

    def _addKeyTranslation(self, oldKey, newKey, source, oldData, sources,
                           oldToNew, newToOld):
        data = oldData[oldKey]
        otherOldKey = newToOld.get(newKey)

        if otherOldKey is not None:
            self.info("found two old keys - %s, %s - both mapping to same new key - %s" % (otherOldKey, oldKey, newKey))
            otherData = oldData[otherOldKey]
            if not self.apiMelDataEqual(data, otherData, oldKey[1]):
                print "data for old keys %s and %s did not match" % (otherOldKey, oldKey)
                print "newKey   : %s" % (newKey,)
                print "old key 1: %s" % (otherOldKey,)
                print otherData
                print "old key 2: %s" % (oldKey,)
                print data
                raise WrapTranslateNewKeyError('new key conflict')
            else:
                self.info("...but data matched, so it's ok")
        else:
            self.info("...adding data: oldKey: %s - newKey: %s - source: %s" % (oldKey, newKey, source))
            oldToNew[oldKey] = newKey
            newToOld[newKey] = oldKey
            sources[oldKey] = source

    def translateData(self):
        self.translateApiData()
        self.translateCmdData()

    def translateApiData(self):
        for clsName, cls in factories.pyNodeNamesToPyNodes.iteritems():
            apiCls = cls.__apicls__
            apiClsName = apiCls.__name__
            clsData = self.apiClassInfo[apiClsName]
            for apiMethodName, overloads in clsData['methods'].iteritems():
                for overloadIndex, methodData in enumerate(overloads):
                    pass


    def translateCmdData(self):
        for clsName, cls in factories.pyNodeNamesToPyNodes.iteritems():
            melCmdName, infoCmd = cls.__metaclass__.getMelCmd(cls.__dict__)
            try:
                cmdInfo = factories.cmdlist[melCmdName]
            except KeyError:
                continue
            for flag, flagInfo in cmdInfo['flags'].iteritems():
                clsName = cls.__name__
                for method, cmdType in cls.__metaclass__.flagToMethods(flag, flagInfo, infoCmd):
                    shouldBeWrapped = self.flagShouldBeWrapped('new', clsName, flag, cmdType)
                    wasWrapped = bool(factories.classToCmdMap.get(cls, {}).get(method))
                    shouldHaveBeenWrapped = self.flagShouldBeWrapped('old', clsName, flag, cmdType)
                    #assert wasWrapped == shouldHaveBeenWrapped, "pyNode: %s - cmd: %s - flag: %s - cmdType: %s - wasWrapped: %s - shouldHaveBeenWrapped: %s" % (clsName, melCmdName, flag, cmdType, wasWrapped, shouldHaveBeenWrapped)
                    if not shouldBeWrapped and wasWrapped:
                        data = self.newCmdsToPyData.setdefault((clsName, flag, cmdType), {})
                        if not self.apiToPyData.get((clsName, method), {}).get('melEnabled', False):
                            self.warn("enabled cmd method %s.%s" % (clsName, method))
                            data.setdefault('notes', []).append("enabled in auto-conversion from old apiToMelData")
                        data['enabled'] = True
                        self.newCmdsToPyData.setdefault((clsName, flag, cmdType), {})['enabled'] = True
                    elif shouldBeWrapped and not wasWrapped:
                        data = self.newCmdsToPyData.setdefault((clsName, flag, cmdType), {})
                        if self.apiToPyData.get((clsName, method), {}).get('melEnabled', True):
                            self.warn("disabled cmd method %s.%s" % (clsName, method))
                            data.setdefault('notes', []).append("disabled in auto-conversion from old apiToMelData")
                        data['enabled'] = False
                # we don't need to bother with 'useName', because old code
                # never bothered with it for mel cmds...

    def flagShouldBeWrapped(self, oldNew, clsName, flag, cmdType):
        self.debug("flagShouldBeWrapped(%r, %r, %r, %r)" % (oldNew, clsName, flag, cmdType))
        cls = getattr(pm.nt, clsName)
        melCmdName, infoCmd = cls.__metaclass__.getMelCmd(cls.__dict__)
        try:
            cmdInfo = factories.cmdlist[melCmdName]
        except KeyError:
            self.debug("False: no entry for %s in cmdlist" % melCmdName)
            return False

        filterAttrs = list(factories.filterCmdMethods)
        filterAttrs += '__doc__ __melcmd__ __melcmdname__ __melcmd_isinfo__'.split()
        # normally, parentClasses would be inspect.getmro(cls)[1:], because
        # you don't want to include this class... but, in this case, we're
        # checking if the flag should be wrapped, AFTER it may already have
        # been wrapped... and including ourself in the parent classes will
        # allow melMethodWrappable_* to check if the existing attribute is
        # a melMethod...
        parentClasses = inspect.getmro(cls)
        for parent in parentClasses:
            filterAttrs += factories.overrideMethods.get(parent.__name__, [])

        try:
            flagInfo = cmdInfo['flags'][flag]
        except KeyError:
            self.debug("False: no entry for %s in flags" % flag)
            return False

        if flag in ['query', 'edit'] or 'modified' in flagInfo:
            self.debug("False: flag was query or edit, or modified in flagInfo")
            return False

        method = None
        for testName, testType in cls.__metaclass__.flagToMethods(flag, flagInfo, infoCmd):
            if cmdType == testType:
                method = testName
                break

        if method is None:
            self.debug("False: no cmdType %s" % cmdType)
            return False

        if oldNew == 'old':
#            # weird quirk of melMethodWrappable_old - since api methods are
#            # constructed first, and creation of api methods calls
#            # _getApiOverrideNameAndData, which can create "default" entries in
#            # apiToPyData, and melMethodWrappable_old does a
#            #    apiToPyData.has_key((classname, methodName))
#            # check... the fact that api wraps are done first can change things
#            # therefore, if we're not using factories.apiToPydata, we need
#            # to account for this...
#            apiToPyData = self.apiToPyData
#            if self.apiToPyData != factories.apiToPyData:
#                if (clsName, method) not in apiToPyData:
#                    # check if there is an api wrap that would translate to the same
#                    # name...
#                    apicls = cls.__apicls__
#                    apiName = apicls.__name__
#                    clsInfo = factories.apiClassInfo[apiName]


            self.debug("calling: melMethodWrappable_old(%r, %r, %r, %r, %r, apiToPyData=self.apiToPyData)" % (cls, method, cmdType, parentClasses, filterAttrs))
            return factories._MetaMayaCommandWrapper.melMethodWrappable_old(cls,
                                                                method,
                                                                cmdType,
                                                                parentClasses,
                                                                filterAttrs,
                                                                apiToPyData=self.apiToPyData)
        elif oldNew == 'new':
            self.debug("calling: melMethodWrappable_new(%r, %r, %r, parentClasses=%r, filterAttrs=%r, cmdsToPyData={})" % (cls, method, cmdType, parentClasses, filterAttrs))
            return factories._MetaMayaCommandWrapper.melMethodWrappable_new(cls,
                                                                method,
                                                                cmdType,
                                                                parentClasses=parentClasses,
                                                                filterAttrs=filterAttrs,
                                                                cmdsToPyData={})


    @classmethod
    def apiMelDataEqual(cls, data1, data2, pyMethodName):
        if data1 == data2:
            return True
        data1 = dict(data1)
        data2 = dict(data2)
        for data in data1, data2:
            # don't do overloadIndex, as it's 'default' is tricky - before
            # pymelControlPanel is run, it's default is None... once
            # pymelControl panel is run, it's set to the first wrappable
            # overload it finds (or None if none are found), so that could be
            # considered it's default as well...
            data.setdefault('useName', 'API')
            data.setdefault('enabled',
                            pyMethodName not in factories.EXCLUDE_METHODS)
        return data1 == data2

    def apiWrappable(self, pyClsName, apiClassName, apiMethodName):
        for i in xrange(len(self.apiClassInfo[apiClassName]['methods'][apiMethodName])):
            argHelper = factories.ApiArgUtil(apiClassName, apiMethodName, i)
            if argHelper.canBeWrapped():
                return True
        return False

    def notDeprecated(self, pyClsName, apiClassName, apiMethodName):
        for i, overloadInfo in enumerate(self.apiClassInfo[apiClassName]['methods'][apiMethodName]):
            argHelper = factories.ApiArgUtil(apiClassName, apiMethodName, i)
            if argHelper.canBeWrapped() and not overloadInfo.get('deprecated', False):
                return False
        return True

    def apiWrapped(self, pyClsName, apiClassName, apiMethodName):
        if not hasattr(factories, '_wrappedApiMethods'):
            return None
        return (apiClassName, apiMethodName) in factories._wrappedApiMethods

    def cmdWrapped(self, pyClsName, cmdName, flagAndCmdType):
        cls = factories.pyNodeNamesToPyNodes[pyClsName]
        data = factories.classToCmdMap.get(cls)
        if data is None:
            return False
        key = (cmdName,) + flagAndCmdType
        return key in data.itervalues()

    def preferred(self, pyClsName, root1, sub1, root2, sub2, deciders):
        better = None
        for decider in deciders:
            good1 = decider(pyClsName, root1, sub1)
            good2 = decider(pyClsName, root2, sub2)
            if good1 != good2:
                if good1:
                    better = 1
                else:
                    better = 2
                break
        return better

    def writeTranslatedCache(self):
        cacheObj= apicache.ApiMelBridgeCache()
        oldCache = cacheObj.read()
        newCache = (self.newApiToPyData, self.newCmdsToPyData, oldCache[1])
        cacheObj.write(newCache)
