"""
This module contains the AstronInternalRepository class, which is the main class
for the Astron internal repository. This class is used to create AI servers and
UberDOG servers using Panda3D. It interfaces with an Astron server to manipulate
objects in the Astron cluster. It does not require any specific "gateway" into the
Astron network. Rather, it just connects directly to any Message Director. Hence,
it is an "internal" repository.
"""

from direct.directnotify import DirectNotifyGlobal
from direct.distributed.PyDatagram import PyDatagram
from direct.distributed.MsgTypes import *
from direct.showbase import ShowBase # __builtin__.config
from direct.task.TaskManagerGlobal import * # taskMgr
from direct.distributed.ConnectionRepository import ConnectionRepository
from direct.distributed.PyDatagramIterator import PyDatagramIterator

from panda3d import core as p3d
from panda3d.direct import STUint16, STUint32, DCPacker
from panda3d_astron import msgtypes
from panda3d_astron.interfaces import clientagent, database
from panda3d_astron.interfaces import events, state
from panda3d_astron.interfaces import messenger
from panda3d_toolbox import runtime, utils

import collections

class AstronInternalRepository(ConnectionRepository):
    """
    This class is part of Panda3D's new MMO networking framework.
    It interfaces with an Astron (https://github.com/Astron/Astron) server in
    order to manipulate objects in the Astron cluster. It does not require any
    specific "gateway" into the Astron network. Rather, it just connects directly
    to any Message Director. Hence, it is an "internal" repository.

    This class is suitable for constructing your own AI Servers and UberDOG servers
    using Panda3D. Objects with a "self.air" attribute are referring to an instance
    of this class.
    """

    notify = DirectNotifyGlobal.directNotify.newCategory("repository")

    def __init__(self, baseChannel, serverId=None, dcFileNames = None, 
                 dcSuffix = 'AI', connectMethod = None, threadedNet = None):
        """
        Initializes the Astron internal repository.
        """

        if connectMethod is None:
            connectMethod = self.CM_NATIVE
        
        ConnectionRepository.__init__(self, 
            connectMethod = connectMethod, 
            config = runtime.config, 
            hasOwnerView = False, 
            threadedNet = threadedNet)
        
        self.setClientDatagram(False)
        self.dcSuffix = dcSuffix

        if hasattr(self, 'setVerbose'):
            if self.config.GetBool('verbose-internalrepository'):
                self.setVerbose(1)

        # The State Server we are configured to use for creating objects.
        # If this is None, generating objects is not possible.
        self.serverId = self.config.GetInt('air-stateserver', 0) or None
        if serverId is not None:
            self.serverId = serverId

        maxChannels = self.config.GetInt('air-channel-allocation', 1000000)
        self.channelAllocator = p3d.UniqueIdAllocator(baseChannel, baseChannel + maxChannels - 1)
        self._registeredChannels = set()

        self.ourChannel = self.allocateChannel()
        self.__contextCounter = 0

        self.database       = database.AstronDatabaseInterface(self)
        self.netMessenger   = messenger.NetMessengerInterface(self)
        self.stateServer    = state.StateServerInterface(self)
        self.clientAgent    = clientagent.ClientAgentInterface(self)
        self.events         = events.EventLoggerInterface(self)

        self.readDCFile(dcFileNames)

    def __getattr__(self, key: str) -> object:
        """
        Custom getattr method to allow for easy access to the interfaces. This also 
        serves as a legacy bridge from the old way of commanding the AIR to the new way.
        """

        if key.startswith('handle_'):
            return AttributeError('No attribute named %s' % key)
        
        snake_case_key = utils.get_snake_case(key)
        if hasattr(self, snake_case_key):
            return getattr(self, snake_case_key)
        elif hasattr(self.database, snake_case_key):
            return getattr(self.database, snake_case_key)
        elif hasattr(self.netMessenger, snake_case_key):
            return getattr(self.netMessenger, snake_case_key)
        elif hasattr(self.stateServer, snake_case_key):
            return getattr(self.stateServer, snake_case_key)
        elif hasattr(self.clientAgent, snake_case_key):
            return getattr(self.clientAgent, snake_case_key)
        elif hasattr(self.events, snake_case_key):
            return getattr(self.events, snake_case_key)
        else:
            raise AttributeError('No attribute named %s' % key)

    def get_context(self) -> int:
        """
        Get a new context ID for a callback.
        """

        self.__contextCounter = (self.__contextCounter + 1) & 0xFFFFFFFF
        return self.__contextCounter
    
    def allocate_channel(self):
        """
        Allocate an unused channel out of this AIR's configured channel space.
        This is also used to allocate IDs for DistributedObjects, since those
        occupy a channel.
        """

        return self.channelAllocator.allocate()

    def deallocate_channel(self, channel):
        """
        Return the previously-allocated channel back to the allocation pool.
        """

        self.channelAllocator.free(channel)

    def register_for_channel(self, channel):
        """
        Register for messages on a specific Message Director channel.
        If the channel is already open by this AIR, nothing will happen.
        """

        if channel in self._registeredChannels:
            return
        self._registeredChannels.add(channel)

        dg = PyDatagram()
        dg.addServerControlHeader(msgtypes.CONTROL_ADD_CHANNEL)
        dg.addChannel(channel)
        self.send(dg)

    def unregister_for_channel(self, channel):
        """
        Unregister a channel subscription on the Message Director. The Message
        Director will cease to relay messages to this AIR sent on the channel.
        """

        if channel not in self._registeredChannels:
            return
        self._registeredChannels.remove(channel)

        dg = PyDatagram()
        dg.addServerControlHeader(msgtypes.CONTROL_REMOVE_CHANNEL)
        dg.addChannel(channel)
        self.send(dg)

    def add_post_remove(self, dg):
        """
        Register a datagram with the Message Director that gets sent out if the
        connection is ever lost.
        This is useful for registering cleanup messages: If the Panda3D process
        ever crashes unexpectedly, the Message Director will detect the socket
        close and automatically process any post-remove datagrams.
        """

        dg2 = PyDatagram()
        dg2.addServerControlHeader(msgtypes.CONTROL_ADD_POST_REMOVE)
        dg2.add_uint64(self.ourChannel)
        dg2.add_blob(dg.getMessage())
        self.send(dg2)

    def clear_post_remove(self):
        """
        Clear all datagrams registered with addPostRemove.
        This is useful if the Panda3D process is performing a clean exit. It may
        clear the "emergency clean-up" post-remove messages and perform a normal
        exit-time clean-up instead, depending on the specific design of the game.
        """

        dg = PyDatagram()
        dg.addServerControlHeader(msgtypes.CONTROL_CLEAR_POST_REMOVES)
        dg.add_uint64(self.ourChannel)
        self.send(dg)

    def handle_datagram(self, di: object) -> None:
        """
        Handle a datagram received from the Message Director.
        """

        msg_type = self.getMsgType()
        if msgtypes.is_state_server_message(msg_type) or \
           msgtypes.is_database_state_server_message(msg_type):
            self.stateServer.handle_datagram(msg_type, di)
        elif msgtypes.is_database_server_message(msg_type):
            self.database.handle_datagram(msg_type, di)
        elif msgtypes.is_client_agent_message(msg_type):
            self.clientAgent.handle_datagram(msg_type, di)
        elif msgtypes.is_net_messenger_message(msg_type):
            self.netMessenger.handle_datagram(msg_type, di)
        else:
            self.notify.warning('Received message with unknown MsgType=%d' % msg_type)

    def sendUpdate(self, do, fieldName, args):
        """
        Send a field update for the given object.
        You should use do.sendUpdate(...) instead. This is not meant to be
        called directly unless you really know what you are doing.
        """

        self.sendUpdateToChannel(do, do.doId, fieldName, args)

    def sendUpdateToChannel(self, do, channelId, fieldName, args):
        """
        Send an object field update to a specific channel.
        This is useful for directing the update to a specific client or node,
        rather than at the State Server managing the object.
        You should use do.sendUpdateToChannel(...) instead. This is not meant
        to be called directly unless you really know what you are doing.
        """

        dclass = do.dclass
        field = dclass.getFieldByName(fieldName)
        dg = field.aiFormatUpdate(do.doId, channelId, self.ourChannel, args)
        self.send(dg)

    def sendActivate(self, doId, parentId, zoneId, dclass=None, fields=None):
        """
        Activate a DBSS object, given its doId, into the specified parentId/zoneId.
        If both dclass and fields are specified, an ACTIVATE_WITH_DEFAULTS_OTHER
        will be sent instead. In other words, the specified fields will be
        auto-applied during the activation.
        """

        fieldPacker = DCPacker()
        fieldCount = 0
        if dclass and fields:
            for k,v in fields.items():
                field = dclass.getFieldByName(k)
                if not field:
                    self.notify.error('Activation request for %s object contains '
                                      'invalid field named %s' % (dclass.getName(), k))

                fieldPacker.rawPackUint16(field.getNumber())
                fieldPacker.beginPack(field)
                field.packArgs(fieldPacker, v)
                fieldPacker.endPack()
                fieldCount += 1

            dg = PyDatagram()
            dg.addServerHeader(doId, self.ourChannel, msgtypes.DBSS_OBJECT_ACTIVATE_WITH_DEFAULTS)
            dg.addUint32(doId)
            dg.addUint32(0)
            dg.addUint32(0)
            self.send(dg)
            # DEFAULTS_OTHER isn't implemented yet, so we chase it with a SET_FIELDS
            dg = PyDatagram()
            dg.addServerHeader(doId, self.ourChannel, msgtypes.STATESERVER_OBJECT_SET_FIELDS)
            dg.addUint32(doId)
            dg.addUint16(fieldCount)
            dg.appendData(fieldPacker.getBytes())
            self.send(dg)
            # Now slide it into the zone we expect to see it in (so it
            # generates onto us with all of the fields in place)
            dg = PyDatagram()
            dg.addServerHeader(doId, self.ourChannel, msgtypes.STATESERVER_OBJECT_SET_LOCATION)
            dg.addUint32(parentId)
            dg.addUint32(zoneId)
            self.send(dg)
        else:
            dg = PyDatagram()
            dg.addServerHeader(doId, self.ourChannel, msgtypes.DBSS_OBJECT_ACTIVATE_WITH_DEFAULTS)
            dg.addUint32(doId)
            dg.addUint32(parentId)
            dg.addUint32(zoneId)
            self.send(dg)

    # Legacy method for the original Panda3D Distributed Object implementation
    def sendSetLocation(self, do: object, parentId: int, zoneId: int) -> None:
        """
        Send a SET_LOCATION message to the State Server to move the object to the
        specified parentId/zoneId.
        """

        self.stateServer.set_location(do, parentId, zoneId)

    def generateWithRequired(self, do, parentId, zoneId, optionalFields=[]):
        """
        Generate an object onto the State Server, choosing an ID from the pool.
        You should use do.generateWithRequired(...) instead. This is not meant
        to be called directly unless you really know what you are doing.
        """

        doId = self.allocateChannel()
        self.generateWithRequiredAndId(do, doId, parentId, zoneId, optionalFields)

    def generateWithRequiredAndId(self, do, doId, parentId, zoneId, optionalFields=[]):
        """
        Generate an object onto the State Server, specifying its ID and location.
        You should use do.generateWithRequiredAndId(...) instead. This is not
        meant to be called directly unless you really know what you are doing.
        """

        do.doId = doId
        self.addDOToTables(do, location=(parentId, zoneId))
        do.sendGenerateWithRequired(self, parentId, zoneId, optionalFields)

    def connect(self, host: str, port: int = 7199) -> None:
        """
        Connect to a Message Director. The airConnected message is sent upon
        success.
        N.B. This overrides the base class's connect(). You cannot use the
        ConnectionRepository connect() parameters.
        """

        url = p3d.URLSpec()
        url.setServer(host)
        url.setPort(port)

        self.notify.info('Now connecting to %s:%s...' % (host, port))
        ConnectionRepository.connect(self, [url],
                                     successCallback=self.__connected,
                                     failureCallback=self.__connect_failed,
                                     failureArgs=[host, port])

    def __connected(self) -> None:
        """
        Handle a successful connection.
        """

        # Listen to our channel...
        self.notify.info('Connected successfully.')
        self.registerForChannel(self.ourChannel)

        # If we're configured with a State Server, register a post-remove to
        # clean up whatever objects we own on this server should we unexpectedly
        # fall over and die.
        if self.serverId:
            self.stateServer.register_delete_ai_objects_post_remove(self.serverId)

        messenger.send('airConnected')
        self.handle_connected()

    def __connect_failed(self, code: int, explanation: str, host: str, port: int) -> None:
        """
        Handle a failed connection attempt.
        """

        self.notify.warning('Failed to connect! (code=%s; %r)' % (code, explanation))
        retryInterval = runtime.config.GetFloat('air-reconnect-delay', 5.0)
        taskMgr.doMethodLater(retryInterval, self.connect, 'Reconnect delay', extraArgs=[host, port])

    def handle_connected(self):
        """
        Subclasses should override this if they wish to handle the connection
        event.
        """

    def lost_connection(self) -> None:
        """
        Handle a lost connection to the Message Director.
        """

        # This should be overridden by a subclass if unexpectedly losing connection
        # is okay.
        self.notify.error('Lost connection to gameserver!')
