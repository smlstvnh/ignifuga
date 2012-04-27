#Copyright (c) 2010-2012, Gabriel Jacobo
#All rights reserved.
#Permission to use this file is granted under the conditions of the Ignifuga Game Engine License
#whose terms are available in the LICENSE file or at http://www.ignifuga.org/license

# Ignifuga Game Engine
# Base Entity class
# Author: Gabriel Jacobo <gabriel@mdqinc.com>

from ignifuga.Gilbert import Event, Gilbert, Signal
from ignifuga.Log import error
from ignifuga.components.Component import Component

import weakref



class Entity(object):

    class __metaclass__(type):
        # Metaclass builds a list of all the components in __inheritors__
        __inheritors__ = {}
        def __new__(meta, name, bases, dct):
            klass = type.__new__(meta, name, bases, dct)
            meta.__inheritors__[name] = klass
            return klass

    @classmethod
    def create(cls, type='Entity', **data):
        """ Create component based on a data dict """
        if type in Entity.__inheritors__:
            entity = Entity.__inheritors__[type](**data)
            return entity
        return None


    ###########################################################################
    # Initialization, deletion, overlord registration functions
    ###########################################################################
    def __init__(self, **kwargs):
        # Initialize internal fields
        self.id = None
        self._released = False
        self._components = {}
        self._componentsByTag = {}
        self._componentsBySignal = {}
        self._properties = {}
        self.tags = []
        self.signalQueue = []

        """
        Preprocess kwargs

        kwargs may be:
            {'id': nodeid, 'components': [{'type':'position','x':1.0,'y':1.0}, {'type':'sprite',image:'test.png'}, etc]} or
            {'nodeid': {'components': [{'type':'position','x':1.0,'y':1.0}, {'type':'sprite',image:'test.png'}, etc] }

        """
        data = {}
        if kwargs.has_key('id'):
            self.id = unicode(kwargs['id'])
            del kwargs['id']
            data = kwargs
        elif len(kwargs.keys())==1:
            self.id = unicode(kwargs.keys()[0])
            data = kwargs[self.id]
        else:
            data = kwargs
            self.id = None

        if 'scene' in kwargs:
            self.scene = weakref.ref(kwargs['scene'])
            del kwargs['scene']
        else:
            self.scene = None

        # Process the data, load the components from it
        self.load(data)

        # Fix the id in case it wasn't specified
        if self.id == None:
            self.id = hash(self)

    def __del__(self):
        if not self._released:
            self.__free__()

    def __free__(self):
        """ This free function exists to break the dependency cycle among entities, components, etc
        If we wait to do what's done here in __del__ the cycle of dependencies is never broken and the data
        won't be garbage collected. It should be only called from __del__ or unregister """

        if self._released:
            error("Node %s released more than once" % self.id)

        self._components = {}
        self._componentsByTag = {}
        self._componentsBySignal = {}
        self._properties = {}
        self._released = True

    def __str__(self):
        return "Entity with ID %s" % (self.id,)

    def init(self,data):
        """ Initialize the required external data """
        components = self._components.keys()
        failcount = {}
        while components:
            component = components.pop(0)
            try:
                self._components[component].init(**data)
            except:
                # Something failed, try it again later
                if component not in failcount:
                    failcount[component] = 1
                else:
                    failcount[component] += 1
                if failcount[component] < 10:
                    components.append(component)
                else:
                    error('Failed initializing component %s' % component)
        return self

    def register(self):
        """ Register Entity with the Overlord """
        Gilbert().registerNode(self)

    def unregister(self):
        """ Unregister Entity with the Overlord """
        Gilbert().stopEntity(self)
        # Break dependency cycles
        if not self._released:
            self.__free__()

    ###########################################################################
    # Persistence, serialization related functions
    ###########################################################################
    def load(self, data):
        """ Load components from given data
        data has the format may be:
        { 'components': [{'id':'something', 'type':'position','x':1.0,'y':1.0}, {id:'somethingelse', 'type':'sprite',image:'test.png'}, etc], otherdata }
        { 'components': {'something':{'type':'position','x':1.0,'y':1.0}, 'somethingelse': {'type':'sprite',image:'test.png'}, etc}, otherdata }

        The key of each entry
        """
        if 'components' in data:
            if isinstance(data['components'], dict):
                for c_id, c_data in data['components'].iteritems():
                    c_data['id'] = c_id
                    c_data['entity'] = self
                    Component.create(**c_data)
            elif isinstance(data['components'], list):
                for c_data in data['components']:
                    c_data['entity'] = self
                    Component.create(**c_data)

    def __getstate__(self):
        odict = self.__dict__.copy()
        # These dont exist in self.__dict__ as they come from Cython (some weird voodoo, right?)...
        # So, we have to add them by hand for them to be pickled correctly
#        odict['id'] = self.id
#        odict['released'] = self._released
#        odict['components'] = self._components
#        odict['componentsByTag'] = self._componentsByTag
#        odict['componentsBySignal'] = self._componentsBySignal
#        odict['tags'] = self.tags
        return odict

#    def __reduce__(self):
#        return type(self), (None,), self.__getstate__()

    def __setstate__(self, data):
        for k,v in data.iteritems():
            setattr(self, k, v)


    ###########################################################################
    # Component handling, tags, properties
    ###########################################################################

    def getComponent(self, id):
        """ Retrieve a component with a given id, return None if no component by that id is found"""
        if id in self._components:
            return self._components[id]

        return None

    def getComponentsByTag(self, tags):
        """ Return a unique list of the components matching the tags or tag provided """
        if isinstance(tags, basestring):
            tags = [tags,]

        components = []

        for tag in tags:
            if tag in self._componentsByTag:
                for component in self._componentsByTag[tag]:
                    if component not in components:
                        components.append(component)

        return components

    def add(self, component):
        """ Add a component to the entity"""
        if component.id in self._components and self._components[component.id] != component:
            error('Entity %s already has a different component with id %s' % (self, component.id))
            return
        self._components[component.id] = component

        if component.entity != self:
            component.entity = self

        if component.active:
            self.addProperties(component)
            self.addTags(component.entityTags)
            for tag in component.tags:
                if tag not in self._componentsByTag:
                    self._componentsByTag[tag] = []
                self._componentsByTag[tag].append(component)



    def remove(self, component):
        """ Remove a component from the entity (accepts either the component object or the id) """
        if not isinstance(component, Component):
            if component in self._components:
                component = self._components[component]
            else:
                return

        if component in self._components:
            del self._components[component]
            self.removeProperties(component)

        self.refreshTags()

    def addProperties(self, component):
        """ Adopt the component public properties"""
        for property in component.properties:
            self._properties[property] = component

    def removeProperties(self, component):
        """ Remove the component public properties"""
        for property in component.properties:
            if property in self._properties and self._properties[property] == component:
                del self._properties[property]

    def addTags(self, tags):
        """ Add one tag or a list of tags to the entity"""
        if isinstance(tags, basestring):
            tags = [tags,]

        for tag in tags:
            if tag not in self.tags:
                self.tags.append(tag)

        Gilbert().refreshEntityTags(self, tags)

    def removeTags(self, tags):
        """ Remove one tag or a list of tags to the entity"""
        if isinstance(tags, basestring):
            tags = [tags,]

        for tag in tags:
            if tag in self.tags:
                self.tags.remove(tag)

        Gilbert().refreshEntityTags(self, [], tags)

    def refreshTags(self):
        # Refresh the entity tags
        oldTags = set(self.tags)
        self.tags = []
        for component in self._components.itervalues():
            if component.active:
                self.addTags(component.entityTags)

        # Update tag index in the Gilbert overlord
        newTags = set(self.tags)
        Gilbert().refreshEntityTags(self, list(newTags-oldTags), list(oldTags-newTags))

    ###########################################################################
    # Update functions
    ###########################################################################
    def update(self, data):
        """ Public customizable update function """
        pass

    def _update(self, data):
        """ Internal update function, updates components, etc, runs IN PARALLEL with update """
        # Dispatch signals
        for signal in self.signalQueue:
            self.directSignal(signal['signal'], signal['sender'], signal['target'], signal['data'])

        self.signalQueue = []

        # Run the active components update loop
        for component in self._components.itervalues():
            if component.active:
                component.update(**data)

    # Events from the overlord
    def event(self, event):
        # Handle an event, return: bool1, bool2
        #bool1: False if the event has to cancel propagation
        #bool2: True if the node wants to capture the subsequent events
        # Send the event as directSignals to subscribed components.

        #Don't capture ethereal events
        continuePropagation, captureEvent = True, False

        if event.type in (Event.TYPE.touchdown, Event.TYPE.touchup, Event.TYPE.touchmove):
            signal = Signal.touches
        elif event.type in (Event.TYPE.zoomin, Event.TYPE.zoomout):
            signal = Signal.zoom
        elif event.type == Event.TYPE.scroll:
            signal = Signal.scroll
        else:
            return continuePropagation, captureEvent

        if signal in self._componentsBySignal:
            for component in self._componentsBySignal[signal]:
                continuePropagation, captureEvent = component.slot(signal, self, event=event)
                if not continuePropagation:
                    break
        return continuePropagation, captureEvent


    ###########################################################################
    # Signal handling
    ###########################################################################

    def subscribe(self, component, signal):
        """ Components subscribe to signals using this function """
        if signal not in self._componentsBySignal:
            self._componentsBySignal[signal] = []

        if component not in self._componentsBySignal[signal]:
            self._componentsBySignal[signal].append(component)

    def unsubscribe(self, component, signal=None):
        """ Components unsubscribe to signals using this function, if signal=None, unsubscribe from all signals """
        if signal == None:
            signals = self._componentsBySignal
        else:
            signals = [signal,]

        for signal in signals:
            if signal in self._componentsBySignal:
                if component in self._componentsBySignal[signal]:
                    self._componentsBySignal[signal].remove(component)
                    if not self._componentsBySignal[signal]:
                        del self._componentsBySignal[signal]

    def signal(self, signal_name, sender=None, target=None, tags = [], subscribers = True, **data):
        """ Function used to send signals to components via a queue (signals are processed in the next update) """
        if target != None:
            targets = [target,]
        else:
            targets = []

        # Send to tags
        if isinstance(tags, basestring):
            tags = [tags,]
        for tag in tags:
            if tag in self._componentsByTag:
                for component in self._componentsByTag[tag]:
                    if component not in targets:
                        targets.append(target)

        if subscribers and signal_name in self._componentsBySignal:
            for component in self._componentsBySignal[signal_name]:
                if component not in targets:
                    targets.append(component)

        for target in targets:
            self.signalQueue.append({'signal': signal_name, 'sender': sender, 'target': target, 'data': data})

    def directSignal(self, signal_name, sender=None, target=None, **data):
        """ Function used to send direct signals to components """
        if target != None and not isinstance(target, Component):
            if target in self._components:
                target = self._components[target]
            else:
                return
        if target.active:
            return target.slot(signal_name, sender, **data)

        return None

    ###########################################################################
    # Properties routing
    ###########################################################################
    def __getattr__( self, name):
        if name == "_properties":
            # If a request for _properties arrives here it means it doesn't yet exist. So, we just create it
            self.__dict__['_properties'] =  {}
            return self.__dict__['_properties']
        if name == '_components':
            self.__dict__['_components'] =  {}
            return self.__dict__['_components']

        if name in self._properties:
            return getattr(self._properties[name], name)

        if name in self._components:
            return self._components[name]

        raise AttributeError('%s does not have a "%s" attribute. Properties are: %s ' % (self, name, self._properties))

    def __setattr__( self, name, value):
        if name in self._properties:
            return setattr(self._properties[name], name, value)
        super(Entity, self).__setattr__(name, value)
