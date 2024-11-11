"""
Client Agent Interface for Astron
"""

from direct.directnotify import DirectNotifyGlobal
from direct.distributed.PyDatagram import PyDatagram
from direct.distributed.PyDatagramIterator import PyDatagramIterator

from panda3d import direct
from panda3d import core as p3d
from panda3d_astron import msgtypes

class ClientAgentInterface(object):
    """
    Network interface for the client agent.
    """

    notify = DirectNotifyGlobal.directNotify.newCategory("client-agent")

    def __init__(self, air: object):
        """
        Initialize the client agent interface.
        """

        self.air = air
        self.__callbacks = {}

    def handle_datagram(self, msg_type: int, di: object) -> None:
        """
        Handles client agent datagrams
        """

        if msg_type == msgtypes.CLIENTAGENT_GET_NETWORK_ADDRESS_RESP:
            self.handle_get_network_address_resp(di)
        elif msg_type == msgtypes.CLIENTAGENT_DONE_INTEREST_RESP:
            self.handle_client_agent_interest_done_resp(di)
        else:
            self.notify.warning(f"Received unknown message type {msg_type} from client agent")

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

        ctx         = di.get_uint32()
        remoteIp    = di.get_string()
        remotePort  = di.get_uint16()
        localIp     = di.get_string()
        localPort   = di.get_uint16()

        if ctx not in self.__callbacks:
            self.notify.warning('Received unexpected CLIENTAGENT_GET_NETWORK_ADDRESS_RESP (ctx: %d)' % ctx)
            return

        try:
            self.__callbacks[ctx](remoteIp, remotePort, localIp, localPort)
        finally:
            del self.__callbacks[ctx]

    def eject(self, clientChannel, reasonCode, reason):
        """
        Kicks the client residing at the specified clientChannel, using the specifed reasoning.
        """

        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_EJECT)
        dg.add_uint16(reasonCode)
        dg.add_string(reason)
        self.air.send(dg)

    Eject = eject

    def set_client_state(self, clientChannel, state):
        """
        Sets the state of the client on the CA.
        Useful for logging in and logging out, and for little else.
        """

        dg = PyDatagram()
        dg.addServerHeader(clientChannel, self.air.ourChannel, msgtypes.CLIENTAGENT_SET_STATE)
        dg.add_uint16(state)
        self.air.send(dg)

    setClientState = set_client_state

    def set_allow_client_send(self, do, channelId, fieldNameList=[]):
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

    setAllowClientSend = set_allow_client_send

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

        client_channel  = di.get_uint64()
        interest_id     = di.get_uint16()
        ctx = (client_channel, interest_id)

        if ctx not in self.__callbacks:
            return

        try:
            self.__callbacks[ctx](client_channel, interest_id)
        finally:
            del self.__callbacks[ctx]