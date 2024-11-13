"""
Client Agent Interface for Astron
"""

import enum

from direct.directnotify import DirectNotifyGlobal
from direct.distributed.PyDatagram import PyDatagram
from direct.distributed.PyDatagramIterator import PyDatagramIterator

from panda3d import direct
from panda3d import core as p3d
from panda3d_astron import msgtypes

class ClientState(enum.IntEnum):
    """
    Possible states for a client connection. These are used to track the state of a client
    and control the client's access to the game world.
    """

    CLIENT_STATE_NEW            = 0
    CLIENT_STATE_ESTABLISHED    = 2
    CLIENT_STATE_DISCONNECTED   = 3

class ClientEjectCodes(enum.IntEnum):
    """
    Constant network eject codes that are used to indicate the reason for ejecting a client.
    """

    EJECT_LOGGED_IN_ELSE_WHERE           = 100

    EJECT_OVERSIZED_DATAGRAM             = 106
    EJECT_INVALID_FIRST_MSG              = 107
    EJECT_INVALID_MSGTYPE                = 108
    EJECT_INVALID_MSGSIZE                = 109

    EJECT_SANDBOX_VIOLATION              = 113
    EJECT_ILLEGAL_INTEREST_OP            = 115
    EJECT_MANIP_INVALID_OBJECT           = 117
    EJECT_PERM_VIOLATION_SET_FIELD       = 118
    EJECT_PERM_VIOLATION_SET_LOCATION    = 119

    EJECT_LOGIN_ISSUE                    = 122

    EJECT_INVALID_VERSION                = 124
    EJECT_INVALID_HASH                   = 125
    EJECT_ADMIN_ACCESS_VIOLATION         = 126

    EJECT_ADMIN_EJECTED                  = 151
    EJECT_MOD_EJECTED                    = 152
    EJECT_ANTI_CHEAT_EJECTED             = 153
    EJECT_GAMESERVER_MAINTENANCE         = 154
    EJECT_GAMESERVER_PROCESSING_ERROR    = 155

    EJECT_HEARTBEAT_TIMEOUT              = 345
    EJECT_SERVER_PROCESSING_ERROR        = 346
    EJECT_CLIENT_AGENT_IO_SEND_ERROR     = 347
    EJECT_CLIENT_AGENT_IO_READ_ERROR     = 348
    EJECT_SERVER_IO_SEND_ERROR           = 349
    EJECT_SERVER_IO_READ_ERROR           = 350

class ClientAgentInterface(object):
    """
    Network interface for the client agent.
    """

    def __init__(self, air: object):
        """
        Initialize the client agent interface.
        """

        self.air = air
        self.__callbacks = {}

    @property
    def notify(self) -> object:
        """
        Retrieves the parent repositories notify object
        """

        return self.air.notify

    def handle_datagram(self, msg_type: int, di: object) -> None:
        """
        Handles client agent datagrams
        """

        if msg_type == msgtypes.CLIENTAGENT_GET_NETWORK_ADDRESS_RESP:
            self.handle_get_network_address_resp(di)
        elif msg_type == msgtypes.CLIENTAGENT_GET_TLVS_RESP:
            self.handle_get_tlvs_response(di)
        elif msg_type == msgtypes.CLIENTAGENT_DONE_INTEREST_RESP:
            self.handle_client_agent_interest_done_resp(di)
        else:
            message_name = msgtypes.MsgId2Names.get(msg_type, str(msg_type))
            self.notify.warning('Received unknown client agent message: %s' % message_name)

    def set_client_state(self, clientChannel: int, state: int) -> None:
        """
        Sets the state of the client on the CA.
        Useful for logging in and logging out, and for little else.
        """

        # If we were given an enum, convert it to its value
        if hasattr(state, 'value'):
            state = state.value

        # Build and send the datagram
        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_SET_STATE)
        dg.add_uint16(state)

        self.air.send(dg)

    setClientState = set_client_state

    def set_client_state_new(self, clientChannel: int) -> None:
        """
        Sets the state of the client to CLIENT_STATE_NEW.
        """

        self.set_client_state(clientChannel, ClientState.CLIENT_STATE_NEW)

    setClientStateNew = set_client_state_new

    def set_client_state_established(self, clientChannel: int) -> None:
        """
        Sets the state of the client to CLIENT_STATE_ESTABLISHED.
        """

        self.set_client_state(clientChannel, ClientState.CLIENT_STATE_ESTABLISHED)

    setClientStateEstablished = set_client_state_established

    def set_client_id(self, clientChannel: int, clientId: int) -> None:
        """
        Changes the sender used to represent this client. This is useful if application/game components need to identify the avatar/account a given message came from: 
        by changing the sender channel to include this information, the server can easily determine the account ID of a client that sends a field update.

        Note: This also results in the CA opening the new channel, if it isn't open already.
        """

        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_SET_CLIENT_ID)
        dg.add_uint64(clientId)

        self.air.send(dg)

    setClientId = set_client_id

    def set_client_account_id(self, clientChannel: int, accountId: int) -> None:
        """
        Changes the client id associated with the client channel to reflect the account the client is authenticated with. This is useful if application/game components need to identify the account a given message came from.
        by changing the sender channel to include this information, the server can easily determine the account ID of a client that sends a field update.

        Note: This also results in the CA opening the new channel, if it isn't open already.
        """

        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_SET_CLIENT_ID)
        dg.add_uint64(accountId << 32)

        self.air.send(dg)

    setAccountId = set_client_account_id

    def set_client_avatar_id(self, clientChannel: int, avatarId: int) -> None:
        """
        Changes the client id associated with the client channel to reflect the avatar the client is authenticated with. This is useful if application/game components need to identify the avatar a given message came from.
        by changing the sender channel to include this information, the server can easily determine the avatar ID of a client that sends a field update.

        Note: This also results in the CA opening the new channel, if it isn't open already.
        """

        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_SET_CLIENT_ID)
        dg.add_uint64(clientChannel << 32 | avatarId)

        self.air.send(dg)

    setAvatarId = set_client_avatar_id

    def remove_client_avatar_id(self, clientChannel: int) -> None:
        """
        Changes the client id associated with the client channel to reflect the avatar the client is authenticated with. This is useful if application/game components need to identify the avatar a given message came from.
        by changing the sender channel to include this information, the server can easily determine the account ID of a client that sends a field update.
        """

        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_SET_CLIENT_ID)
        dg.add_uint64(clientChannel << 32)

        self.air.send(dg)

    removeAvatarId = remove_client_avatar_id

    def send_client_datagram(self, clientChannel: int, datagram: PyDatagram) -> None:
        """
        Send a raw datagram down the pipe to the client. This is useful for sending app/game-specific messages to the client, debugging, etc.
        """

        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_SEND_DATAGRAM)
        dg.add_string(datagram.getMessage())

        self.air.send(dg)

    def eject(self, clientChannel: int, reasonCode: int, reason: str) -> None:
        """
        Kicks the client residing at the specified clientChannel, using the specifed reasoning.
        """

        # If we were given an enum, convert it to its value
        if hasattr(reasonCode, 'value'):
            reasonCode = reasonCode.value

        # Build and send the datagram
        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_EJECT)
        dg.add_uint16(reasonCode)
        dg.add_string(reason)

        self.air.send(dg)

    Eject = eject

    def drop(self, clientChannel: int) -> None:
        """
        Similar to eject, but causes the CA to silently close the client connection, providing no explanation whatsoever to the client.
        """

        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_DROP)

        self.air.send(dg)

    Drop = drop

    def get_client_network_address(self, clientId: int, callback: object) -> None:
        """
        Get the endpoints of a client connection.
        You should already be sure the client actually exists, otherwise the
        callback will never be called.
        Callback is called as: callback(remoteIp, remotePort, localIp, localPort)
        """

        ctx = self.air.get_context()
        self.__callbacks[ctx] = callback

        dg = PyDatagram()
        dg.addServerHeader(clientId, self.air.ourChannel, msgtypes.CLIENTAGENT_GET_NETWORK_ADDRESS)
        dg.add_uint32(ctx)

        self.air.send(dg)

    getClientNetworkAddress = get_client_network_address

    def handle_get_network_address_resp(self, di: object) -> None:
        """
        Handle the response to a get_network_address request.
        """

        ctx        = di.get_uint32()
        remoteIp   = di.get_string()
        remotePort = di.get_uint16()
        localIp    = di.get_string()
        localPort  = di.get_uint16()

        if ctx not in self.__callbacks:
            self.notify.warning('Received unexpected CLIENTAGENT_GET_NETWORK_ADDRESS_RESP (ctx: %d)' % ctx)
            return

        try:
            self.__callbacks[ctx](remoteIp, remotePort, localIp, localPort)
        finally:
            del self.__callbacks[ctx]

    def declare_object(self, clientChannel: int, doId: int, zoneId: int) -> None:
        """
        Because Client Agents verify the integrity of field updates, they must know the dclass of a given object to ensure that the incoming field update is for a field that the dclass/object actually has. 
        Therefore, clients are normally unable to send messages to objects unless they are either configured as an UberDOG or are currently visible to the client.
        This message explicitly tells the CA that a given object exists, of a given type, and allows the client to send field updates to that object even if the client cannot currently see that object.
        """

        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_DECLARE_OBJECT)
        dg.add_uint32(doId)
        dg.add_uint32(zoneId)

        self.air.send(dg)

    declareObject = declare_object

    def undeclare_object(self, clientChannel: int, doId: int) -> None:
       """
       Antithesis of declare_object: the object is no longer explicitly declared, and the client can no longer send updates on this object without seeing it.
       """ 

       dg = PyDatagram()
       dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_UNDECLARE_OBJECT)
       dg.add_uint32(doId)
    
       self.air.send(dg)

    def client_add_session_object(self, clientChannel: int, doId: int) -> None:
        """
        Declares the specified DistributedObject to be a "session object",
        meaning that it is destroyed when the client disconnects.
        Generally used for avatars owned by the client.
        """

        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_ADD_SESSION_OBJECT)
        dg.add_uint32(doId)

        self.air.send(dg)

    clientAddSessionObject = client_add_session_object

    def client_remove_session_object(self, clientChannel: int, doId: int) -> None:
        """
        Antithesis of client_add_session_object. The declared object is no longer tied to the client's session, and will therefore 
        not be deleted if the client drops (nor will the client be dropped if this object is deleted).
        """
        
        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_REMOVE_SESSION_OBJECT)
        dg.add_uint32(doId)

        self.air.send(dg)
        
    def set_fields_sendable(self, do: object, channelId: int, fieldNameList: list = []) -> None:
        """
        Overrides the security of a field(s) specified, allows an owner of a DistributedObject to send
        the field(s) regardless if its marked ownsend/clsend.
        """

        dg = PyDatagram()
        dg.addServerHeader(channelId, self.air.ourChannel, msgtypes.CLIENTAGENT_SET_FIELDS_SENDABLE)
        fieldIds = []
        for fieldName in fieldNameList:
            field = do.dclass.getFieldByName(fieldName)

            if not field:
                continue

            fieldIds.append(field.getNumber())

        dg.add_uint32(do.doId)
        dg.add_uint16(len(fieldIds))
        for fieldId in fieldIds:
            dg.add_uint16(fieldId)

        self.air.send(dg)

    setAllowClientSend = set_fields_sendable
    set_allow_client_send = set_fields_sendable # Legacy alias

    def get_tlvs(self, clientChannel: int, callback: object) -> None:
        """
        Requests the TLVs associated with the client.
        """

        ctx = self.air.get_context()
        self.__callbacks[ctx] = callback

        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_GET_CLIENTTLVS)
        dg.add_uint32(ctx)

        self.air.send(dg)

    getTlvs = get_tlvs

    def handle_get_tlvs_response(self, di: PyDatagramIterator) -> None:
        """
        Returns the blob representation of the TLVs associated with the client, as provided by HAProxy.
        """

        ctx = di.get_uint32()
        tlvs = di.get_remaining_bytes()

        if ctx not in self.__callbacks:
            self.notify.warning('Received unexpected CLIENTAGENT_GET_CLIENTTLVS_RESP (ctx: %d)' % ctx)
            return

        try:
            self.__callbacks[ctx](tlvs)
        finally:
            del self.__callbacks[ctx]

    def client_open_channel(self, clientChannel: int, newChannel: int) -> None:
        """
        Instruct the client session to open a channel on the MD. Messages sent to this new channel will be processed by the CA.
        """

        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_OPEN_CHANNEL)
        dg.add_uint64(newChannel)

        self.air.send(dg)

    clientOpenChannel = client_open_channel

    def client_close_channel(self, clientChannel: int, channel: int) -> None:
        """
        This message is the antithesis of the message above. The channel is immediately closed, even if the channel was automatically opened.
        """

        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_CLOSE_CHANNEL)
        dg.add_uint64(channel)

        self.air.send(dg)

    clientCloseChannel = client_close_channel

    def client_add_post_remove(self, clientChannel:int, datagram: object) -> None:
        """
        Similar to CONTROL_ADD_POST_REMOVE, this hangs a "post-remove" message on the client. If the client is ever disconnected, the post-remove messages will be sent out automatically.
        """

        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_ADD_POST_REMOVE)
        dg.add_string(datagram.getMessage())

        self.air.send(dg)

    clientAddPostRemove = client_add_post_remove

    def client_clear_post_remove(self, clientChannel: int) -> None:
        """
        Removes all post-remove messages from the client.
        """

        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_CLEAR_POST_REMOVES)

        self.air.send(dg)

    clientClearPostRemove = client_clear_post_remove

    def client_add_interest(self, client_channel: int, interest_id: int, parent_id: int, zone_id: int, callback: object = None) -> None:
        """
        Opens an interest on the behalf of the client. This, used in conjunction
        with add_interest: visible (or preferably, disabled altogether), will mitigate
        possible security risks.
        """

        dg = PyDatagram()
        dg.addServerHeader(client_channel, self.air.ourChannel, msgtypes.CLIENTAGENT_ADD_INTEREST)
        dg.add_uint16(interest_id)
        dg.add_uint32(parent_id)
        dg.add_uint32(zone_id)

        self.air.send(dg)

        if callback != None:
            ctx = (client_channel, interest_id)
            self.__callbacks[ctx] = callback

    clientAddInterest = client_add_interest

    def client_add_interest_multiple(self, client_channel: int, interest_id: int, parent_id: int, zone_list: int, callback: object = None) -> None:
        """
        Opens multiple interests on the behalf of the client. This, used in conjunction
        with add_interest: visible (or preferably, disabled altogether), will mitigate
        possible security risks.
        """

        dg = PyDatagram()
        dg.addServerHeader(client_channel, self.air.ourChannel, msgtypes.CLIENTAGENT_ADD_INTEREST_MULTIPLE)
        dg.add_uint16(interest_id)
        dg.add_uint32(parent_id)

        dg.add_uint16(len(zone_list))
        for zoneId in zone_list:
            dg.add_uint32(zoneId)

        if callback != None:
            ctx = (client_channel, interest_id)
            self.__callbacks[ctx] = callback

        self.air.send(dg)

    clientAddInterestMultiple = client_add_interest_multiple

    def client_remove_interest(self, client_channel: int, interest_id: int, callback: object = None) -> None:
        """
        Removes an interest on the behalf of the client. This, used in conjunction
        with add_interest: visible (or preferably, disabled altogether), will mitigate
        possible security risks.
        """

        dg = PyDatagram()
        dg.addServerHeader(client_channel, self.air.ourChannel, msgtypes.CLIENTAGENT_REMOVE_INTEREST)
        dg.add_uint16(interest_id)
        
        self.air.send(dg)

        if callback != None:
            ctx = (client_channel, interest_id)
            self.__callbacks[ctx] = callback

    clientRemoveInterest = client_remove_interest

    def handle_client_agent_interest_done_resp(self, di: PyDatagramIterator) -> None:
        """
        Sent by the ClientAgent to the caller of CLIENTAGENT_ADD_INTEREST to inform them 
        that the interest operation has completed.
        """

        client_channel = di.get_uint64()
        interest_id    = di.get_uint16()
        ctx = (client_channel, interest_id)

        if ctx not in self.__callbacks:
            return

        try:
            self.__callbacks[ctx](client_channel, interest_id)
        finally:
            del self.__callbacks[ctx]

    def send_system_message(self, message: str, clientChannel: int = 10) -> None:
        """
        Sends a CLIENT_SYSTEM_MESSAGE to the given client channel.
        """

        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_SEND_SYSTEM_MESSAGE)
        dg.add_string(message)

        self.send_client_datagram(clientChannel, dg)

    sendSystemMessage = send_system_message