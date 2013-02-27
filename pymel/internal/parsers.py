import re, os.path, platform
from HTMLParser import HTMLParser
import pymel.util as util
import pymel.versions as versions
import plogging
from pymel.mayautils import getMayaLocation

try:
    from pymel.util.external.BeautifulSoup import BeautifulSoup, NavigableString, Comment
except ImportError:
    from BeautifulSoup import BeautifulSoup, NavigableString, Comment
from keyword import iskeyword as _iskeyword

FLAGMODES = ('create', 'query', 'edit', 'multiuse')

_logger = plogging.getLogger(__name__)

def mayaIsRunning():
    """
    Returns True if maya.cmds have  False otherwise.

    Early in interactive startup it is possible for commands to exist but for Maya to not yet be initialized.

    :rtype: bool
    """

    # Implementation is essentially just a wrapper for getRunningMayaVersionString -
    # this function was included for clearer / more readable code

    try :
        from maya.cmds import about
        about(version=True)
        return True
    except :
        return False

def mayaDocsLocation(version=None):
    docLocation = os.environ.get('MAYA_DOC_DIR')

    if (not docLocation and (version is None or version == versions.installName() )
            and mayaIsRunning()):
        # Return the doc location for the running version of maya
        from maya.cmds import showHelp
        docLocation = showHelp("", q=True, docs=True)

        # Older implementations had no trailing slash, but the result returned by
        # showHelp has a trailing slash... so eliminate any trailing slashes for
        # consistency
        while docLocation != "" and os.path.basename(docLocation) == "":
            docLocation = os.path.dirname(docLocation)

    # Want the docs for a different version, or maya isn't initialized yet
    if not docLocation or not os.path.isdir(docLocation):
        docBaseDir = os.environ.get('MAYA_DOC_BASE_DIR')
        if not docBaseDir:
            docBaseDir = getMayaLocation(version) # use original version
            if docBaseDir is None and version is not None:
                docBaseDir = getMayaLocation(None)
                _logger.warning("Could not find an installed Maya for exact version %s, using first installed Maya location found in %s" % (version, docBaseDir) )

            if platform.system() == 'Darwin':
                docBaseDir = os.path.dirname(os.path.dirname(docBaseDir))
            docBaseDir = os.path.join(docBaseDir, 'docs')

        if version:
            short_version = versions.parseVersionStr(version, extension=False)
        else:
            short_version = versions.shortName()
        docLocation = os.path.join(docBaseDir , 'Maya%s' % short_version, 'en_US')

    return os.path.realpath(docLocation)

#---------------------------------------------------------------
#        Doc Parser
#---------------------------------------------------------------
class CommandDocParser(HTMLParser):

    def __init__(self, command):
        self.command = command
        self.flags = {}  # shortname, args, docstring, and a list of modes (i.e. edit, create, query)
        self.currFlag = ''
        # iData is used to track which type of data we are putting into flags, and corresponds with self.datatypes
        self.iData = 0
        self.pcount = 0
        self.active = False  # this is set once we reach the portion of the document that we want to parse
        self.description = ''
        self.example = ''
        self.emptyModeFlags = [] # when flags are in a sequence ( lable1, label2, label3 ), only the last flag has queryedit modes. we must gather them up and fill them when the last one ends
        HTMLParser.__init__(self)

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self.command)

    def startFlag(self, data):
        #_logger.debug(self, data)
        #assert data == self.currFlag
        self.iData = 0
        self.flags[self.currFlag] = {'longname': self.currFlag, 'shortname': None, 'args': None,
                                     'numArgs': None, 'docstring': '', 'modes': [] }

    def addFlagData(self, data):
        # encode our non-unicode 'data' string to unicode
        data = data.decode('utf-8')
        # now saftely encode it to non-unicode ascii, ignorning unknown characters
        data = data.encode('ascii', 'ignore')
        # Shortname
        if self.iData == 0:
            self.flags[self.currFlag]['shortname'] = data.lstrip('-\r\n')

        # Arguments
        elif self.iData == 1:
            typemap = {
             'string'  : unicode,
             'float'   : float,
             'double'  : float,
             'linear'  : float,
             'angle'   : float,
             'int'     : int,
             'uint'    : int,
             'int64'   : int,
             'index'   : int,
             'integer'  : int,
             'boolean'  : bool,
             'script'   : 'script',
             'name'     : 'PyNode',
             'select'   : 'PyNode',
             'time'     : 'time',
             'timerange': 'timerange',
             'floatrange':'floatrange',
             '...'      : '...' # means that there is a variable number of args. we don't do anything with this yet
            }
            args = [x.strip() for x in data.replace('[', '').replace(']', '').split(',') if x.strip()]
            for i, arg in enumerate(args):
                if arg not in typemap:
                    _logger.error("%s: %s: unknown arg type %r" % (self, self.currFlag, arg))
                else:
                    args[i] = typemap[arg]
            numArgs = len(args)
            if numArgs == 0:
                args = bool
                #numArgs = 1
                # numArgs will stay at 0, which is the number of mel arguments.
                # this flag should be renamed to numMelArgs
            elif numArgs == 1:
                args = args[0]

            self.flags[self.currFlag]['args'] = args
            self.flags[self.currFlag]['numArgs'] = numArgs

        # Docstring
        else:
            #self.flags[self.currFlag]['docstring'] += data.replace( '\r\n', ' ' ).strip() + " "
            data = data.replace( 'In query mode, this flag needs a value.', '' )
            data = data.replace( 'Flag can appear in Create mode of command', '' )
            data = data.replace( 'Flag can appear in Edit mode of command', '' )
            data = data.replace( 'Flag can appear in Query mode of command', '' )
            data = data.replace( '\r\n', ' ' ).lstrip()
            data = data.replace( '\n', ' ' ).lstrip()
            data = data.strip('{}\t')
            data = data.replace('*', '\*') # for reStructuredText
            self.flags[self.currFlag]['docstring'] += data
        self.iData += 1

    def endFlag(self):
        # cleanup last flag
        #data = self.flags[self.currFlag]['docstring']

        #_logger.debug(("ASSERT", data.pop(0), self.currFlag))
        try:
            if not self.flags[self.currFlag]['modes']:
                self.emptyModeFlags.append(self.currFlag)
            elif self.emptyModeFlags:
                    #_logger.debug("past empty flags:", self.command, self.emptyModeFlags, self.currFlag)
                    basename = re.match( '([a-zA-Z]+)', self.currFlag ).groups()[0]
                    modes = self.flags[self.currFlag]['modes']
                    self.emptyModeFlags.reverse()
                    for flag in self.emptyModeFlags:
                        if re.match( '([a-zA-Z]+)', flag ).groups()[0] == basename:
                            self.flags[flag]['modes'] = modes
                        else:
                            break

                    self.emptyModeFlags = []
        except KeyError, msg:
            pass
            #_logger.debug(self.currFlag, msg)

    def handle_starttag(self, tag, attrs):
        #_logger.debug("begin: %s tag: %s" % (tag, attrs))
        attrmap = dict(attrs)
        if not self.active:
            if tag == 'a':
                name = attrmap.get('name', None)
                if name == 'hFlags':
                    #_logger.debug('ACTIVE')
                    self.active = 'flag'
                elif name == 'hExamples':
                    #_logger.debug("start examples")
                    self.active = 'examples'
        elif tag == 'a' and 'name' in attrmap:
            self.endFlag()
            newFlag = attrmap['name'][4:]
            newFlag = newFlag.lstrip('-')
            self.currFlag = newFlag
            self.iData = 0
            #_logger.debug("NEW FLAG", attrs)
            #self.currFlag = attrs[0][1][4:]

        elif tag == 'img':
            mode = attrmap.get('title', None)
            if mode in FLAGMODES:
                #_logger.debug("MODES", attrs[1][1])
                self.flags[self.currFlag]['modes'].append(mode)
        elif tag == 'h2':
            self.active = False

    def handle_endtag(self, tag):
        #if tag == 'p' and self.active == 'command': self.active = False
        #_logger.debug("end: %s" % tag)
        if not self.active:
            if tag == 'p':
                if self.pcount == 3:
                    self.active = 'command'
                else:
                    self.pcount += 1
        elif self.active == 'examples' and tag == 'pre':
            self.active = False

    def handle_entityref(self,name):
        if self.active == 'examples':
            self.example += r'"'

    def handle_data(self, data):
        if not self.active:
            return
        elif self.active == 'flag':
            if self.currFlag:
                stripped = data.strip()
                if stripped == 'Return value':
                    self.active=False
                    return

                if data and stripped and stripped not in ['(',')', '=', '], [']:
                    #_logger.debug("DATA", data)

                    if self.currFlag in self.flags:
                        self.addFlagData(data)
                    else:
                        self.startFlag(data)
        elif self.active == 'command':
            data = data.replace( '\r\n', ' ' )
            data = data.replace( '\n', ' ' )
            data = data.lstrip()
            data = data.strip('{}')
            data = data.replace('*', '\*') # for reStructuredText
            if '{' not in data and '}' not in data:
                self.description += data
            #_logger.debug(data)
            #self.active = False
        elif self.active == 'examples' and data != 'Python examples':
            #_logger.debug("Example\n")
            #_logger.debug(data)
            data = data.replace( '\r\n', '\n' )
            self.example += data
            #self.active = False


# class MayaDocsLoc(str) :
#    """ Path to the Maya docs, cached at pymel start """
#    __metaclass__ = util.Singleton

# TODO : cache doc location or it's evaluated for each getCmdInfo !
# MayaDocsLoc(mayaDocsLocation())

class NodeHierarchyDocParser(HTMLParser):

    def parse(self):
        docloc = mayaDocsLocation(self.version)
        if not os.path.isdir( docloc ):
            raise IOError, "Cannot find maya documentation. Expected to find it at %s" % docloc

        f = open( os.path.join( docloc , 'Nodes/index_hierarchy.html' ) )
        try:
            rawdata = f.read()
        finally:
            f.close()

        if versions.v2011 <= versions.current() < versions.v2012:
            # The maya 2011 doc doesn't parse correctly with HTMLParser - the
            # '< < <' lines get left out.  Use beautiful soup instead.
            soup = BeautifulSoup( rawdata, convertEntities='html' )
            for tag in soup.findAll(['tt', 'a']):
                # piggypack on current handle_starttag / handle_data
                self.handle_starttag(tag.name, tag.attrs)
                data = tag.string
                if data is not None:
                    self.handle_data(data)
        else:
            self.feed( rawdata )
        return self.tree

    def __init__(self, version=None):
        self.version = version
        self.currentTag = None
        self.depth = 0
        self.lastDepth = -1
        self.tree = None
        self.currentLeaves = []

        HTMLParser.__init__(self)
    def handle_starttag(self, tag, attrs):
        #_logger.debug("%s - %s" % (tag, attrs))
        self.currentTag = tag

    def handle_data(self, data):
        _logger.debug("data %r" % data)
        if self.currentTag == 'tt':
            self.depth = data.count('>')
            #_logger.debug("lastDepth: %s - depth: %s" % (self.lastDepth, self.depth))

        elif self.currentTag == 'a':
            data = data.lstrip()

            if self.depth == 0:
                if self.tree is None:
                    #_logger.debug("starting brand new tree: %s %s" % (self.depth, data))
                    self.tree = [data]
                else:
                    #_logger.debug("skipping %s", data)
                    return

            elif self.depth == self.lastDepth and self.depth > 0:
                #_logger.debug("adding to current level", self.depth, data)
                self.tree[ self.depth ].append( data )

            elif self.depth > self.lastDepth:
                #_logger.debug("starting new level: %s %s" % (self.depth, data))
                self.tree.append( [data] )

            elif self.depth < self.lastDepth:

                    for i in range(0, self.lastDepth-self.depth):
                        branch = self.tree.pop()
                        #_logger.debug("closing level %s - %s - %s" % (self.lastDepth, self.depth, self.tree[-1]))
                        currTree = self.tree[-1]
                        #if isinstance(currTree, list):
                        currTree.append( branch )
                        #else:
                        #    _logger.info("skipping", data)
                        #    self.close()
                        #    return

                    #_logger.debug("adding to level", self.depth, data)
                    self.tree[ self.depth ].append( data )
            else:
                return
            self.lastDepth = self.depth
            # with 2009 and the addition of the MPxNode, the hierarchy closes all the way out ( i.e. no  >'s )
            # this prevents the depth from getting set properly. as a workaround, we'll set it to 0 here,
            # then if we encounter '> >' we set the appropriate depth, otherwise it defaults to 0.
            self.depth = 0


def printTree( tree, depth=0 ):
    for branch in tree:
        if util.isIterable(branch):
            printTree( branch, depth+1)
        else:
            _logger.info('%s %s' % ('> '*depth,  branch))


class CommandModuleDocParser(HTMLParser):

    def parse(self):

        f = open( os.path.join( self.docloc , 'Commands/cat_' + self.category + '.html' ) )
        self.feed( f.read() )
        f.close()
        return self.cmdList

    def __init__(self, category, version=None ):
        self.cmdList = []
        self.category = category
        self.version = version

        docloc = mayaDocsLocation( '2009' if self.version=='2008' else self.version)
        self.docloc = docloc
        HTMLParser.__init__(self)

    def handle_starttag(self, tag, attrs):
        try:
            attrs = attrs[0]
            #_logger.debug(attrs)
            if tag == 'a' and attrs[0]=='href':
                cmd = attrs[1].split("'")[1].split('.')[0]
                self.cmdList.append( cmd )
                #_logger.debug(cmd)
        except IndexError: return

def findText(tag):
    return [x.encode('ascii', 'ignore') for x in tag.findAll(text=True)
            if not isinstance(x, Comment)]


class ApiDocParser(object):
    class CurrentMethodSetter(object):
        def __init__(self, apiDocParser, method):
            self.apiDocParser = apiDocParser
            self.method = method

        def __enter__(self):
            self.savedMethod = self.apiDocParser.currentMethod
            self.apiDocParser.currentMethod = self.method

        def __exit__(self, exc_type, exc_value, tb):
            self.apiDocParser.currentMethod = self.savedMethod


    OBSOLETE_MSGS = ['NO SCRIPT SUPPORT.', 'This method is not available in Python.']
    OBSOLETE_RE = re.compile('|'.join(re.escape(x) for x in OBSOLETE_MSGS))
    DEPRECATED_MSG = ['This method is obsolete.', 'Deprecated:']

    # in enums with multiple keys per int value, which (pymel) key name to use
    # as the default - ie, in MSpace, both object and preTransformed map to 2;
    # since 'object' is in PYMEL_ENUM_DEFAULTS['Space'], that is preferred
    PYMEL_ENUM_DEFAULTS = {'Space':('object',)}

    def __init__(self, apiModule, version=None, verbose=False, enumClass=tuple,
                 docLocation=None):
        self.version = versions.installName() if version is None else version
        self.apiModule = apiModule
        self.verbose = verbose
        if docLocation is None:
            docLocation = mayaDocsLocation('2009' if self.version=='2008' else self.version)
        self.docloc = docLocation
        self.enumClass = enumClass
        if not os.path.isdir(self.docloc):
            raise IOError, "Cannot find maya documentation. Expected to find it at %s" % self.docloc

        self.enums = {}
        self.pymelEnums = {}
        self.methods=util.defaultdict(list)
        self.currentMethod=None
        self.badEnums = []

    def formatMsg(self, *args):
        return self.apiClassName + '.' + self.currentMethod + ': ' + ' '.join( [ str(x) for x in args ] )

    def xprint(self, *args):
        if self.verbose:
            print self.formatMsg(*args)

    def methodSetter(self, method):
        return self.CurrentMethodSetter(self, method)

    def isMayaConstant(self, name):
        if name.startswith('k') and len(name) >= 2 and name[1].isupper():
            return hasattr(self.apiModule, name)
        return False

    def getPymelMethodNames(self):


        setReg = re.compile('set([A-Z].*)')

        allFnMembers = self.methods.keys()
        pymelNames = {}
        pairs = {}
        pairsList = []

        def addSetGetPair(setmethod, getMethod):
            pairsList.append( (setMethod,getMethod) )
            # pair 'set' with 'is/get'
            pairs[setMethod] = getMethod
            for info in self.methods[setMethod]:
                info['inverse'] = (getMethod, True)

            # pair 'is/get' with 'set'
            pairs[getMethod] = setMethod
            for info in self.methods[getMethod]:
                info['inverse'] = (setMethod, False)

        for member in allFnMembers:
            m = setReg.match(member)
            if m:
                # MFn api naming convention usually uses setValue(), value() convention for its set and get methods, respectively
                # setSomething()  &  something()  becomes  setSomething() & getSomething()
                # setIsSomething() & isSomething() becomes setSomething() & isSomething()
                basename = m.group(1)
                origGetMethod = util.uncapitalize(basename)
                setMethod = member  # for name clarity
                if origGetMethod in allFnMembers:
                    # fix set
                    if re.match( 'is[A-Z].*', origGetMethod):
                        newSetMethod = 'set' + origGetMethod[2:] # remove 'is' #member[5:]
                        pymelNames[setMethod] = newSetMethod
                        for info in self.methods[setMethod]:
                            info['pymelName'] = newSetMethod
                        addSetGetPair( setMethod, origGetMethod)


                    # fix get
                    else:
                        newGetMethod = 'g' + setMethod[1:] # remove 's'
                        pymelNames[origGetMethod] = newGetMethod
                        for info in self.methods[origGetMethod]:
                            info['pymelName'] = newGetMethod
                        addSetGetPair( setMethod, origGetMethod)


                else:
                    getMethod = 'get' + basename
                    isMethod = 'is' + basename
                    if getMethod in allFnMembers:
                        addSetGetPair( setMethod, getMethod )
                    elif isMethod in allFnMembers:
                        addSetGetPair( setMethod, isMethod )

        return pymelNames, pairsList



    def getClassFilename(self):
        filename = 'class'
        for tok in re.split( '([A-Z][a-z]*)', self.apiClassName ):
            if tok:
                if tok[0].isupper():
                    filename += '_' + tok.lower()
                else:
                    filename += tok
        return filename

    _capitalizedRe = re.compile('([A-Z0-9][a-z0-9]*)')

    def _apiEnumNamesToPymelEnumNames(self, apiEnumNames):
        """remove all common prefixes from list of enum values"""
        if isinstance(apiEnumNames, util.Enum):
            apiEnumNames = apiEnumNames._keys.keys()
        if len(apiEnumNames) > 1:
            # We first aim to remove all similar 'camel-case-group' prefixes, ie:
            # if our enums look like:
            #    kFooBar
            #    kFooSomeThing
            #    kFooBunnies
            # we want to get Bar, SomeThing, Bunnies

            # {'kFooBar':0, 'kFooSomeThing':1}
            #     => [['k', 'Foo', 'Some', 'Thing'], ['k', 'Foo', 'Bar']]
            splitEnums = [ [ y for y in self._capitalizedRe.split( x ) if y ] for x in apiEnumNames ]

            # [['k', 'Invalid'], ['k', 'Pre', 'Transform']]
            #     => [('k', 'k'), ('Foo', 'Foo'), ('Some', 'Bar')]
            splitZip = zip( *splitEnums )
            for partList in splitZip:
                if  tuple([partList[0]]*len(partList)) == partList:
                    [ x.pop(0) for x in splitEnums ]
                else: break
            # splitEnums == [['Some', 'Thing'], ['Bar']]

            joinedEnums = [ util.uncapitalize(''.join(x), preserveAcronymns=True ) for x in splitEnums]
            for i, enum in enumerate(joinedEnums):
                if _iskeyword(enum):
                    joinedEnums[i] = enum+'_'
                    self.xprint( "bad enum", enum )
                elif enum[0].isdigit():
                    joinedEnums[i] = 'k' + enum
                    self.xprint( "bad enum", enum )

                    #print joinedEnums
                    #print enumList
                    #break

            return dict(zip(apiEnumNames, joinedEnums))
        else:
            # if only 1 name or less, name is unaltered
            return dict((name, name) for name in apiEnumNames)

    def _apiEnumToPymelEnum(self, apiEnum, apiToPymelNames=None):
        defaultsSet = self.PYMEL_ENUM_DEFAULTS.get(apiEnum.name, set())
        defaults = {}
        if apiToPymelNames is None:
            apiToPymelNames = self._apiEnumNamesToPymelEnumNames(apiEnum)
        pymelKeyDict = {}
        docs = dict(apiEnum._docs)
        for apiName, val in apiEnum._keys.iteritems():
            # want to include docs, so make dict (key, doc) => val
            pymelKeyDict[apiName] = val
            pymelName = apiToPymelNames[apiName]
            pymelKeyDict[pymelName] = val

            doc = apiEnum._docs.get(apiName)
            if doc:
                docs[pymelName] = doc

            # in the pymel dict, the pymel name should always be the default
            # key for a value... but the original dict may also have multiple
            # keys for a value... so:
            #   if there is an entry in PYMEL_ENUM_DEFAULTS for this
            #     class/pymelName, then use that as the default
            #   otherwise, use the pymel equivalent of whatever the original
            #     api default was
            if (pymelName in defaultsSet
                    # need to check val not in defaults, or else we can override
                    # a value set due to defaultsSet
                    or (val not in defaults and apiName == apiEnum.getKey(val))):
                defaults[val] = pymelName
        return util.Enum(apiEnum.name, pymelKeyDict, multiKeys=True,
                         defaultKeys=defaults)

    def handleEnums( self, type ):
        missingTypes = ['MUint64']
        otherTypes = ['void', 'char', 'uchar',
                    'double', 'double2', 'double3', 'double4',
                    'float', 'float2', 'float3', 'float4',
                    'bool',
                    'int', 'int2', 'int3', 'int4',
                    'uint', 'uint2', 'uint3', 'uint4',
                    'short', 'short2', 'short3', 'short4',
                    'long', 'long2', 'long3',
                    'MString', 'MStringArray', 'MStatus']
        notTypes = ['MCallbackId']

        if type is None: return type

        # the enum is on another class
        if '::' in type:
            type = self.enumClass( type.split( '::') )

        # the enum is on this class
        elif type in self.enums:
            type = self.enumClass( [self.apiClassName, type] )

        elif type[0].isupper() and 'Ptr' not in type and not hasattr( self.apiModule, type ) and type not in otherTypes+missingTypes+notTypes:
            type = self.enumClass( [self.apiClassName, type] )
            if type not in self.badEnums:
                self.badEnums.append(type)
                _logger.warn( "Suspected Bad Enum: %s", type )
        else:
            type = str(type)
        return type

    def handleEnumDefaults( self, default, type ):

        if default is None: return default

        if isinstance( type, self.enumClass ):

            # the enum is on another class
            if '::' in default:
                apiClass, enumConst = default.split( '::')
                assert apiClass == type[0]
            else:
                enumConst = default

            return self.enumClass([type[0], type[1], enumConst])

        return default

    def getOperatorName(self, methodName):
        op = methodName[8:]
        #print "operator", methodName, op
        if op == '=':
            methodName = None
        else:

            methodName = {
                '*=' : '__rmult__',
                '*'  : '__mul__',
                '+=' : '__radd__',
                '+'  : '__add__',
                '-=' : '__rsub__',
                '-'  : '__sub__',
                '/=' : '__rdiv__',
                '/'  : '__div__',
                '==' : '__eq__',
                '!=' : '__neq__',
                '[]' : '__getitem__'}.get( op, None )
        return methodName

    def isSetMethod(self):
        if re.match( 'set[A-Z]', self.currentMethod ):
            return True
        else:
            return False

    def isGetMethod(self):
        if re.match( 'get[A-Z]', self.currentMethod ):
            return True
        else:
            return False

    def parseType(self, tokens):
        i=0
        for i, each in enumerate(tokens):
            if each not in self.KNOWN_QUALIFIERS:
                argtype = tokens.pop(i)
                break
        else:
            # We didn't find any arg type - therefore everything
            # in buf is in the set('*', '&', 'const', 'unsigned')
            # ... so it's implicitly an unsigned int
            argtype = 'int'

        if 'unsigned' in tokens and argtype in self.UNSIGNED_PREFIX_TYPES:
            argtype = 'u' + argtype

        argtype = self.handleEnums(argtype)
        return argtype, tokens

    def parseTypes(self, proto):
        defaults={}
        names=[]
        types ={}
        typeQualifiers={}

        for argNum, paramtype in enumerate(proto.findAll('td', 'paramtype')):
            buf = []
            # TYPES
            [ buf.extend(x.split()) for x in findText(paramtype) ] #if x.strip() not in ['', '*', '&', 'const', 'unsigned'] ]
            typebuf = [ x.strip().encode('ascii', 'ignore') for x in buf if x.strip() ]

            # ARGUMENT NAMES
            paramname = paramtype.parent.find('td', 'paramname')
            if paramname is None:
                raise ValueError('error parsing %r - could not find paramname for %r' % (proto, paramtype))

            namebuf = [ x.strip() for x in findText(paramname) if x.strip() not in['',','] ]

            self.addParamDef(self.parseParamDef(typebuf, namebuf), names, types,
                             typeQualifiers, defaults, defaultName='arg%d' % argNum)
        assert sorted(names) == sorted(types.keys()), 'name-type mismatch %s %s' %  (sorted(names), sorted(types.keys()) )
        return names, types, typeQualifiers, defaults

    def parseParamDef(self, typebuf, namebuf):
        if not typebuf and not namebuf:
            return None
        type, qualifiers = self.parseType(typebuf)
        if type == 'void':
            return None

        if not namebuf:
            argname = None
            data = []
        else:
            argname = namebuf[0]
            data = namebuf[1:]

        default=None
        joined = ''.join(data).strip()

        # need to return a dict, because we need a way to NOT return a default
        # ...ie, differentiate between no default specified, and a default
        # which WAS given, but evaluates to None
        results = {}

        if joined:
            joined = joined.encode('ascii', 'ignore')
            # break apart into index and defaults :  '[3] = NULL'
            brackets, default = re.search( '([^=]*)(?:\s*=\s*(.*))?', joined ).groups()

            if brackets:
                numbuf = re.split( r'\[|\]', brackets)
                if len(numbuf) > 1:
                    # Note that these two args need to be cast differently:
                    #   int2 foo;
                    #   int bar[2];
                    # ... so, instead of storing the type of both as
                    # 'int2', we make the second one 'int__array2'
                    type = type + '__array' + numbuf[1]
                else:
                    print "this is not a bracketed number", repr(brackets), joined

            if default is not None:
                try:
                    # Constants
                    default = {
                        'true' : True,
                        'false': False,
                        'NULL' : None
                    }[default]
                except KeyError:
                    if self.isMayaConstant(default):
                        default = getattr(self.apiModule, default)
                    else:
                        try:
                            if type in ['int', 'uint','long', 'uchar']:
                                default = int(default)
                            elif type in ['float', 'double']:
                                # '1.0 / 24.0'
                                if '/' in default:
                                    default = eval(default)
                                # '1.0e-5F'  --> '1.0e-5'
                                elif default.endswith('F'):
                                    default = float(default[:-1])
                                else:
                                    default = float(default)
                            else:
                                default = self.handleEnumDefaults(default, type)
                        except ValueError:
                            default = self.handleEnumDefaults(default, type)
                # default must be set here, because 'NULL' may be set to back to None, but this is in fact the value we want
                self.xprint('DEFAULT', default)
                results['default'] = default

        results['name'] = argname
        results['type'] = type
        results['qualifiers'] = qualifiers
        return results

    def addParamDef(self, paramInfo, argNames, argTypes, typeQualifiers,
                    defaults, defaultName=None):
        if paramInfo is None:
            return
        argname = paramInfo['name']
        if argname is None and defaultName is not None:
            argname = defaultName
        argTypes[argname] = paramInfo['type']
        typeQualifiers[argname] = paramInfo['qualifiers']
        argNames.append(argname)
        if 'default' in paramInfo:
            defaults[argname] = paramInfo['default']

    def parseEnums(self, proto):
        enumValues={}
        enumDocs={}
        for em in proto.findNextSiblings( 'div', limit=1)[0].findAll( 'em'):
            enumKey = str(em.contents[-1])
            try:
                enumVal = getattr(self.apiClass, enumKey)
            except:
                _logger.warn( "%s.%s of enum %s does not exist" % ( self.apiClassName, enumKey, self.currentMethod))
                enumVal = None
            enumValues[ enumKey ] = enumVal
            # TODO:
            # do we want to feed the docstrings to the Enum object itself
            # (which seems to have support for docstrings)? Currently, we're
            # not...
            docItem = em.next.next.next.next.next

            if isinstance( docItem, NavigableString ):
                enumDocs[enumKey] = str(docItem).strip()
            else:
                enumDocs[enumKey] = str(docItem.contents[0]).strip()

        apiEnum = util.Enum(self.currentMethod, enumValues, multiKeys=True)
        apiToPymelNames = self._apiEnumNamesToPymelEnumNames(apiEnum)
        pymelEnum = self._apiEnumToPymelEnum(apiEnum,
                                             apiToPymelNames=apiToPymelNames)
        for apiName, pymelName in apiToPymelNames.iteritems():
            apiDoc = enumDocs.get(apiName)
            if apiDoc is not None:
                enumDocs[pymelName] = apiDoc

        enumInfo = {'values' : apiEnum,
                    'valueDocs' : enumDocs,

                      #'doc' : methodDoc
                    }
        return enumInfo, pymelEnum

    def isProto(self, tag):
        return tag.name == 'div' and dict(tag.attrs).get('class') == 'memproto'

    def isObsolete(self, tag):
        # check if it's a 'proto' tag, in which case we need to check it's
        # addendum sibling
        if self.isProto(tag):
            # ARGUMENT DIRECTION AND DOCUMENTATION
            tag = tag.findNextSiblings( 'div', limit=1)[0]

        if tag.find(text=self.OBSOLETE_RE):
            self.xprint( "OBSOLETE" )
            return True
        return False

    def parseMethodArgs(self, proto, returnType, names, types, typeQualifiers):
        directions={}
        docs={}
        deprecated = False
        returnDoc = ''

        addendum = proto.findNextSiblings( 'div', 'memdoc', limit=1)[0]
        #if self.currentMethod == 'createColorSet': raise NotImplementedError
        if addendum.findAll( text=lambda x: x in self.DEPRECATED_MSG ):
            self.xprint( "DEPRECATED" )
            #print self.apiClassName + '.' + self.currentMethod + ':' + ' DEPRECATED'
            deprecated = True

        methodDoc = addendum.p
        if methodDoc:
            methodDoc = ' '.join( findText(methodDoc) )
        else:
            methodDoc = ''

        tmpDirs = []
        tmpNames = []
        tmpDocs = []

        #extraInfo = addendum.dl.table
        #if self.version and int(self.version.split('-')[0]) < 2013:

        # 2012 introduced a new Doxygen version, which changed the api doc
        # format; also, even in 2013/2014, some pre-release builds of he docs
        # have used the pre-2012 format; so we can't just go by maya version...
        format2012 = self.doxygenVersion >= (1,7)

        if format2012:
            extraInfos = addendum.findAll('table', **{'class':'params'})
        else:
            #extraInfos = addendum.findAll(lambda tag: tag.name == 'table' and ('class', 'params') in tag.attrs)
            extraInfos = addendum.findAll(lambda tag: tag.name == 'dl' and ('class', 'return') not in tag.attrs and ('class', 'user') not in tag.attrs)
        if extraInfos:
            #print "NUMBER OF TABLES", len(extraInfos)
            if format2012:
                for extraInfo in extraInfos:
                    for tr in extraInfo.findAll('tr', recursive=False):
                        assert tr, "could not find name tr"
                        tds = tr.findAll('td', recursive=False)
                        assert tds, "could not find name td"
                        assert len(tds) == 3, "td list is unexpected length: %d" % len(tds)

                        paramDir = tds[0]
                        paramName = tds[1]

                        assert dict(paramDir.attrs).get('class') == 'paramdir', "First element in param table row was not a paramdir"
                        assert dict(paramName.attrs).get('class') == 'paramname', "Second element in param table row was not a paramname"

                        tmpDirs.append(paramDir.find(text=True).encode('ascii', 'ignore'))
                        tmpNames.append(paramName.find(text=True).encode('ascii', 'ignore'))
                        doc = ''.join(findText(tds[2]))
                        tmpDocs.append(doc)
            else:
                for extraInfo in extraInfos:
                    for tr in extraInfo.findAll( 'tr'):
                        assert tr, "could not find name tr"
                        tds = tr.findAll('td')
                        assert tds, "could not find name td"
                        assert len(tds) == 3, "td list is unexpected length: %d" % len(tds)

                        tt = tds[0].find('tt')
                        dir = tt.find(text=True).encode('ascii', 'ignore')
                        tmpDirs.append(dir)

                        name = tds[1].find(text=True).encode('ascii', 'ignore')
                        tmpNames.append(name)

                        doc = ''.join(findText(tds[2]))
                        tmpDocs.append(doc)

            assert len(tmpDirs) == len(tmpNames) == len(tmpDocs), \
                'names, types, and docs are of unequal lengths: %s vs. %s vs. %s' % (tmpDirs, tmpNames, tmpDocs)
            assert sorted(tmpNames) == sorted(typeQualifiers.keys()), 'name-typeQualifiers mismatch %s %s' %  (sorted(tmpNames), sorted(typeQualifiers.keys()) )
            #self.xprint(  sorted(tmpNames), sorted(typeQualifiers.keys()), sorted(typeQualifiers.keys()) )

            for name, dir, doc in zip(tmpNames, tmpDirs, tmpDocs) :
                if dir == '[in]':
                    # attempt to correct bad in/out docs
                    if re.search(r'\b([fF]ill|[sS]tor(age)|(ing))|([rR]esult)', doc ):
                        _logger.warn( "%s.%s(%s): Correcting suspected output argument '%s' based on doc '%s'" % (
                                                            self.apiClassName,self.currentMethod,', '.join(names), name, doc))
                        dir = 'out'
                    elif not re.match( 'set[A-Z]', self.currentMethod) and '&' in typeQualifiers[name] and types[name] in ['int', 'double', 'float', 'uint', 'uchar']:
                        _logger.warn( "%s.%s(%s): Correcting suspected output argument '%s' based on reference type '%s &' ('%s')'" % (
                                                            self.apiClassName,self.currentMethod,', '.join(names), name, types[name], doc))
                        dir = 'out'
                    else:
                        dir = 'in'
                elif dir == '[out]':
                    if types[name] == 'MAnimCurveChange':
                        _logger.warn( "%s.%s(%s): Setting MAnimCurveChange argument '%s' to an input arg (instead of output)" % (
                                                            self.apiClassName,self.currentMethod,', '.join(names), name))
                        dir = 'in'
                    else:
                        dir = 'out'
                elif dir == '[in,out]':
                    # it makes the most sense to treat these types as inputs
                    # maybe someday we can deal with dual-direction args...?
                    dir = 'in'
                else:
                    raise ValueError("direction must be either '[in]', '[out]', or '[in,out]'. got %r" % dir)

                assert name in names
                directions[name] = dir
                docs[name] = doc.replace('\n\r', ' ').replace('\n', ' ')


            # Documentation for Return Values
            if returnType:
                returnTag = addendum.find('dl', 'return')
                if returnTag:
                    returnDocBuf = findText(returnTag)
                    if returnDocBuf:
                        returnDoc = ''.join( returnDocBuf[1:] ).replace('\n\r', ' ').replace('\n', ' ').encode('ascii', 'ignore')
                    self.xprint(  'RETURN_DOC', repr(returnDoc)  )
        #assert len(names) == len(directions), "name lenght mismatch: %s %s" % (sorted(names), sorted(directions.keys()))
        return directions, docs, methodDoc, returnDoc, deprecated

    def getMethodNameAndOutputFromProto(self, proto):
        memb = proto.find( 'td', **{'class':'memname'} )
        buf = []
        for text in findText(memb):
            text = text.strip()
            buf.extend(x for x in text.split() if x)
        return self.getMethodNameAndOutputFromToks(buf)

    TYPEDEF_RE = re.compile('^typedef(\s|$)')
    def getMethodNameAndOutputFromToks(self, buf):
        assert buf, "could not parse a method name"

        methodName = returnType = returnQualifiers = None

        # typedefs aren't anything we care about (ie, may be a typedef of a
        # method - see MQtUtil.UITypeCreatorFn)
        if not self.TYPEDEF_RE.match(buf[0]):
            returnTypeToks = buf[:-1]
            methodName = buf[-1]

            methodName = methodName.split('::')[-1]
            returnType, returnQualifiers = self.parseType(returnTypeToks)

            # convert operators to python special methods
            if methodName.startswith('operator'):
                methodName = self.getOperatorName(methodName)
            else:
                #constructors and destructors
                if methodName.startswith('~') or methodName == self.apiClassName:
                    methodName = None
            # no MStatus in python
            if returnType in ['MStatus', 'void']:
                returnType = None

        return methodName, returnType, returnQualifiers

    DOXYGEN_VER_RE = re.compile('Generated by Doxygen ([0-9.]+)')

    def getDoxygenVersion(self, soup):
        doxyComment = soup.find(text=self.DOXYGEN_VER_RE)
        match = self.DOXYGEN_VER_RE.search(unicode(doxyComment))
        verStr = match.group(1)
        return tuple(int(x) for x in verStr.split('.'))

    def getClassPath(self):
        filename = self.getClassFilename() + '.html'
        apiBase = os.path.join(self.docloc , 'API')
        path = os.path.join(apiBase, filename)
        if not os.path.isfile(path):
            path = os.path.join(apiBase, 'cpp_ref', filename)
        return path

    # parse the method summary as a 'backup' for the parsing of the full
    # method descriptions, as sometimes methods will have a summary, but no
    # full description
    def parseMethodSummaries(self):
        if self.doxygenVersion >= (1,7):
            summaries = self.soup.find('table', 'memberdecls')
        else:
            summaries = self.soup.find('div', 'contents').find('table')

        for summary in summaries.findAll('tr', recursive=False):
            self.parseMethodSummary(summary)

    IDENTIFIER = r'[a-zA-Z_][0-9a-zA-Z_]*'
    NESTED_IDENTIFIER = '(?:%(id)s::)*%(id)s' % {'id':IDENTIFIER}
    NESTED_IDENTIFIER_RE = re.compile(r'^%s$' % NESTED_IDENTIFIER)
    ARG_DEF_SPLIT_RE = re.compile(r'((?:%s)|\S)|\s+' % NESTED_IDENTIFIER)
    METHOD_NAME_ARGS_RE = re.compile(r'([^(]*)\s*\(([^)]*)\)')

    # Really, should get a real c++ parser at some point...
    SPECIFIERS = ('auto', 'register',  'static', 'extern', 'mutable', 'friend',
                  'typedef', 'enum', 'typename', 'const', 'volatile',
                  'signed', 'unsigned',)

    # can't support C++0x - 'auto' must be EITHER a specifier OR a base_type,
    # not both...
    BASE_TYPES = ('char',
                  'wchar_t',
                  'bool',
                  'short',
                  'int',
                  'long',
                  'signed',
                  'unsigned',
                  'float',
                  'double',
                  'void',
#                  'auto',     #C++0x
#                  'char16_t', #C++0x
#                  'char32_t', #C++0x
                 )

    UNSIGNED_PREFIX_TYPES = ('char', 'int', 'int2', 'int3', 'int4')

    KNOWN_QUALIFIERS = ('*', '&', 'const', 'unsigned')

    def parseMethodSummary(self, summary):
        methodReturn = summary.find('td', 'memItemLeft', recursive=False)
        methodRest = summary.find('td', 'memItemRight', recursive=False)
        if None in (methodReturn, methodRest):
            return

        # split the return portion by whitespace and ampersands (including the
        # ampersand in the final result)
        returnText = ' '.join(findText(methodReturn))
        returnBuf = self.ARG_DEF_SPLIT_RE.split(returnText)
        returnBuf = [x.strip() for x in returnBuf if x and x.strip()]
        static = False
        if 'static' in returnBuf:
            static = True
            returnBuf.remove('static')


        # Now, split methodRest into the method name and the args
        restText = ' '.join(findText(methodRest))

        methodMatch = self.METHOD_NAME_ARGS_RE.match(restText)
        if methodMatch is None:
            # we have an enum def, or a class def, or a typedef, etc... ignore...
            return
        methodName, args = methodMatch.groups()
        methodName = methodName.strip()

        if not methodName:
            raise ValueError('could not parse method name from summary: %s' % summary)

        # run getMethodNameAndOutputFromToks before setting currentMethod, as it
        # may be transformed - ie, if we have an operator, etc...
        returnNameBuf = returnBuf + [methodName]
        methodName, returnType, returnQualifiers = self.getMethodNameAndOutputFromToks(returnNameBuf)
        if methodName is None:
            return

        # The original motivation for using the "declarations"/"summaries"
        # section of the docs was that, when autodesk moved to the new doxygen
        # format in 2012, some methods that used to have "full" descriptions
        # (ie, MBoundingBox.clear, MFnParticleSet.age, etc) no longer did... and
        # only had "summaries".  Because of backwards compatibility reasons, we
        # could not eliminate these methods, and needed some way to ensure that
        # the methods could still be parsed...
        #
        # We may eventually decide to expand the use of the summaries to fill
        # in more cases...? ie, additional overloads...?
        #
        # ..for now, we only use it it to fill in methods that have NO
        # overloads after parsing the "full" descriptions...
        if methodName in self.methods:
            return

        with self.methodSetter(methodName):
            if returnType == 'enum':
                # ignore enum declarations - don't know of any cases where an enum
                # appears in the declaration, but has no "full description"
                return

            argNames, argTypes, typeQualifiers, defaults = self.parseMethodSummaryArgs(args)

            descTag = summary.findNextSibling('tr').find('td', 'mdescRight')
            if descTag:
                if self.isObsolete(descTag):
                    return
                methodDoc = ''.join(findText(descTag))
            else:
                methodDoc = ''

            deprecated = False
            returnDoc = ''
            directions = {}
            docs = {}

            _logger.debug("Added method from method summary/declaration: %s.%s" % (self.apiClassName, methodName))
            self.addMethod(methodName, methodDoc, static, deprecated,
                           returnType, returnQualifiers, returnDoc, argNames,
                           argTypes, typeQualifiers, defaults, directions, docs)


    def parseMethodSummaryArgs(self, args):
        argNames = []
        argTypes = {}
        typeQualifiers = {}
        defaults = {}

        if args:
            for argNum, argText in enumerate(args.split(',')):
                argBuf = [x.strip() for x in self.ARG_DEF_SPLIT_RE.split(argText)
                          if x and x.strip()]

                # Now have the hard job of figuring out which portion is the
                # parameter type, and which the name
                #
                # This is made harder because, in the declaration, the name
                # may not be specified! ie, consider these two:
                #   int myVal
                #   const int
                # The only way to tell that the first gives a type and a name,
                # and the second only a type, is by using information about
                # 'known' modifiers...
                baseTypeIndex = None
                # need to treat 'unsigned' special, since it can be both
                # a specier, or a baseType
                specifierOrTypeIndices = []
                possibleNameIndices = []
                for i, tok in enumerate(argBuf):
                    if tok == '=':
                        # if we find an equals sign, then we have a 'default'
                        # assignment, ie:
                        #    myFunc(int myParam=3.0f)
                        # ...and we can stop, as both the type and name come
                        # before this...
                        break
                    if tok in self.SPECIFIERS:
                        if tok in self.BASE_TYPES:
                            specifierOrTypeIndices.append(i)
                        continue
                    elif tok in self.BASE_TYPES:
                        if baseTypeIndex is not None:
                            raise ValueError('error parsing argText %r - found two types, %s and %s' % (argText,
                                                                                                        argBuf[baseTypeIndex],
                                                                                                        tok))
                        baseTypeIndex = i
                    elif self.NESTED_IDENTIFIER_RE.match(tok):
                        possibleNameIndices.append(i)

                # if we have objects which can be specifiers OR
                # base-types, see if they're a base-type
                #
                # technically, this is a guess, since if you have:
                #    myFunc(unsigned foo)
                # ... this would NORMALLY mean an arg named "foo", of type
                # int... but if you had previously done:
                #    typedef int foo
                # ...then it would be an unnamed arg, of type "unsigned foo"

                # however, for practical purposes, we can assume that if we
                # have "unsigned foo", since foo is not a base type, it is
                # probably a name...
                if specifierOrTypeIndices and not baseTypeIndex:
                    baseTypeIndex = specifierOrTypeIndices[-1]

                if baseTypeIndex is not None:
                    if not possibleNameIndices:
                        # only found a type, no name!
                        nameIndex = None
                    elif len(possibleNameIndices) == 1:
                        nameIndex = possibleNameIndices[0]
                    else:
                        raise ValueError('error parsing argText %r - found too '
                                         'many possible names: %s, %s, ...'
                                         % (argText,
                                            argBuf[possibleNameIndices[0]],
                                            argBuf[possibleNameIndices[1]]))
                else:
                    if not possibleNameIndices:
                        raise ValueError('error parsing argText %r - found no '
                                         'possible types or names' % argText)
                    elif len(possibleNameIndices) == 1:
                        # only found a type, no name!
                        nameIndex = None
                    elif len(possibleNameIndices) == 2:
                        nameIndex = possibleNameIndices[1]
                    else:
                        raise ValueError('error parsing argText %r - found too '
                                         'many possible types/names: %s, %s, %s, ...'
                                         % (argText,
                                            argBuf[possibleNameIndices[0]],
                                            argBuf[possibleNameIndices[1]],
                                            argBuf[possibleNameIndices[2]]))
                if nameIndex is None:
                    typeToks = argBuf
                    nameToks = ['arg%d' %  argNum]
                else:
                    typeToks = argBuf[:nameIndex]
                    nameToks = argBuf[nameIndex:]

                # ok, we've finally split into the type/name portions... can
                # now call parseParamDef
                self.addParamDef(self.parseParamDef(typeToks, nameToks),
                                 argNames, argTypes, typeQualifiers, defaults)
        return argNames, argTypes, typeQualifiers, defaults

    def parseFullMethods(self):
        for proto in self.soup.body.findAll('div', 'memproto'):
            self.parseFullMethod(proto)

    def parseFullMethod(self, proto):
        methodName, returnType, returnQualifiers = self.getMethodNameAndOutputFromProto(proto)
        if methodName is None:
            return

        with self.methodSetter(methodName):
            if self.currentMethod == 'void(*':
                return
            # ENUMS
            if returnType == 'enum':
                self.xprint( "ENUM", returnType)
                #print returnType, methodName
                try:
                    #print enumList
                    enumData = self.parseEnums(proto)
                    self.enums[self.currentMethod] = enumData[0]
                    self.pymelEnums[self.currentMethod] = enumData[1]

                except AttributeError, msg:
                    _logger.error("FAILED ENUM: %s", msg)
                    import traceback
                    _logger.debug(traceback.format_exc())

            # ARGUMENTS
            else:
                self.xprint( "RETURN", returnType)

                # Static methods
                static = False
                try:
                    res = proto.findAll('code')
                    if res:
                        code = res[-1].string
                        if code and code.strip() == '[static]':
                            static = True
                except IndexError: pass

                if self.isObsolete(proto):
                    return

                names, types, typeQualifiers, defaults = self.parseTypes(proto)

                try:
                    directions, docs, methodDoc, returnDoc, deprecated = self.parseMethodArgs(proto, returnType, names, types, typeQualifiers)
                except AssertionError, msg:
                    _logger.error(self.formatMsg("FAILED", str(msg)))
                    return
                except AttributeError:
                    import traceback
                    _logger.error(self.formatMsg(traceback.format_exc()))
                    return

                return self.addMethod(methodName, methodDoc, static, deprecated,
                                      returnType, returnQualifiers, returnDoc,
                                      names, types, typeQualifiers, defaults,
                                      directions, docs)

    def addMethod(self, methodName, methodDoc, static, deprecated, returnType,
                  returnQualifiers, returnDoc, names, types, typeQualifiers,
                  defaults, directions, docs):
        with self.methodSetter(methodName):
            argInfo={}
            argList=[]
            inArgs=[]
            outArgs=[]

            for argname in names[:] :
                type = types[argname]
                if argname not in directions:
                    self.xprint("Warning: assuming direction is 'in'")
                    directions[argname] = 'in'
                direction = directions[argname]
                doc = docs.get( argname, '')

                if type == 'MStatus':
                    types.pop(argname)
                    defaults.pop(argname,None)
                    directions.pop(argname,None)
                    docs.pop(argname,None)
                    idx = names.index(argname)
                    names.pop(idx)
                else:
                    if direction == 'in':
                        inArgs.append(argname)
                    else:
                        outArgs.append(argname)
                    argInfo[ argname ] = {'type': type, 'doc': doc }

            # correct bad outputs
            if self.isGetMethod() and not returnType and not outArgs:
                for argname in names:
                    if '&' in typeQualifiers[argname]:
                        doc = docs.get(argname, '')
                        directions[argname] = 'out'
                        idx = inArgs.index(argname)
                        inArgs.pop(idx)
                        outArgs.append(argname)

                        _logger.warn( "%s.%s(%s): Correcting suspected output argument '%s' because there are no outputs and the method is prefixed with 'get' ('%s')" % (
                                                                       self.apiClassName,self.currentMethod, ', '.join(names), argname, doc))

            # now that the directions are correct, make the argList
            for argname in names:
                type = types[argname]
                self.xprint( "DIRECTIONS", directions )
                direction = directions[argname]
                data = ( argname, type, direction)
                self.xprint( "ARG", data )
                argList.append(  data )

            methodInfo = { 'argInfo': argInfo,
                          'returnInfo' : {'type' : returnType,
                                          'doc' : returnDoc,
                                          'qualifiers' : returnQualifiers},
                          'args' : argList,
                          'returnType' : returnType,
                          'inArgs' : inArgs,
                          'outArgs' : outArgs,
                          'doc' : methodDoc,
                          'defaults' : defaults,
                          #'directions' : directions,
                          'types' : types,
                          'static' : static,
                          'typeQualifiers' : typeQualifiers,
                          'deprecated' : deprecated }
            self.methods[self.currentMethod].append(methodInfo)
            return methodInfo

    def setClass(self, apiClassName):
        self.enums = {}
        self.pymelEnums = {}
        self.methods=util.defaultdict(list)
        self.currentMethod=None
        self.badEnums = []

        self.apiClassName = apiClassName
        self.apiClass = getattr(self.apiModule, self.apiClassName)
        self.docfile = self.getClassPath()

        _logger.info( "parsing file %s" , self.docfile )

        with open( self.docfile ) as f:
            self.soup = BeautifulSoup( f.read(), convertEntities='html' )
        self.doxygenVersion = self.getDoxygenVersion(self.soup)

    def parse(self, apiClassName):
        self.setClass(apiClassName)
        self.parseFullMethods()
        self.parseMethodSummaries()
        pymelNames, invertibles = self.getPymelMethodNames()
        return { 'methods' : dict(self.methods),
                 'enums' : self.enums,
                 'pymelEnums' : self.pymelEnums,
                 'pymelMethods' :  pymelNames,
                 'invertibles' : invertibles
                }
