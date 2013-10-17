"""
Maya-related functions, which are useful to both `api` and `core`, including `mayaInit` which ensures
that maya is initialized in standalone mode.
"""
from __future__ import with_statement
import types
import os.path
import sys
import glob
import inspect
import gzip
import json

import maya
import maya.OpenMaya as om
import maya.utils

from pymel.util import picklezip, shellOutput, subpackages, refreshEnviron, \
    namedtuple, enum
import pymel.versions as versions
from pymel.mayautils import getUserPrefsDir
from pymel.versions import shortName, installName
import plogging


# There are FOUR different ways maya might be started, all of which are
# subtly different, that need to be considered / tested:
#
# 1) Normal gui
# 2) maya -prompt
# 3) Render
# 4) mayapy (or just straight up python)

_logger = plogging.getLogger(__name__)
try:
    import cPickle as pickle
except:
    _logger.warning("using pickle instead of cPickle: load performance will be affected")
    import pickle

#from maya.cmds import encodeString

isInitializing = False
# Setting this to False will make finalize() do nothing
finalizeEnabled = True
_finalizeCalled = False

# tells whether this maya package has been modified to work with pymel
pymelMayaPackage = hasattr(maya.utils, 'shellLogHandler') or versions.current() >= versions.v2011


def _moduleJoin(*args):
    """
    Joins with the base pymel directory.
    :rtype: string
    """
    moduleDir = os.path.dirname( os.path.dirname( sys.modules[__name__].__file__ ) )
    return os.path.realpath(os.path.join( moduleDir, *args))


def mayaStartupHasRun():
    """
    Returns True if maya.app.startup has already finished, False otherwise.
    """
    return 'maya.app.startup.gui' in sys.modules or 'maya.app.startup.batch' in sys.modules

def mayaStartupHasStarted():
    """
    Returns True if maya.app.startup has begun running, False otherwise.

    It's possible that maya.app.startup is in the process of running (ie,
    in maya.app.startup.basic, calling executeUserSetup) - unlike mayaStartup,
    this will attempt to detect if this is the case.
    """
    return hasattr(maya, 'stringTable')

def setupFormatting():
    import pprint
    import maya.utils
    def myResultCallback(obj):
        return pprint.pformat(obj)
    maya.utils.formatGuiResult = myResultCallback
    # prevent auto-completion generator from getting confused
    maya.utils.formatGuiResult.__module__ = 'maya.utils'

#def loadDynamicLibs():
#    """
#    due to a bug in maya.app.commands many functions do not return any value the first time they are run,
#    especially in standalone mode.  this function forces the loading of all dynamic libraries, which is
#    a very fast and memory-efficient process, which begs the question: why bother dynamically loading?
#
#    this function can only be run after maya.standalone is initialized
#    """
#
#    commandListPath = os.path.realpath( os.environ[ 'MAYA_LOCATION' ] )
#    commandListPath = os.path.join( commandListPath, libdir, 'commandList' )
#
#    import maya.cmds
#    assert hasattr( maya.cmds, 'dynamicLoad'), "maya.standalone must be initialized before running this function"
#    file = open( commandListPath, 'r' )
#    libraries = set( [ line.split()[1] for line in file] )
#    for library in libraries:
#        try:
#            maya.cmds.dynamicLoad(library)
#        except RuntimeError:
#            _logger.debug("Error dynamically loading maya library: %s" % library)

# Will test initialize maya standalone if necessary (like if scripts are run from an exernal interpeter)
# returns True if Maya is available, False either
def mayaInit(forversion=None) :
    """ Try to init Maya standalone module, use when running pymel from an external Python inerpreter,
    it is possible to pass the desired Maya version number to define which Maya to initialize


    Part of the complexity of initializing maya in standalone mode is that maya does not populate os.environ when
    parsing Maya.env.  If we initialize normally, the env's are available via maya (via the shell), but not in python
    via os.environ.

    Note: the following example assumes that MAYA_SCRIPT_PATH is not set in your shell environment prior to launching
    python or mayapy.

    >>> import maya.standalone            #doctest: +SKIP
    >>> maya.standalone.initialize()      #doctest: +SKIP
    >>> import maya.mel as mm             #doctest: +SKIP
    >>> print mm.eval("getenv MAYA_SCRIPT_PATH")    #doctest: +SKIP
    /Network/Servers/sv-user.luma-pictures.com/luma .....
    >>> import os                         #doctest: +SKIP
    >>> 'MAYA_SCRIPT_PATH' in os.environ  #doctest: +SKIP
    False

    The solution lies in `refreshEnviron`, which copies the environment from the shell to os.environ after maya.standalone
    initializes.

    :rtype: bool
    :return: returns True if maya.cmds required initializing ( in other words, we are in a standalone python interpreter )

    """
    _logger.debug( "startup.mayaInit: called" )
    setupFormatting()

    global isInitializing

    # test that Maya actually is loaded and that commands have been initialized,for the requested version

    aboutExists = False
    try :
        from maya.cmds import about
        aboutExists = True
    except ImportError:
        pass

    if aboutExists and mayaStartupHasStarted():
        # if this succeeded, we're initialized
        _logger.debug( "startup.mayaInit: maya already started - exiting" )
        isInitializing = False
        return False

    _logger.debug( "startup.mayaInit: running" )
    # for use with pymel compatible maya package
    os.environ['MAYA_SKIP_USERSETUP_PY'] = 'on'

    if not aboutExists and not sys.modules.has_key('maya.standalone'):
        try :
            _logger.debug( "startup.mayaInit: running standalone.initialize" )
            import maya.standalone #@UnresolvedImport
            maya.standalone.initialize(name="python")

            if versions.current() < versions.v2009:
                refreshEnviron()

        except ImportError, e:
            raise ImportError(str(e) + ": pymel was unable to intialize maya.standalone")

    try:
        from maya.cmds import about
    except Exception:
        _logger.error("maya.standalone was successfully initialized, but pymel failed to import maya.cmds (or it was not populated)")
        raise

    if not mayaStartupHasRun():
        _logger.debug( "running maya.app.startup" )
        # If we're in 'maya -prompt' mode, and a plugin loads pymel, then we
        # can have a state where maya.standalone has been initialized, but
        # the python startup code hasn't yet been run...
        if about(batch=True):
            import maya.app.startup.batch
        else:
            import maya.app.startup.gui

    # return True, meaning we had to initialize maya standalone
    isInitializing = True
    return True

def initMEL():
    if 'PYMEL_SKIP_MEL_INIT' in os.environ or pymel_options.get( 'skip_mel_init', False ) :
        _logger.info( "Skipping MEL initialization" )
        return

    _logger.debug( "initMEL" )
    mayaVersion = versions.installName()
    prefsDir = getUserPrefsDir()
    if prefsDir is None:
        _logger.error( "could not initialize user preferences: MAYA_APP_DIR not set" )
    elif not os.path.isdir(prefsDir):
        _logger.error( "could not initialize user preferences: %s does not exist" % prefsDir  )

    # TODO : use cmds.internalVar to get paths
    # got this startup sequence from autodesk support
    startup = [
        #'defaultRunTimeCommands.mel',  # sourced automatically
        #os.path.join( prefsDir, 'userRunTimeCommands.mel'), # sourced automatically
        'createPreferencesOptVars.mel',
        'createGlobalOptVars.mel',
        os.path.join( prefsDir, 'userPrefs.mel') if prefsDir else None,
        'initialStartup.mel',
        #$HOME/Documents/maya/projects/default/workspace.mel
        'initialPlugins.mel',
        #'initialGUI.mel', #GUI
        #'initialLayout.mel', #GUI
        #os.path.join( prefsDir, 'windowPrefs.mel'), #GUI
        #os.path.join( prefsDir, 'menuSetPrefs.mel'), #GUI
        #'hotkeySetup.mel', #GUI
        'namedCommandSetup.mel',
        os.path.join( prefsDir, 'userNamedCommands.mel' ) if prefsDir else None,
        #'initAfter.mel', #GUI
        os.path.join( prefsDir, 'pluginPrefs.mel' )  if prefsDir else None
    ]
    try:
        for f in startup:
            _logger.debug("running: %s" % f)
            if f is not None:
                if os.path.isabs(f) and not os.path.exists(f):
                    _logger.warning( "Maya startup file %s does not exist" % f )
                else:
                    # need to encode backslashes (used for windows paths)
                    if isinstance(f, unicode):
                        encoding = 'unicode_escape'
                    else:
                        encoding = 'string_escape'
                    #import pymel.core.language as lang
                    #lang.mel.source( f.encode(encoding)  )
                    import maya.mel
                    maya.mel.eval( 'source "%s"' % f.encode(encoding) )

    except Exception, e:
        _logger.error( "could not perform Maya initialization sequence: failed on %s: %s" % ( f, e) )

    try:
        # make sure it exists
        res = maya.mel.eval('whatIs "userSetup.mel"')
        if res != 'Unknown':
            maya.mel.eval( 'source "userSetup.mel"')
    except RuntimeError: pass

    _logger.debug("done running mel files")

def initAE():
    try:
        pkg = __import__('AETemplates')
    except ImportError:
        return False
    except Exception:
        import traceback
        traceback.print_exc()
        return False
    else:
        # import subpackages
        for data in subpackages(pkg):
            pass
    return True

def finalize():
    global finalizeEnabled
    global _finalizeCalled
    if not finalizeEnabled or _finalizeCalled:
        return
    _logger.debug('finalizing')
    # Set this to true HERE, as in running userSetup.py,
    # we could end up in here again, inside the initial finalize...
    _finalizeCalled = True

    global isInitializing
    if pymelMayaPackage and isInitializing:
        # this module is not encapsulated into functions, but it should already
        # be imported, so it won't run again
        assert 'maya.app.startup.basic' in sys.modules, \
            "something is very wrong. maya.app.startup.basic should be imported by now"
        import maya.app.startup.basic
        maya.app.startup.basic.executeUserSetup()

    state = om.MGlobal.mayaState()
    if state == om.MGlobal.kLibraryApp: # mayapy only
        initMEL()
        #fixMayapy2011SegFault()
    elif state == om.MGlobal.kInteractive:
        initAE()


# Have all the checks inside here, in case people want to insert this in their
# userSetup... it's currently not always on
def fixMayapy2011SegFault():
    currentVer = versions.current()
    # this was fixed in 2014, but in 2014, it will crash consistently if you use
    # the sceneAseembly plugin, and inconsistently even if you don't...
    if versions.v2011 <= currentVer < versions.v2013 or currentVer >= versions.v2014:
        import platform
        if platform.system() == 'Linux':
            if om.MGlobal.mayaState() == om.MGlobal.kLibraryApp: # mayapy only
                # In linux maya 2011, once maya has been initialized, if you try
                # to do a 'normal' sys.exit, it will crash with a segmentation
                # fault..
                # do a 'hard' os._exit to avoid this

                # note that, since there is no built-in support to tell from
                # within atexit functions what the exit code is, we cannot
                # guarantee returning the "correct" exit code... for instance,
                # if someone does:
                #    raise SystemExit(300)
                # we will instead return a 'normal' exit code of 0
                # ... but in general, the return code is a LOT more reliable now,
                # since it used to ALWAYS return non-zero...

                import sys
                import atexit

                # First, wrap sys.exit to store the exit code...
                _orig_exit = sys.exit

                # This is just in case anybody else needs to access the
                # original exit function...
                if not hasattr('sys', '_orig_exit'):
                    sys._orig_exit = _orig_exit
                def exit(status):
                    sys._exit_status = status
                    _orig_exit(status)
                sys.exit = exit

                def hardExit():
                    # run all the other exit handlers registered with
                    # atexit, then hard exit... this is easy, because
                    # atexit._run_exitfuncs pops funcs off the stack as it goes...
                    # so all we need to do is call it again
                    import sys
                    atexit._run_exitfuncs()
                    try:
                        print "pymel: hard exiting to avoid mayapy crash..."
                    except Exception:
                        pass
                    import os
                    import sys

                    exitStatus = getattr(sys, '_exit_status', None)
                    if exitStatus is None:
                        last_value = getattr(sys, 'last_value', None)
                        if last_value is not None:
                            if isinstance(last_value, SystemExit):
                                try:
                                    exitStatus = last_value.args[0]
                                except Exception: pass
                            if exitStatus is None:
                                exitStatus = 1
                    if exitStatus is None:
                        exitStatus = 0
                    os._exit(exitStatus)
                atexit.register(hardExit)

# Fix for non US encodings in Maya
def encodeFix():
    if mayaInit() :
        from maya.cmds import about

        mayaEncode = about(cs=True)
        pyEncode = sys.getdefaultencoding()     # Encoding tel que defini par sitecustomize
        if mayaEncode != pyEncode :             # s'il faut redefinir l'encoding
            #reload (sys)                       # attention reset aussi sys.stdout et sys.stderr
            #sys.setdefaultencoding(newEncode)
            #del sys.setdefaultencoding
            #print "# Encoding changed from '"+pyEncode+'" to "'+newEncode+"' #"
            if not about(b=True) :              # si pas en batch, donc en mode UI, redefinir stdout et stderr avec encoding Maya
                import maya.utils
                try :
                    import maya.app.baseUI
                    import codecs
                    # Replace sys.stdin with a GUI version that will request input from the user
                    sys.stdin = codecs.getreader(mayaEncode)(maya.app.baseUI.StandardInput())
                    # Replace sys.stdout and sys.stderr with versions that can output to Maya's GUI
                    sys.stdout = codecs.getwriter(mayaEncode)(maya.utils.Output())
                    sys.stderr = codecs.getwriter(mayaEncode)(maya.utils.Output( error=1 ))
                except ImportError :
                    _logger.debug("Unable to import maya.app.baseUI")

#===============================================================================
# JSON encoding / decoding
#===============================================================================

_PY_27_JSON = sys.version_info[:2] >= (2, 7)
if _PY_27_JSON:
    # we need to dot a bit of ugly hackery to override _iterencode_dict in
    # python 2.7... these helper funcs will be needed...

    # Some utility funcs for dealing with closures / cells / etc...

    def make_cell(value):
        '''Makes an object of type Cell (a member of the func_closure tuple)
        Python has no standard way to make of one of these, but we can do so
        by use of a workaround
        see http://nedbatchelder.com/blog/201301/byterun_and_making_cells.html
        for more info
        '''
        def func_with_closure():
            return value
        return func_with_closure.func_closure[0]

    def get_closure_var_index(func, closure_var_name_or_index):
        if isinstance(closure_var_name_or_index, basestring):
            return func.func_code.co_freevars.index(closure_var_name_or_index)
        elif isinstance(closure_var_name_or_index, int):
            return closure_var_name_or_index
        else:
            raise TypeError(closure_var_name_or_index)

    def get_closure_var(func, closure_var_name_or_index):
        closure_index = get_closure_var_index(func, closure_var_name_or_index)
        return func.func_closure[closure_index].cell_contents

    def replace_closure_values(func, varsToNewValues):
        new_closure = list(func.func_closure)
        for closure_var_name_or_index, new_value in varsToNewValues.iteritems():
            closure_index = get_closure_var_index(func, closure_var_name_or_index)
            new_cell = make_cell(new_value)
            new_closure[closure_index] = new_cell
        return types.FunctionType(func.func_code, func.func_globals,
                                  func.func_name, func.func_defaults,
                                  tuple(new_closure))


ENCODED_TYPE = '_JSON_encoded_type'
class PymelJSONEncoder(json.JSONEncoder):

    def default(self, obj):
        # print "default: %r" % (obj,)
        if isinstance(obj, type):
            # before encoding, ensure that the class object can be pulled
            # from it's module...
            moduleName = obj.__module__
            className = obj.__name__
            moduleObj = sys.modules.get(moduleName)
            if moduleObj is None:
                raise TypeError("cannot encode class %s.%s - module %s does not"
                                " exist in sys.modules" % (moduleName,
                                                           className,
                                                           moduleName))
            classFromModule = getattr(moduleObj, className, None)
            if classFromModule is not obj:
                raise TypeError("cannot encode class %s.%s - object %s in "
                                " module %s (%r) is not the given class object "
                                " (%r)" % (moduleName, className, className,
                                           moduleName, classFromModule, obj))
            result = {ENCODED_TYPE: 'type', '__name__': obj.__name__,
                      '__module__': obj.__module__}
        elif isinstance(obj, enum.Enum):
            name = obj._name
            keys = obj._keys
            values = obj._values
            docs = obj._docs

            # only thing we need to do is convert the "values" to a defaults
            # dict, in case we have muliple keys per int-value (ie, like in
            # MSpace.Space)
            defaults = dict((enumInt, enumValue.key) for enumInt, enumValue
                            in values.iteritems())

            result = {ENCODED_TYPE: 'Enum',
                      'name': name,
                      'keys': keys,
                      'defaultKeys': defaults,
                      'docs': docs}
        else:
            result = super(PymelJSONEncoder, self).default(obj)
        return result

    # unfortuantely, the json standard requires keys for all dicts to be
    # strings... and the standard JSONEncoder provides no good way by default
    # to either override the default convert-basic-type-keys-to-strings
    # behavior, or a way to handle non-basic-type-keys... so we have to
    # resort to a bit of hackery... even worse, the exact type of hackery
    # depends on the python version...

    if not _PY_27_JSON:
        # in python 2.6, life is easy - the class has an _iterencode_dict method
        # which we can override directly...

        def _iterencode_dict(self, dct, *args, **kwargs):
            jsonDct = self.pyDictToJsonDict(dct)
            return super(PymelJSONEncoder, self)._iterencode_dict(jsonDct,
                                                                  *args,
                                                                  **kwargs)

        def _iterencode_list(self, lst, markers=None):
            if isinstance(lst, tuple):
                obj = {ENCODED_TYPE: 'tuple', 'items': list(lst)}
                return self._iterencode(obj, markers)
            else:
                return super(PymelJSONEncoder, self)._iterencode_list(lst,
                                                                      markers=markers)

    else:
        # in python 2.7, they made it more difficult...
        # the _iterencode_dict is generated, on the fly, inside of the
        # iterencode function... by calling _make_iterencode... and it is
        # only inside of the function body of _make_iterencode that
        # the _iterencode_dict that we wish to override lives...
        # ...however, thanks to the magic of function enclosures, we can still
        # actually get at / modify this function within a function... though
        # it definitely takes some hacking...

        def iterencode(self, o, *args, **kwargs):
            # print "iterencode: %r" % (o,)
            import json.encoder
            orig_make_iterencode = json.encoder._make_iterencode
            orig_c_make_encoder = json.encoder.c_make_encoder

            def new_make_iterencode(*args, **kwargs):
                # WARNING!!!!!!!
                # THIS DOES NOT CURRENLTY WORK!

                # The problem is that all three of _iterencode,
                # _iterencode_dict, and _iterencode_list reference themselves
                # and the other two.  This means, that for all three, we need
                # edit their enclosures to point to the "wrapped"/"new" versions
                # of these functions.

                # This means that we need to generate "recursive closures" - ie,
                # _iterencode needs to have inside of it's own closure a
                # referernce to itself, _iterencode.

                # However, since the only official way to set a closure for a
                # function is to generaate a NEW function - by calling
                # FunctionType(code, ..., closure) - there's no way for me to
                # generate a function (from an existing code object) that has
                # itself in it's own closure.

                # In essence, function objects can be thought of as immutable,
                # like tuples; so the problem is similar to asking, "How can I
                # make a tuple which contains itself?"

                # The simple answer is: you can't.  The longer answer is - you
                # can, but it's incredibly hacky, and requires calling out to
                # the cpython code - basically, a function which allows you to
                # alter the members of a tuple, what is supposed to be an
                # immutable type.

                # With such a function, we can make this work - by modifying
                # the closures of the original functions in place, since they
                # are just tuples of cell objects - but this is EXTREMELY hacky,
                # on top of a solution which is already extremely hacky.

                # For reference, here's a function which allows setting of a
                # tuple:

# def set_tuple(array, index, value):
#     import ctypes
#
#     # Sanity check. We can't let PyTuple_SetItem fail, or it will Py_DECREF
#     # the object and destroy it.
#     if not isinstance(array, tuple):
#         raise TypeError("array must be a tuple")
#
#     if not 0 <= index < len(tup):
#         raise IndexError("tuple assignment index out of range")
#
#     arrayobj = ctypes.py_object(array)
#     valobj = ctypes.py_object(value)
#
#     # Need to drop the refcount to 1 in order to use PyTuple_SetItem.
#     # Needless to say, this is incredibly dangerous.
#     refcnt = ctypes.pythonapi.Py_DecRef(arrayobj)
#     for i in range(refcnt-1):
#         ctypes.pythonapi.Py_DecRef(arrayobj)
#
#     try:
#         ret = ctypes.pythonapi.PyTuple_SetItem(arrayobj, ctypes.c_ssize_t(index), valobj)
#         if ret != 0:
#             raise RuntimeError("PyTuple_SetItem failed")
#     except:
#         raise SystemError("FATAL: PyTuple_SetItem failed: tuple probably unusable")
#
#     # Restore refcount and add one more for the new self-reference
#     for i in range(refcnt+1):
#         ctypes.pythonapi.Py_IncRef(arrayobj)

                orig_iterenc_func = orig_make_iterencode(*args, **kwargs)
                orig_iterencode_dict = get_closure_var(orig_iterenc_func,
                                                       '_iterencode_dict')
                orig_iterencode_list = get_closure_var(orig_iterenc_func,
                                                       '_iterencode_list')

                def new_iterencode_dict(dct, *args, **kwargs):
                    # print "pyDct", dct
                    jsonDct = self.pyDictToJsonDict(dct)
                    # print "jsonDct:", jsonDct
                    return orig_iterencode_dict(jsonDct, *args, **kwargs)

                def new_iterencode_list(lst, *args, **kwargs):
                    # print "pylst:", lst
                    if isinstance(lst, tuple):
                        obj = {ENCODED_TYPE: 'tuple', 'items': list(lst)}
                        # we use the orig_iterencode_dict here, because we don't
                        # wish/need to double-encode this... ie, we're mapped
                        # a tuple to a dict, THAT CONTAINS ENCODED_TYPE; if we
                        # were to then use new_iterenc_func, it would call
                        # our new_iterencode_dict, which would detect that the
                        # dict contains ENCODED_TYPE, and then re-encode
                        # it as a PythonDict type...
                        return orig_iterencode_dict(obj, *args, **kwargs)
                    else:
                        return orig_iterencode_list(lst, *args, **kwargs)

                closure_replacements = {
                    '_iterencode_dict': new_iterencode_dict,
                    '_iterencode_list': new_iterencode_list,
                }
                new_iterenc_func = replace_closure_values(orig_iterenc_func,
                    closure_replacements)
                return new_iterenc_func

            json.encoder._make_iterencode = new_make_iterencode
            json.encoder.c_make_encoder = None
            try:
                return super(PymelJSONEncoder, self).iterencode(o, *args, **kwargs)
            finally:
                json.encoder._make_iterencode = orig_make_iterencode
                json.encoder.c_make_encoder = orig_c_make_encoder
        #
    #

    @classmethod
    def pyDictToJsonDict(cls, pyDict):
        # print "pyDictToJsonDict: %r" % (pyDict,)
        # if all keys are strings, no conversion needed
        if (all(type(key) in (str, unicode) for key in pyDict)
                # (also, we need to encode if the dict contains our special
                # signal key, ENCODED_TYPE)
                and ENCODED_TYPE not in pyDict):
            return pyDict

        # otherwise, we mark that it's been converted by adding our special
        # ENCODED_TYPE key...
        # also, we keep two dicts, one with encoded keys, and one with
        # un-encoded keys... do this to avoid unnecessary extra level of
        # encoding for string keys, if there is a mix of string and non-string
        # keys...
        encodedKeys = {}
        unencodedKeys = {}
        jsonDict = {'encodedKeys': encodedKeys, 'unencodedKeys': unencodedKeys,
                    ENCODED_TYPE: 'PythonDict'}

        for pyKey, val in pyDict.iteritems():
            if isinstance(pyKey, (str, unicode)):
                # it's a "normal" key - we can add it into the unencodedKeys
                unencodedKeys[pyKey] = val
            else:
                # print "pyKey: %r" % (pyKey,)
                jsonKey = json.dumps(pyKey, sort_keys=True, cls=cls)
                # print "jsonKey: %r" % (jsonKey,)
                encodedKeys[jsonKey] = val
        return jsonDict

    @classmethod
    def jsonDictToPyDict(cls, jsonDict):
        pyDict = dict(jsonDict['unencodedKeys'])

        # now, decode the keys that need decoding...
        for jsonKey, val in jsonDict['encodedKeys'].iteritems():
            pyKey = json.loads(jsonKey, object_hook=cls.decoderHook)
            pyDict[pyKey] = val
        return pyDict

    @classmethod
    def decoderHook(cls, objDict):
        objType = objDict.pop(ENCODED_TYPE, None)
        if objType is not None:
            if objType == 'type':
                module = __import__(objDict['__module__'], fromlist=[''])
                return getattr(module, objDict['__name__'])
            elif objType == 'tuple':
                return tuple(objDict['items'])
            elif objType == 'Enum':
                return enum.Enum(multiKeys=True, **objDict)
            elif objType == 'PythonDict':
                return cls.jsonDictToPyDict(objDict)
            else:
                raise TypeError("could not decode object with unrecognized"
                                " python type: %s" % objType)
        return objDict


#===============================================================================
# Cache utilities
#===============================================================================

def _dump( data, filename, protocol = -1):
    with open(filename, mode='wb') as file:
        pickle.dump( data, file, protocol)

def _load(filename):
    with open(filename, mode='rb') as file:
        res = pickle.load(file)
        return res

class PymelCache(object):
    # override these
    NAME = ''   # ie, 'mayaApi'
    DESC = ''   # ie, 'the API cache' - used in error messages, etc

    # whether to add the version to the filename when writing out the cache
    USE_VERSION = True

    # In general, compressed caches should have "two extensions", first giving
    # the serialization type, and the second giving the compression type - ie,
    #   mayaApi2014.json.zip
    # If it has only one extension, it is usually a serialization type, and it
    # has no compression:
    #   mayaApi2014.json
    # However, for backwards compatibility, if it only has one extension, and it
    # is "zip", then the serialization is assumed to be pickle:
    #   mayaApi2014.zip

    # order gives preference - ie, first one is the "default"
    SERIALIZATION_TYPES = ("json", "pickle")
    SERIALIZATIONS_TO_EXTENSIONS = {"json": ".json", "pickle": ".bin"}
    EXTENSIONS_TO_SERIALIZATIONS = dict(
        (ext, fileType) for (fileType, ext)
        in SERIALIZATIONS_TO_EXTENSIONS.iteritems()
    )

    COMPRESSION_TYPES = ("gzip", "uncompressed")
    COMPRESSIONS_TO_EXTENSIONS = {"gzip": ".gz", "uncompressed": ""}
    EXTENSIONS_TO_COMPRESSIONS = dict(
        (ext, fileType) for (fileType, ext)
        in COMPRESSIONS_TO_EXTENSIONS.iteritems()
    )
    COMPRESSION_TO_FILEOBJ = {"gzip": gzip.GzipFile, "uncompressed": file}

    # For backwards compatibility, a map from a single extension to
    # (serialization, compression)
    COMBO_EXTENSIONS = {".zip": ("pickle", "gzip")}

#     FILE_TYPES = COMPRESSION_TYPES + SERIALIZATION_TYPES
#     FILE_TYPES_TO_EXTENSIONS = {"json": ".json", "pickle": ".bin",
#                                 "zip": ".zip", "uncompressed": ""}
#     FILE_EXTENSIONS_TO_TYPES = dict((ext, fileType) for (fileType, ext)
#                                     in FILE_TYPES_TO_EXTENSIONS.iteritems())

    def __init__(self):
        self._readPath = None
        self._readSerialization = None
        self._readCompression = None

    def read(self, serialization=None, compression=None, comboExtension=None):
        result = self.pathAndTypes(serialization=serialization,
                                   compression=compression,
                                   comboExtension=comboExtension, onDisk=True)
        if result is None:
            _logger.error("Unable to find %s on disk" % self.DESC)

        path, serialization, compression = result

        # if we get a result with compression, check to see if there is a
        # result with NO compression, and if so, whether it has a newer
        # timestamp... if so, then use it instead
        if compression != "uncompressed":
            uncompressedResult = self.pathAndTypes(serialization=serialization,
                                                   compression="uncompressed",
                                                   onDisk=True)
            if uncompressedResult is not None:
                uncompressedPath = uncompressedResult[0]
                assert uncompressedResult[1] == serialization
                assert uncompressedResult[2] == "uncompressed"
                compressedTime = os.path.getmtime(path)
                uncompressedTime = os.path.getmtime(uncompressedPath)
                if uncompressedTime > compressedTime:
                    path, serialization, compression = uncompressedResult

        readClass = self.COMPRESSION_TO_FILEOBJ.get(compression)
        if readClass is None:
            raise ValueError("unrecognized compression: %s" % compression)

        _logger.debug(self._actionMessage('Loading', 'from', path))

        try:
            # alas, GzipFile has no context manager support...
            handle = readClass(path, "rb")
            try:
                contents = handle.read()
            finally:
                handle.close()
        except Exception, e:
            self._errorMsg('read', 'from', path, e)
            return

        self._readPath = path
        self._readSerialization = serialization
        self._readCompression = compression

        _logger.debug("loaded cache: %s" % (result,))

        if serialization == "pickle":
            result = pickle.loads(contents)
        elif serialization == "json":
            result = json.loads(contents,
                                object_hook=PymelJSONEncoder.decoderHook)
        else:
            raise ValueError("unrecognized serialization: %s" % serialization)
        return result

    def write(self, data, serialization=None, compression=None,
              comboExtension=None):

        result = self.pathAndTypes(serialization=serialization,
                                   compression=compression,
                                   comboExtension=comboExtension, onDisk=False)
        path, serialization, compression = result

        if serialization == "pickle":
            contents = pickle.dumps(data, 2)
        elif serialization == "json":
            contents = json.dumps(data, indent=4, sort_keys=True,
                                  cls=PymelJSONEncoder)

        writeClass = self.COMPRESSION_TO_FILEOBJ.get(compression)
        if writeClass is None:
            raise ValueError("unrecognized compression: %s" % compression)

        _logger.info(self._actionMessage('Saving', 'to', path))
        try:
            # alas, GzipFile has no context manager support...
            handle = writeClass(path, "wb")
            try:
                handle.write(contents)
            finally:
                handle.close()
        except Exception, e:
            self._errorMsg('write', 'to', path, e)

    def pathAndTypes(self, serialization=None, compression=None,
                     comboExtension=None, onDisk=False):
        '''Returns (path, serialization, compression)

        Parameters
        ----------
        serialization : str or None
            if given, specify the serialization type of the path to return;
            if None, and onDisk is False, the default serialization will be
            used; if None, and onDisk is True, then the function will use/return
            the first serialization that exists on disk
        compression : str or None
            if given, specify the compression type of the path to return;
            if None, and onDisk is False, the default compression will be
            used; if None, and onDisk is True, then the function will use/return
            the first compression that exists on disk
        comboExtension : str or None
            as a special case for backwards compatibility, it is possible to
            specify a single extension, which maps to both a serialization type
            and a compression type (ie, "myCache.zip" is the old format, and
            means gzip-compression and pickle-serialization); if this is given,
            then both serialization and compression MUST be None
        onDisk : bool
            if True, then returned paths must exist on disk; also affects the
            behavior if either serialization or compression is None. If either
            is None, and onDisk is True, then it will search all available
            serialization or compression types to find the first one that exists
            on disk. In either case, if no compatible path may be found on disk,
            the single item None is returned, instead of the standard tuple
        '''
        if comboExtension is not None:
            if serialization is not None or compression is not None:
                raise ValueError("if comboExtension is given, both"
                                 " serialization and compression must be None")
            serialization, compression = self.COMBO_EXTENSIONS[comboExtension]
        elif onDisk and None in (serialization, compression):
            # we need to determine which file type to read, from what's on
            # disk...
            if serialization is None:
                serialTypes = self.SERIALIZATION_TYPES
            else:
                serialTypes = [serialization]
            if compression is None:
                compressTypes = self.COMPRESSION_TYPES
            else:
                compressTypes = [compression]

            for currentSerialization in serialTypes:
                for currentCompression in compressTypes:
                    result = self.pathAndTypes(serialization=currentSerialization,
                                               compression=currentCompression,
                                               onDisk=True)
                    if result is not None:
                        return result
                # we haven't found anything - as a last ditch, try the old
                # cache.zip (ie, no-explicit-serialization) style path, for
                # backwards compatibility...
                for currentCombo in self.COMBO_EXTENSIONS:
                    result = self.pathAndTypes(comboExtension=currentCombo,
                                               onDisk=True)
                    if result is not None:
                        return result
                # we found nothing - return None
                return None

        # if we're here, then we're not doing any "guess-and-check" - there
        # is only one possible value of serialization AND compression...

        if compression is None:
            compression = self.COMPRESSION_TYPES[0]
        if serialization is None:
            serialization = self.SERIALIZATION_TYPES[0]

        if comboExtension is not None:
            # special case for backwards compatibility - if the serialization is
            # a combo extension, use it as the only extension...
            serialExt = ""
            compressExt = comboExtension
        else:
            serialExt = self.SERIALIZATIONS_TO_EXTENSIONS[serialization]
            compressExt = self.COMPRESSIONS_TO_EXTENSIONS[compression]

        # if we got here, then both serialization and compression should be
        # "set". Just construct the appropriate path...

        if self.USE_VERSION:
            if hasattr(self, 'version'):
                short_version = str(self.version)
            else:
                short_version = shortName()
        else:
            short_version = ''

        newPath = _moduleJoin('cache', self.NAME + short_version)
        newPath = newPath + serialExt + compressExt

        if onDisk and not os.path.exists(newPath):
            return None
        return newPath, serialization, compression

    @classmethod
    def _actionMessage(cls, action, direction, location):
        '''_actionMessage('eat', 'at', 'Joes') =>
            "eat cls.DESC at 'Joes'"
        '''
        description = cls.DESC
        if description:
            description = ' ' + description
        return "%s%s %s %r" % (action, description, direction, location)

    @classmethod
    def _errorMsg(cls, action, direction, path, error):
        '''_errorMessage('eat', 'at', 'Joes') =>
            'Unable to eat cls.DESC at Joes: error.msg'
        '''
        actionMsg = cls._actionMessage(action, direction, path)
        _logger.error("Unable to %s: %s" % (actionMsg, error))
        if sys.exc_type is not None:
            import traceback
            _logger.debug(traceback.format_exc())


# Considered using named_tuple, but wanted to make data stored in cache
# have as few dependencies as possible - ie, just a simple tuple
class SubItemCache(PymelCache):
    '''Used to store various maya information

    ie, api / cmd data parsed from docs

    To implement, create a subclass, which overrides at least the NAME, DESC,
    and _CACHE_NAMES attributes, and implements the rebuild method.

    Then to access data, you should initialize an instance, then call build;
    build will load the data from the cache file if possible, or call rebuild
    to build the data from scratch if not.  If the data had to be rebuilt,
    a new file cache will be saved.

    The data may then be accessed through attributes on the instance, with
    the names given in _CACHE_NAMES.

    >>> class NodeCache(SubItemCache):
    ...     NAME = 'mayaNodes'
    ...     DESC = 'the maya nodes cache'
    ...     _CACHE_NAMES = ['nodeTypes']
    ...     def rebuild(self):
    ...         import maya.cmds
    ...         self.nodeTypes = maya.cmds.allNodeTypes(includeAbstract=True)
    >>> cacheInst = NodeCache()
    >>> cacheInst.build()
    >>> 'polyCube' in cacheInst.nodeTypes
    True
    '''
    # Provides a front end for a pickled file, which should contain a
    # tuple of items; each item in the tuple is associated with a name from
    # _CACHE_NAMES

    # override this with a list of names for the items within the cache
    _CACHE_NAMES = []

    # Set this to the initialization contructor for each cache item;
    # if a given cache name is not present in ITEM_TYPES, DEFAULT_TYPE is
    # used
    # These are the types that the contents will 'appear' to be to the end user
    # (ie, the types returned by contents).
    # If the value needs to be converted before pickling, specify an entry
    # in STORAGE_TYPES
    # Both should be constructors which can either take no arguments, or
    # a single argument to initialize an instance.
    ITEM_TYPES = {}
    STORAGE_TYPES = {}
    DEFAULT_TYPE = dict

    def __init__(self):
        for name in self._CACHE_NAMES:
            self.initVal(name)

    def cacheNames(self):
        return tuple(self._CACHE_NAMES)

    def initVal(self, name):
        itemType = self.itemType(name)
        if itemType is None:
            val = None
        else:
            val = itemType()
        setattr(self, name, val)

    def itemType(self, name):
        return self.ITEM_TYPES.get(name, self.DEFAULT_TYPE)

    def build(self):
        """
        Used to rebuild cache, either by loading from a cache file, or rebuilding from scratch.
        """
        data = self.load()
        if data is None:
            self.rebuild()
            self.save()
        elif self._readCompression == "uncompressed":
            # write out a compressed version, for faster reading later
            self.save(compression=self.COMPRESSION_TYPES[0])

    # override this...
    def rebuild(self):
        """Rebuild cache from scratch

        Unlike 'build', this does not attempt to load a cache file, but always
        rebuilds it by parsing the docs, etc.
        """
        pass

    def update(self, obj, cacheNames=None):
        '''Update all the various data from the given object, which should
        either be a dictionary, a list or tuple with the right number of items,
        or an object with the caches stored in attributes on it.
        '''
        if cacheNames is None:
            cacheNames = self.cacheNames()

        if isinstance(obj, dict):
            for key, val in obj.iteritems():
                setattr(self, key, val)
        elif isinstance(obj, (list, tuple)):
            if len(obj) != len(cacheNames):
                raise ValueError('length of update object (%d) did not match length of cache names (%d)' % (len(obj), len(cacheNames)))
            for newVal, name in zip(obj, cacheNames):
                setattr(self, name, newVal)
        else:
            for cacheName in cacheNames:
                setattr(self, cacheName, getattr(obj, cacheName))

    def load(self, serialization=None, compression=None, comboExtension=None):
        '''Attempts to load the data from the cache on file.

        If it succeeds, it will update itself, and return the loaded items;
        if it fails, it will return None
        '''
        data = self.read(serialization=serialization, compression=compression,
                         comboExtension=comboExtension)
        if data is not None:
            data = list(data)
            # if STORAGE_TYPES, need to convert back from the storage type to
            # the 'normal' type
            if self.STORAGE_TYPES:
                for name in self.STORAGE_TYPES:
                    index = self._CACHE_NAMES.index(name)
                    val = data[index]
                    val = self.itemType(name)(val)
                    data[index] = val
            data = tuple(data)
            self.update(data, cacheNames=self._CACHE_NAMES)
        return data

    def save(self, obj=None, serialization=None, compression=None):
        '''Saves the cache

        Will optionally update the caches from the given object (which may be
        a dictionary, or an object with the caches stored in attributes on it)
        before saving
        '''
        if obj is not None:
            self.update(obj)
        data = self.contents()
        if self.STORAGE_TYPES:
            newData = []
            for name, val in zip(self._CACHE_NAMES, data):
                if name in self.STORAGE_TYPES:
                    val = self.STORAGE_TYPES[name](val)
                newData.append(val)
            data = tuple(newData)

        self.write(data, serialization=serialization, compression=compression)

    # was called 'caches'
    def contents(self):
        return tuple( getattr(self, x) for x in self.cacheNames() )

#===============================================================================
# Config stuff
#===============================================================================

def getConfigFile():
    return plogging.getConfigFile()

def parsePymelConfig():
    import ConfigParser

    types = {'skip_mel_init' : 'boolean',
             'check_attr_before_lock' : 'boolean',
            }
    defaults = {'skip_mel_init' : 'off',
                'check_attr_before_lock' : 'off',
               }

    config = ConfigParser.ConfigParser(defaults)
    config.read( getConfigFile() )

    d = {}
    for option in config.options('pymel'):
        getter = getattr( config, 'get' + types.get(option, '') )
        d[option] = getter( 'pymel', option )
    return d

pymel_options = parsePymelConfig()
