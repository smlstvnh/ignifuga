#Copyright (c) 2010-2012, Gabriel Jacobo
#All rights reserved.
#Permission to use this file is granted under the conditions of the Ignifuga Game Engine License
#whose terms are available in the LICENSE file or at http://www.ignifuga.org/license

# Ignifuga Game Engine
# Main Singleton
# Author: Gabriel Jacobo <gabriel@mdqinc.com>

#from ignifuga.Rect import *
from ignifuga.Singleton import Singleton
from ignifuga.Log import *
import sys, pickle, os, weakref, gc, platform, copy, base64
from optparse import OptionParser

class BACKENDS:
    sdl = 'sdl'

# This needs to match the values defined in GameLoopBase.pxd

REQUEST_NONE = 0x00000000
REQUEST_DONE = 0x00000001
REQUEST_SKIP = 0x00000002
REQUEST_STOP = 0x00000004
REQUEST_LOADIMAGE = 0x0000008
REQUEST_ERROR = 0x80000000

#from Task import Task
    
class Event:
    class TYPE:
        # We don't really use these
        mouseout = 'mouseout'
        mouseover = 'mouseover'
        click = 'click'
        # The following 3 are mapped to touch events
        _mousemove = 'mousemove'
        _mousedown = 'mousedown'
        _mouseup = 'mouseup'
        # The following 3 are mapped to touch events
        _moztouchmove = 'moztouchmove'
        _moztouchdown = 'moztouchdown'
        _moztouchup = 'moztouchup'
        
        # EVENTS ACTUALLY HANDLED BY THE NODES
        
        # Interactive x/y coordinates events
        touchdown = 'touchdown'
        touchup = 'touchup'
        touchmove = 'touchmove'
        
        # Ethereal events
        accelerometer = 'accelerometer'
        compass = 'compass'
        focus = 'focus'
        blur = 'blur'
        zoomin = 'zoomin'
        zoomout = 'zoomout'
        scroll = 'scroll'
        
    ETHEREALS = [TYPE.accelerometer, TYPE.compass, TYPE.focus, TYPE.blur, TYPE.zoomin, TYPE.zoomout, TYPE.scroll]
        
    class MODIFIERS:
        ctrl = 'ctrl'
        alt = 'alt'
        shift = 'shift'
        meta = 'meta'
    
    def __init__(self, type, x=None, y=None, deltax=None, deltay=None, button=None, stream=0, pressure=None, modifiers=[]):
        self.type = str(type).lower()
        self.x = x
        self.y = y
        self.deltax = deltax
        self.deltay = deltay
        self.button = button
        self.stream = stream
        self.pressure = pressure
        self.modifiers = modifiers
        self.ethereal = type in Event.ETHEREALS
        
    def __str__(self):
        return "%s (%s,%s) btn:%s stream: %s pre: %s mod: %s ethereal: %s" % (self.type, self.x, self.y, self.button, self.stream, self.pressure, str(self.modifiers), str(self.ethereal))

class Signal(object):
    touches = 'touches'
    zoom = 'zoom'
    scroll = 'scroll'

def getRenderer():
    return Gilbert().renderer

def Canvas():
    return _Canvas

########################################################################################################################
# SPLASH SCENE DEFINITION.
# ANY MODIFICATION OF THE SCENE DEFINITION AND RELATED CODE AND ARTWORK RENDERS THE LICENSE TO USE THIS ENGINE VOID.
########################################################################################################################

SPLASH_SCENE = {
    "resolution": {
        "width": 1920,
        "height": 1200,
    },
    "keepAspect": True,
    "autoScale": True,
    "autoCenter": True,
    "userCanScroll": False,
    "userCanZoom": False,
    "size": {
        "width": 3840,
        "height": 2400
    },
    "entities": {
        "splashimg": {
            "components": [{
                "type": "Sprite",
                "file": u"embedded:splash",
                "z": 0,
                "x": 960,
                "y": 600,
                "interactive": False
            },
            {
                "id" : "pause",
                "type": "Action",
                "duration": 2.0,
                "runNext": {
                    "duration":1.0,
                    "alpha":0.0,
                    "onStop": "Gilbert().startFirstScene()"
                }
            }]
        }
    }
}
from embedded import SPLASH
EMBEDDED_IMAGES = {
    'splash': SPLASH
}

########################################################################################################################
# END SPLASH SCENE DEFINITION
########################################################################################################################

# Dynamic imported modules (they are set up depending on the backend)
GameLoop = None
DataManager = None
_Canvas = None
Renderer = None

class GilbertPickler(pickle.Pickler):
    def memoize(self, obj):
        """Override the standard memoize as it contains an assertion in the wrong place (at least in Python 2.7.2) that screws up the children attribute in Node.pyx"""
        if self.fast:
            return
        if id(obj) in self.memo:
            return
        memo_len = len(self.memo)
        self.write(self.put(memo_len))
        self.memo[id(obj)] = memo_len, obj

class Gilbert:    
    __metaclass__ = Singleton

    def __init__(self):
        pass
    
    def init(self, backend, firstScene, scenesFile=None):
        """
        backend: 'sdl'
        firstScene: The first scene ID (a string) in which case it'll be loaded from scenesFile or a Scene object
        scenesFile: A File where to load scenes from
        """
        self.backend = backend
        debug ('Initializing Gilbert Overlord')

        usage = "game [options]"
        parser = OptionParser(usage=usage, version="Ignifuga Build Utility 1.0")
        parser.add_option("-d", "--display", dest="display", default=0,help="Display (default: 0)")
        parser.add_option("--width", dest="width", default=None,help="Resolution Width")
        parser.add_option("--height", dest="height", default=None,help="Resolution Height")
        parser.add_option("-w", "--windowed", action="store_true", dest="windowed", default=False,help="Start in windowed mode (default: no)")
        parser.add_option("-p", "--profile", action="store_true", dest="profile", default=False,help="Do a profile (ignored by the engine, useful for apps)")
        (options, args) = parser.parse_args()

        # Set up dynamic imports
        global GameLoop
        global DataManager
        global _Canvas
        global Renderer

        self.platform = sys.platform
        if self.platform.startswith('linux'):
            self.platform = 'linux'
            self.distro_name, self.distro_version, self.distro_id = platform.linux_distribution()
            if self.distro_name.lower() == 'android':
                self.platform = 'android'
        elif self.platform == 'darwin':
            self.distro_name, self.distro_version, self.distro_id = platform.mac_ver()
        elif self.platform.startswith('win32'):
            self.distro_name, self.distro_version, self.distro_id, self.multi_cpu = platform.win32_ver()

        debug('Platform: %s' % self.platform)
        debug('Distro: %s' % self.distro_name)
        debug('Distro Ver: %s ID: %s' % (self.distro_version, self.distro_id) )

        if self.backend == BACKENDS.sdl:
            debug('Initializing backend %s' % (backend,))
            from backends.sdl import initializeBackend
            from backends.sdl.GameLoop import GameLoop as gameloop
            from backends.sdl.DataManager import DataManager as datamanager
            from backends.sdl.Canvas import Canvas as canvas
            from backends.sdl.Renderer import Renderer as renderer
            initializeBackend()
            GameLoop = gameloop
            DataManager = datamanager
            _Canvas = canvas
            Renderer = renderer
            debug('Backend %s initialized' % (backend,))
        else:
            error('Unknown backend %s. Aborting' % (backend,))
            exit()

        # The only dictionaries that keeps strong references to the entities
        self.scenes = {}
        # A pointer to the current scene stored in self.scenes
        self.scene = None
        # A pointer to the current scene entities
        self.entities = {}
        # These dictionaries keep weakrefs via WeakSet, contain the current scene entities
        self.entitiesByTag = {}
        self.entitiesByZ = []

        # These keep weakrefs in the key and via Task
        #self.loading = {}
        #self.running = {}

        self._touches = {}
        self._touchCaptured = False
        self._touchCaptor = None
        self._lastEvent = None

        self._freezeRenderer = False

        self.renderer = Renderer(width=options.width, height=options.height, fullscreen= not options.windowed, display=options.display)
        self.dataManager = DataManager()
        self.gameLoop = GameLoop()

        if not self.loadState():
            debug('Failed loading previous state')
            if scenesFile is not None:
                self.loadScenesFromFile(scenesFile)

            if isinstance(firstScene, Scene):
                self.scenes[firstScene.id] = firstScene
                self._firstScene = firstScene.id
            else:
                self._firstScene = firstScene
########################################################################################################################
# SPLASH SCENE CODE
# ANY MODIFICATION OF THE SCENE DEFINITION AND RELATED CODE AND ARTWORK RENDERS THE LICENSE TO USE THIS ENGINE VOID.
########################################################################################################################
            self.loadScene('splash', copy.deepcopy(SPLASH_SCENE))
            #self.startFirstScene()
            if not self.startScene('splash'):
                error('Could not load splash scene')
                return
########################################################################################################################
# SPLASH SCENE CODE ENDS.
########################################################################################################################

        debug('Starting Game Loop')
        self.startLoop()
        # Nothing after this will get executed until the engine exits
        debug('Ignifuga Game Engine Exits...')

    def startLoop(self):
        """Set up the game loop"""
        self.gameLoop.run()

        # Engine is exiting from here onwards

        debug('Saving state')
        self.saveState()

        # Release all data
        if self.backend == BACKENDS.sdl:
            from backends.sdl import terminateBackend

        self.resetScenes()
        # DEBUG - See what's holding on to what
        objs = gc.get_objects()
        for n in objs:
            if isinstance(n, Entity) or isinstance(n,Component):
                debug ('%s: %s' % (n.__class__.__name__, n))
                for ref in gc.get_referrers(n):
                    if ref != objs:
                        debug('    REFERRER: %s %s'  % (ref.__class__, id(ref)))
                        if isinstance(ref, dict):
                            debug("    DICT: %s" % ref.keys())
                        elif isinstance(ref, list):
                            debug("    LIST: %s items" % len(ref))
                        elif isinstance(ref, tuple):
                            debug("    TUPLE: %s" % str(ref))
                        else:
                            debug("    OTHER: %s" % str(ref))
        self.dataManager.cleanup(True)
        # Break any remaining cycles that prevent garbage collection
        del self.dataManager
        del self.renderer
        debug('Terminating backend %s' % (self.backend,))
        terminateBackend()

    def endLoop(self):
        """ End the game loop, free stuff """
        self.gameLoop.quit = True



    def renderScene(self):
        # Render a new scene
        if not self._freezeRenderer:
            self.renderer.update()

#    def refreshEntityZ(self, entity):
#        """ Change the entity's z index ordering """
#        # Remove from the old z-index
#        if entity.id in self.loading:
#            return
#
#        self.hideEntity(entity)
#        # Add to the new z-index
#        if entity not in self.entitiesByZ:
#            self.entitiesByZ.append(entity)
#
#        self.entitiesByZ.sort(key = lambda x: x.z)
#
#    def hideEntity(self, entity):
#        """ Check all the Z layers, remove the entity from it"""
#        if entity in self.entitiesByZ:
#            self.entitiesByZ.remove(entity)

    def refreshEntityTags(self, entity, added_tags=[], removed_tags=[]):
        for tag in added_tags:
            if tag not in self.entitiesByTag:
                self.entitiesByTag[tag] = [] #set() #weakref.WeakSet()
            if entity not in self.entitiesByTag[tag]:
                self.entitiesByTag[tag].append(entity)

        for tag in removed_tags:
            if tag in self.entitiesByTag:
                if entity in self.entitiesByTag[tag]:
                    self.entitiesByTag[tag].remove(entity)

    def reportEvent(self, event):
        """ Propagate an event through the entities """
        # Do some event mapping/discarding
        if event.type == Event.TYPE._mousedown or event.type == Event.TYPE._moztouchdown:
            event.type = Event.TYPE.touchdown
        elif event.type == Event.TYPE._mouseup or event.type == Event.TYPE._moztouchup:
            event.type = Event.TYPE.touchup
        elif event.type == Event.TYPE._mousemove or event.type == Event.TYPE._moztouchmove:
            event.type = Event.TYPE.touchmove

        continuePropagation = True
        captureEvent = False
   
        if not event.ethereal and event.x != None and event.y != None:
            # See if we have a deltax,deltay
            if event.deltax == None or event.deltay == None:
                if event.stream in self._touches:
                    lastTouch = self._touches[event.stream]
                    event.deltax = event.x - lastTouch.x
                    event.deltay = event.y - lastTouch.y

            # Walk the entities, see if the event matches one of them and inform it of the event
#            scale_x, scale_y = self.renderer.scale
#            # Scroll is in scene coordinates
#            scroll_x, scroll_y = self.renderer.scroll
            
            event.scene_x, event.scene_y = self.renderer.screenToScene(event.x, event.y)
            self._lastEvent = event

            if not self._touchCaptured:
                for entity in self.entitiesByZ:
                    continuePropagation, captureEvent = entity.event(event)
                    if captureEvent:
                        self._touchCaptor = entity
                        self._touchCaptured = True
                    if not continuePropagation:
                        break
            elif self._touchCaptor is not None:
                continuePropagation, captureEvent = self._touchCaptor.event(event)
                if not captureEvent:
                    self._touchCaptured = False
                    self._touchCaptor = None

            if continuePropagation and self._touchCaptor == None:
                if event.deltax != None and event.deltay != None and event.type != Event.TYPE.touchdown:
                    if self.scene and self.scene.userCanScroll and event.stream == 0 and event.stream in self._touches and len(self._touches)==1:
                        # Handle scrolling
                        self.renderer.scrollBy(event.deltax, event.deltay)
                        self._touchCaptured = True
                        self._touchCaptor = None

                    if self.scene and self.scene.userCanZoom and len(self._touches) == 2 and (event.stream == 0 or event.stream == 1) and 0 in self._touches and 1 in self._touches:
                        # Handle zooming
                        prevArea = (self._touches[0].x-self._touches[1].x)**2 + (self._touches[0].y-self._touches[1].y)**2
                        if event.stream == 0:
                            prevTouch = self._touches[1]
                        else:
                            prevTouch = self._touches[0]

                        currArea = (event.x-prevTouch.x)**2 +(event.y-prevTouch.y)**2
                        zoomCenterX = (event.x + prevTouch.x)/2
                        zoomCenterY = (event.y + prevTouch.y)/2
                        cx,cy = self.renderer.screenToScene(zoomCenterX, zoomCenterY)
                        self.renderer.scaleBy(currArea-prevArea)
                        sx,sy = self.renderer.sceneToScreen(cx,cy)

                        self.renderer.scrollBy(zoomCenterX-sx, zoomCenterY-sy)
                        self._touchCaptured = True
                        self._touchCaptor = None

            if event.type == Event.TYPE.touchup:
                # Forget about this stream as the user lift the finger/mouse button
                self._resetStream(event.stream)
                self._touchCaptured = False
                self._touchCaptor = None
            elif event.type == Event.TYPE.touchdown or event.stream in self._touches:   # Don't store touchmove events because in a pointer based platform this gives you scrolling with no mouse button pressed
                    # Save the last touch event for the stream
                    self._storeEvent(event)
            
        elif event.ethereal:
            # Send the event to all entity until something stops it
            for entity in self.entitiesByZ:
                continuePropagation, captureEvent = entity.event(event)
                if captureEvent:
                    self._touchCaptor = entity
                    self._touchCaptured = True
                if not continuePropagation:
                    break

            if continuePropagation:
                if self.scene and self.scene.userCanZoom:
                    if event.type == Event.TYPE.zoomin:
                        if self._lastEvent:
                            cx,cy = self.renderer.screenToScene(self._lastEvent.x, self._lastEvent.y)
                        self.renderer.scaleByFactor(1.2)
                        if self._lastEvent:
                            sx,sy = self.renderer.sceneToScreen(cx,cy)
                            self.renderer.scrollBy(self._lastEvent.x-sx, self._lastEvent.y-sy)
                    elif event.type == Event.TYPE.zoomout:
                        if self._lastEvent:
                            cx,cy = self.renderer.screenToScene(self._lastEvent.x, self._lastEvent.y)
                        self.renderer.scaleByFactor(0.8)
                        if self._lastEvent:
                            sx,sy = self.renderer.sceneToScreen(cx,cy)
                            self.renderer.scrollBy(self._lastEvent.x-sx, self._lastEvent.y-sy)
                    
    def _storeEvent(self, event):
        """ Store a touch/mouse event for a stream, to be used for future reference"""
        self._touches[event.stream] = event

    def _resetStream(self, stream):
        """ Reset the last stored event for the stream"""
        if stream in self._touches:
            del self._touches[stream]

    def saveState(self):
        """ Serialize the current status of the engine """
        debug('Waiting for entities to finish loading before saving state')
        tries = 0
#        while self.loading:
#            self.update()
#            tries += 1
#            if tries > 100:
#                debug('Still waiting for loading entities: %s' % self.loading)
#                tries = 0


        #f = open('ignifuga.state', 'w')
        #state = GilbertPickler(f, -1).dump(self.nodes)
        #f.close()

    def loadState(self):
        pass
        # TODO!
#        try:
#            if os.path.isfile('ignifuga.state'):
#                f = open('ignifuga.state', 'r')
#                self.nodes = pickle.load(f)
#                f.close()
#
#                for node in self.nodes:
#                    task = Task(weakref.ref(node), node.init, parent=Task.getcurrent())
#                    self.loading.append((task, None, None))
#
#                return True
#            else:
#                return False
#        except:
#            return False

    def loadScenes(self, data):
        """ Load scenes from a dictionary like structure. The data format is...
        """
        if not isinstance(data, dict):
            return False

        # As scene data may be cached or still referenced when the loop ends,
        # we iterate over a deepcopy of it to avoid a reference circle with entities
        # that prevents them from being garbage collected
        for scene_id, scene_data in copy.deepcopy(data).iteritems():
            self.loadScene(scene_id, scene_data)

    def loadScenesFromFile(self, scenesFile):
        scenes = self.dataManager.loadJsonFile(scenesFile)
        self.loadScenes(scenes)

    def loadScene(self, scene_id, scene_data):
        scene = Scene(id=scene_id, **scene_data)
        self.scenes[scene_id] = scene

    def startScene(self, scene_id):
        if scene_id in self.scenes:
            self.scene = self.scenes[scene_id]
            self.entities = self.scene.entities
            self.scene.sceneInit()
            self.startEntity(self.scene)
            for entity in self.entities.itervalues():
                self.startEntity(entity)

            return True

        return False

    def startFirstScene(self):
        if not self.changeScene(self._firstScene):
            error('Error loading first scene: %s' % self._firstScene)

    def resetScenes(self):
        """ Reset all scene, garbage collect, get ready to leave! """
#        for scene_id in self.scenes.iterkeys():
#            self.resetScene(scene_id)

        self.resetScene()
        self.scenes = {}
        # Clean up cache
        self.dataManager.cleanup()
        gc.collect()

    def resetScene(self):
        """ Reset all the scene information """
        # Make sure all entities finished loading and running
        debug('Waiting for entities to finish loading/running')
        tries = 0
        self._freezeRenderer = True
#        while self.loading or self.running:
#            self.update(wrapup=True)
#            tries += 1
#            if tries > 100:
#                debug('Still waiting for loading entities: %s' % self.loading)
#                debug('Still waiting for running entities: %s' % self.running)
#                tries = 0


        for entity in self.entities.values():
            # Forget about the entity and release data
            entity.unregister()

        del self.entities
        del self.scene
        del self.entitiesByZ
        del self.entitiesByTag
        #del self.loading
        #del self.running

        # Really remove nodes and data
        gc.collect()

        self.scene = None
        self.entities = {}
        self.entitiesByZ = []
        self.entitiesByTag = {}
        #self.loading = {}
        #self.running = {}

        # Clean up cache
        # Do not clean the cache here, there may be useful data for other scenes -> self.dataManager.cleanup()
        gc.collect()

    def changeScene(self, scene_id):
        debug("Switching scene to: %s " % scene_id)
        self.resetScene()
        self.renderer.scrollTo(0,0)
        return self.startScene(scene_id)

    def startEntity(self, entity):
        # Add it to the loading queue
        self.gameLoop.startEntity(entity)

    def stopEntity(self, entity):
        """ Remove node, release its data """
        self.gameLoop.stopEntity(entity)


    def getEmbedded(self, url):
        url = str(url)
        if url in EMBEDDED_IMAGES:
            return base64.b64decode(EMBEDDED_IMAGES[url])

        return None


# Gilbert imports
from Entity import Entity
from components import Component
from Scene import Scene