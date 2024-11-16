"""
This module contains the AstronInternalRepository class, which is the main class
for the Astron internal repository. This class is used to create AI servers and
UberDOG servers using Panda3D. It interfaces with an Astron server to manipulate
objects in the Astron cluster. It does not require any specific "gateway" into the
Astron network. Rather, it just connects directly to any Message Director. Hence,
it is an "internal" repository.
"""

import os

from direct.directnotify import DirectNotifyGlobal
from direct.distributed.PyDatagram import PyDatagram
from direct.distributed.MsgTypes import *
from direct.showbase import ShowBase # __builtin__.config
from direct.task.TaskManagerGlobal import * # taskMgr
from direct.distributed.ConnectionRepository import ConnectionRepository

from panda3d import core as p3d
from panda3d_astron import msgtypes
from panda3d_astron.interfaces import clientagent, database
from panda3d_astron.interfaces import events, state
from panda3d_astron.interfaces import messenger as net_messenger
from panda3d_toolbox import runtime, utils

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

    def __init__(self, baseChannel, maxChannels = 1000000, serverId = None, dcFileNames = None, 
                 dcSuffix = 'AI', connectMethod = None, threadedNet = None):
        """
        Initializes the Astron internal repository.
        """

        # If no connection method was define assumed we should use
        # the native connection method. This is the most performant 
        # option for connecting to the Message Director.
        if connectMethod is None:
            connectMethod = self.CM_NATIVE

        # Iniitlaize our base connection repository
        # instance with the provided connection method and
        # threading options.
        self.interfacesReady = False
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
        self.notify.info('Using State Server %d for object creation' % self.serverId)

        # Setup our channel allocator and register our own channel for communicating
        # our selves to the larger Astron cluster. 
        self.minChannel = baseChannel
        self.maxChannel = self.config.GetInt('air-channel-allocation', baseChannel + maxChannels)
        self.notify.info(f"Dynamic channel range [{self.minChannel}, {self.maxChannel}]. totaling {self.maxChannel - self.minChannel +1} slots.")
        assert self.maxChannel >= self.minChannel
        self.channelAllocator = p3d.UniqueIdAllocator(baseChannel, baseChannel + self.maxChannel - 1)

        self._registeredChannels = set()
        self.ourChannel = self.allocateChannel()

        self.__context_counter = 0
        self.__message_counter = 0

        # Initialize our interface for communicating with Astron
        # server components.
        self.database        = database.AstronDatabaseInterface(self)
        self.net_messenger   = net_messenger.NetMessengerInterface(self)
        self.state_server    = state.StateServerInterface(self)
        self.client_agent    = clientagent.ClientAgentInterface(self)
        self.events          = events.EventLoggerInterface(self)
        self.interfacesReady = True

        # Load the DC files if they were provided.
        self.readDCFile(dcFileNames)

    @property
    def our_channel(self) -> int:
        """
        Gets the channel this AIR is operating on.

        Serves as a legacy bridge to the original ourChannel value
        """

        return self.ourChannel

    def __getattr__(self, key: str) -> object:
        """
        Custom getattr method to allow for easy access to the interfaces. This also 
        serves as a legacy bridge from the old way of commanding the AIR to the new way.
        """

        # Attempt to retrieve the key on our own object first. If they key
        # does not exist attempt to retrieve it from one of our interfaces.
        try:
            return object.__getattribute__(self, key)
        except AttributeError:  
            # TODO: Should this be a flag we have to manange or should we 
            # assume if we've gotten here and the key matches any of our interface attribute names
            # that the interfaces are not ready and we should raise an exception?
            if not self.interfacesReady:
                raise

            # Check if the key is a valid attribute of any of our interfaces.
            # If it is then return the attribute.
            if hasattr(self.database, key):
                getattr(self.database, key)
            elif hasattr(self.net_messenger, key):
                return getattr(self.net_messenger, key)
            elif hasattr(self.state_server, key):
                return getattr(self.state_server, key)
            elif hasattr(self.client_agent, key):
                return getattr(self.client_agent, key)
            elif hasattr(self.events, key):
                return getattr(self.events, key)
        except:
            # An unexpected error occurred while attempting to retrieve the attribute.
            # We should simply raise the error for normal handling.
            raise

    def does_dc_suffix_match(self, suffix: str) -> bool:
        """
        Returns whether the repository's DC suffix matches the provided suffix.

        This function will ignore case when comparing the suffixes.
        """

        lower_suffix = self.dcSuffix.lower()
        lower_match_suffix = suffix.lower()

        return lower_suffix == lower_match_suffix
    
    doesDCSuffixMatch = does_dc_suffix_match

    def is_uberdog(self) -> bool:
        """
        Returns whether the repository is an UberDOG server or not
        """

        return self.does_dc_suffix_match('UD')
    
    isUberDOG = is_uberdog

    def is_ai(self) -> bool:
        """
        Returns whether the repository is an AI server or not
        """

        return self.does_dc_suffix_match('AI')
    
    isAI = is_ai

    def get_game_do_id(self) -> int:
        """
        Gets the distributed id of the root game object as defined by 
        the legacy GameDoId variable.
        """

        return self.getGameDoId()

    def get_context(self) -> int:
        """
        Get a new context ID for a callback.
        """

        self.__context_counter = (self.__context_counter + 1) & 0xFFFFFFFF
        return self.__context_counter
    
    getContext = get_context
    
    def allocate_channel(self) -> None:
        """
        Allocate an unused channel out of this AIR's configured channel space.
        This is also used to allocate IDs for DistributedObjects, since those
        occupy a channel.
        """

        return self.channelAllocator.allocate()
    
    allocateChannel = allocate_channel

    def deallocate_channel(self, channel: int) -> None:
        """
        Return the previously-allocated channel back to the allocation pool.
        """

        self.channelAllocator.free(channel)

    deallocateChannel = deallocate_channel

    def get_location_channel(self, parentId: int, zoneId: int) -> int:
        """
        Get a location channel for the specified parent and zone. This is used
        to receive updates from the State Server about objects in a specific zone.
        """

        return (parentId << 32) | zoneId
    
    getLocationChannel = get_location_channel

    def register_for_channel(self, channel: int) -> None:
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

    registerForChannel = register_for_channel

    def register_for_location_channel(self, parentId: int, zoneId: int) -> None:
        """
        Register for messages on a specific state server zone channel.
        If the channel is already open by this AIR, nothing will happen.
        """

        channel = self.get_location_channel(parentId, zoneId)
        self.registerForChannel(channel)

    registerForLocationChannel = register_for_location_channel

    def unregister_for_channel(self, channel: int) -> None:
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

    unregisterForChannel = unregister_for_channel

    def unregister_for_location_channel(self, parentId: int, zoneId: int) -> None:
        """
        Unregister a location channel subscription on the Message Director. The Message
        Director will cease to relay messages to this AIR sent on the location channel.
        """       
         
        channel = self.get_location_channel(parentId, zoneId)
        self.unregisterForChannel(channel)

    unregisterForLocationChannel = unregister_for_location_channel

    def subscribe_to_zone(self, zoneId: int, parentId: int = None, callback: object = None) -> None:
        """
        Subscribes the server to a network zone and requests all objects in the zone. This is useful
        for UberDOG servers to allow them to receive UD objects in a specific zone. The channel subscription
        is followed up with a get_zone_objects request to ensure we know about all objects already in the zone.
        """

        # If our zone id came from an enum then retrieve the value of it.
        if hasattr(zoneId, 'value'):
            zoneId = zoneId.value

        # if we were not given a parent then assume we want to subscribe
        # to the root global object's children.
        if parentId is None:
            parentId = self.getGameDoId()
            
        self.notify.info(f'Subscribing to network zone ({zoneId}) under parent {parentId}')
        self.register_for_location_channel(parentId, zoneId)

        self.state_server.get_zone_objects(
            parentId=parentId,
            zoneId=zoneId,
            callback=callback)
        
    subscribeToZone = subscribe_to_zone

    def add_post_remove(self, dg: object) -> None:
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

    addPostRemove = add_post_remove

    def clear_post_remove(self) -> None:
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

    clearPostRemove = clear_post_remove

    def get_account_id_from_channel(self, channel: int) -> int:
        """
        Get the account ID of the client connected to the specified channel.
        """

        return (channel >> 32) & 0xFFFFFFFF
    
    getAccountIdFromChannel = get_account_id_from_channel

    def get_avatar_id_from_channel(self, channel: int) -> int:
        """
        Get the avatar ID of the client connected to the specified channel.
        """

        return channel & 0xFFFFFFFF

    getAvatarIdFromChannel = get_avatar_id_from_channel

    def get_account_id_from_sender(self) -> int:
        """
        Get the account ID of the sender of the current message. This only works if the
        client agent set_client_account_id was called previously.
        """

        return self.get_account_id_from_channel(self.getMsgSender())
    
    getAccountIdFromSender = get_account_id_from_sender

    def get_avatar_id_from_sender(self) -> int:
        """
        Get the avatar ID of the sender of the current message. This only works if the
        client agent set_client_id was called previously.
        """

        return self.get_avatar_id_from_channel(self.getMsgSender())
    
    getAvatarIdFromSender = get_avatar_id_from_sender

    def register_net_messager_event(self, message: int) -> None:
        """
        Registers a new event with the NetMessenger. This is useful for
        broadcasting messenger events across the entire internal cluster.
        """

        self.net_messenger.register(self.__message_counter, message)
        self.__message_counter += 1

    def handle_datagram(self, di: object) -> None:
        """
        Handle a datagram received from the Message Director.
        """

        msg_type = self.getMsgType()
        if msgtypes.is_state_server_message(msg_type) or \
           msgtypes.is_database_state_server_message(msg_type):
            self.state_server.handle_datagram(msg_type, di)
        elif msgtypes.is_database_server_message(msg_type):
            self.database.handle_datagram(msg_type, di)
        elif msgtypes.is_client_agent_message(msg_type):
            self.client_agent.handle_datagram(msg_type, di)
        elif msgtypes.is_net_messenger_message(msg_type):
            self.net_messenger.handle_datagram(msg_type, di)
        else:
            self.notify.warning('Received message with unknown MsgType=%d' % msg_type)

    handleDatagram = handle_datagram

    def send_update(self, do, fieldName, args):
        """
        Send a field update for the given object.
        You should use do.sendUpdate(...) instead. This is not meant to be
        called directly unless you really know what you are doing.
        """

        self.send_update_to_channel(do, do.doId, fieldName, args)

    sendUpdate = send_update

    def send_update_to_channel(self, do, channelId, fieldName, args):
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
    
    sendUpdateToChannel = send_update_to_channel

    def connect(self, host: str, port: int = 7199) -> None:
        """
        Connect to a Message Director. The airConnected message is sent upon
        success.
        N.B. This overrides the base class's connect(). You cannot use the
        ConnectionRepository connect() parameters.
        """

        url = p3d.URLSpec()
        url.set_server(host)
        url.set_port(port)

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
        self.register_for_channel(self.ourChannel)

        # If we're configured with a State Server, register a post-remove to
        # clean up whatever objects we own on this server should we unexpectedly
        # fall over and die.
        if self.serverId:
            self.state_server.register_delete_ai_objects_post_remove(self.serverId)

        runtime.messenger.send('airConnected')
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

    lostConnection = lost_connection # Legacy carry-over

    def generate_global_object_if_configured(self, object_id: int, object_name: str, config_name: str = '', guarantee: bool = False) -> object:
        """
        Generates a distributed object global if it was requested at startup. This is used for
        generating certain global objects across different instances of the UberDOG server.

        When this method is called by an AI repository instance it is guaranteed to generate the object
        to ensure the AI can properly communicate with whichever UberDOG server the object is on.

        An optional guarantee flag can be set to force the object to be generated regardless of the configuration.
        """

        # Verify the requested object exists in our dclass schema
        dclass_name = f'{object_name}{self.dcSuffix}'
        if not self.dclassesByName.get(dclass_name):
            self.notify.warning(f'Could not find dclass for global object {object_name}')
            return

        # If our object id came from an int enum then retrieve
        # the value of it.
        if hasattr(object_id, 'value'):
            object_id = object_id.value

        # If the config name was not supplied then generate it from the object name.
        # It should match the name of the object turned snake case and upper case. E.g.
        # DistributedAccountManager -> DISTRIBUTED_ACCOUNT_MANAGER
        if config_name == '':
            config_name = utils.get_snake_case(object_name)
            config_name = config_name.upper()

        # Check if the object's environment variable flag was set on startup,
        # we are running in development mode, or this repository represents an AI server. If any
        # of these conditions are met then we should generate the object.
        should_generate = int(os.environ.get(config_name, '0')) or guarantee or self.is_ai()
        if should_generate or runtime.__dev__:
            self.notify.info(f'Generating global object {object_name} with id {object_id}')
            return self.generate_global_object(object_id, object_name)

        return None
    
    # Exists as a legacy bridge to the original Panda3D generateGlobalObject method
    def generate_global_object(self, doId: int, dcname: str, values: list = None) -> object:
        """
        Generates a global object with the specified doId and dclass name.
        """

        return self.generateGlobalObject(doId, dcname, values)